"""
Email Threading & Continuity Fix
=================================
Ensures replies always continue in the same ticket even when:
  - CC/To recipients change
  - Client breaks the In-Reply-To chain
  - Email is forwarded or re-composed

Three layers of defence:
  1. Outgoing: set RFC-2822 `References` header (full chain of Message-IDs)
  2. Incoming: read `References` header as fallback when In-Reply-To is missing
  3. Incoming: extract ticket ID from subject line as last resort
"""

import frappe
from frappe import _
from frappe.utils import get_string_between


# ── Layer 2 & 3: Patched parent_communication() ──────────────────────────────

def get_parent_communication_with_fallback(inbound_mail):
    """
    Extended version of InboundMail.parent_communication().

    Priority order:
      1. Exact In-Reply-To → Communication.message_id  (Frappe default)
      2. In-Reply-To → EmailQueue.communication         (Frappe default)
      3. In-Reply-To parsed as Communication name       (Frappe default)
      4. [NEW] Any Message-ID in References header      (RFC 2822 fallback)
      5. [NEW] Ticket/document ID extracted from subject line
    """
    from frappe.core.doctype.communication.communication import Communication

    # ── Strategies 1-3: existing Frappe logic ────────────────────────────────
    in_reply_to = inbound_mail.in_reply_to

    if in_reply_to:
        # Strategy 1: Direct message_id match
        comm = Communication.find_one_by_filters(
            message_id=in_reply_to, order_by="creation DESC"
        )
        if comm:
            return comm

        # Strategy 2: Via EmailQueue
        from frappe.email.doctype.email_queue.email_queue import EmailQueue
        eq = EmailQueue.find_one_by_filters(message_id=in_reply_to)
        if eq and eq.communication:
            comm = Communication.find(eq.communication, ignore_error=True)
            if comm:
                return comm

        # Strategy 3: In-Reply-To contains Communication name
        reference = in_reply_to
        if "@" in in_reply_to:
            reference, _ = in_reply_to.split("@", 1)
        comm = Communication.find(reference, ignore_error=True)
        if comm:
            return comm

    # ── Strategy 4: References header (RFC 2822) ──────────────────────────────
    references_header = inbound_mail.mail.get("References") or ""
    if references_header:
        # References is a space-separated list of Message-IDs (newest last)
        # Try each one, starting from the most recent (rightmost)
        ref_ids = references_header.split()
        for ref in reversed(ref_ids):
            ref_clean = get_string_between("<", ref, ">") or ref.strip("<>")
            if not ref_clean:
                continue

            # Try message_id match in Communication
            comm = Communication.find_one_by_filters(
                message_id=ref_clean, order_by="creation DESC"
            )
            if comm:
                frappe.logger("email_threading").info(
                    f"Thread recovered via References header: {ref_clean} → {comm.name}"
                )
                return comm

            # Try message_id match in EmailQueue
            from frappe.email.doctype.email_queue.email_queue import EmailQueue
            eq = EmailQueue.find_one_by_filters(message_id=ref_clean)
            if eq and eq.communication:
                comm = Communication.find(eq.communication, ignore_error=True)
                if comm:
                    frappe.logger("email_threading").info(
                        f"Thread recovered via References→EmailQueue: {ref_clean} → {comm.name}"
                    )
                    return comm

    # ── Strategy 5: Extract document/ticket ID from subject line ─────────────
    subject = inbound_mail.subject or ""
    comm = _find_communication_by_subject_ticket_id(subject, inbound_mail.email_account)
    if comm:
        frappe.logger("email_threading").info(
            f"Thread recovered via subject ticket ID: '{subject}' → {comm.name}"
        )
        return comm

    return ""


def _find_communication_by_subject_ticket_id(subject, email_account):
    """
    Extract a document name from subject patterns like:
      - [#ACC-JV-2026-001]
      - (#TICKET-2026-001)
      - Re: Something [Ticket #HD-TKT-2026-00123]
    and find the most recent Communication linked to that document.
    """
    import re
    from frappe.core.doctype.communication.communication import Communication

    # Match patterns: [#NAME], (#NAME), [Ticket #NAME], #NAME at end
    patterns = [
        r"\[#([A-Z0-9]+-[A-Z0-9-]+)\]",
        r"\(#([A-Z0-9]+-[A-Z0-9-]+)\)",
        r"#([A-Z0-9]+-[A-Z0-9-]+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, subject, re.IGNORECASE)
        if not match:
            continue

        doc_name = match.group(1)

        # Find Communications referencing this document name
        comm = frappe.db.get_value(
            "Communication",
            filters={
                "reference_name": doc_name,
                "communication_medium": "Email",
            },
            fieldname="name",
            order_by="creation DESC",
        )
        if comm:
            return Communication.find(comm, ignore_error=True)

    return None


# ── Layer 1: Set References header on outgoing emails ────────────────────────

def set_references_header_on_queue(email_queue_doc, mail):
    """
    Called after email_queue builds the mail object.
    Builds the RFC 2822 `References` header by collecting the full
    chain of Message-IDs from ancestor Communications.
    """
    if not email_queue_doc.in_reply_to:
        return

    chain = _collect_message_id_chain(email_queue_doc.in_reply_to)
    if chain:
        mail.set_header("References", " ".join(f"<{mid}>" for mid in chain if mid))


def _collect_message_id_chain(communication_name, depth=0, max_depth=20):
    """
    Walk up the Communication.in_reply_to chain and collect all message_ids
    in chronological order (oldest first) for the References header.
    """
    if depth > max_depth or not communication_name:
        return []

    row = frappe.db.get_value(
        "Communication",
        communication_name,
        ["message_id", "in_reply_to"],
        as_dict=True,
    )
    if not row:
        return []

    parent_chain = _collect_message_id_chain(row.in_reply_to, depth + 1, max_depth)
    if row.message_id:
        parent_chain.append(row.message_id)
    return parent_chain


# ── Monkey-patch entry point ──────────────────────────────────────────────────

def apply_patches():
    """
    Apply all email threading patches.
    Call this from frappe's hooks: on_session_creation or a scheduler event,
    or simply import this module in your app's __init__.py.
    """
    _patch_inbound_mail_parent_communication()
    _patch_email_queue_send()


def _patch_inbound_mail_parent_communication():
    """Replace InboundMail.parent_communication with our extended version."""
    try:
        from frappe.email.receive import InboundMail

        def patched_parent_communication(self):
            if self._parent_communication is not None:
                return self._parent_communication
            if not self.is_reply() and not (self.mail.get("References") or ""):
                return ""
            result = get_parent_communication_with_fallback(self)
            self._parent_communication = result
            return self._parent_communication

        InboundMail.parent_communication = patched_parent_communication
        frappe.logger("email_threading").debug("InboundMail.parent_communication patched.")
    except Exception as e:
        frappe.logger("email_threading").error(f"Failed to patch parent_communication: {e}")


def _patch_email_queue_send():
    """Inject References header into outgoing email queue send."""
    try:
        from frappe.email.doctype.email_queue.email_queue import EmailQueue

        original_build_message = EmailQueue.build_message

        def patched_build_message(self, recipient_email):
            mail = original_build_message(self, recipient_email)
            try:
                set_references_header_on_queue(self, mail)
            except Exception as e:
                frappe.logger("email_threading").warning(
                    f"Could not set References header on {self.name}: {e}"
                )
            return mail

        EmailQueue.build_message = patched_build_message
        frappe.logger("email_threading").debug("EmailQueue.build_message patched.")
    except Exception as e:
        frappe.logger("email_threading").error(f"Failed to patch EmailQueue.build_message: {e}")
