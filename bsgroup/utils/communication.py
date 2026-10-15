import re
import frappe
from frappe.utils import add_days, now_datetime

# W-2: this hook is the single app implementation of partner email threading.
# The production Server Script "HD Partner Email Threading - Communication
# Before Insert" (exported under bsgroup/dcs/server_script_export) does the
# same job with a fixed prefix scan against HD Ticket.external_reference and
# the *oldest* match. Both are active on production today; the hook runs
# first (doc_events precede Server Scripts in Document.run_method) and the
# script only acts when the hook attached nothing. To make the hook a strict
# superset before the script is retired, it now (a) falls back to the same
# prefix scan when a Partner Email Source has no regex configured and
# (b) reads whichever external-reference field the site's HD Ticket carries.
PARTNER_KEY_PREFIXES = ("INC-", "SR-", "REQ-", "CHG-", "PRB-", "TASK-", "TKT-")
THREADING_WINDOW_DAYS = 180


def _external_reference_field():
    """Fieldname on HD Ticket holding the partner key on this site, or None."""
    meta = frappe.get_meta("HD Ticket")
    for fieldname in ("custom_external_reference", "external_reference"):
        if meta.has_field(fieldname):
            return fieldname
    return None


def scan_partner_key(subject):
    """Prefix scan identical to the Server Script: first prefix found, digits that follow."""
    subj_upper = (subject or "").upper()
    for prefix in PARTNER_KEY_PREFIXES:
        idx = subj_upper.find(prefix)
        if idx < 0:
            continue
        start = end = idx + len(prefix)
        while end < len(subj_upper) and subj_upper[end].isdigit():
            end += 1
        if end > start:
            return prefix + subj_upper[start:end]
    return None


def hd_partner_email_threading(doc, method=None):

    try:
        if doc.doctype != 'Communication':
            return

        elif (doc.communication_medium or '').lower() != 'email':
            return

        elif (doc.sent_or_received or '').lower() != 'received':
            return

        elif doc.reference_doctype and doc.reference_name:
            return

        sender = (doc.sender or '').lower().strip()
        domain = sender.split('@')[-1] if '@' in sender else ''
        subject = doc.subject or ''
        content = (doc.content or '')[:2000]

        target_ticket = None
        partner_key = None

        # 1. Standard email threading
        in_reply_to = doc.in_reply_to

        if in_reply_to:
            parent_comm = frappe.db.get_value(
                'Communication',
                in_reply_to,
                ['reference_doctype', 'reference_name'],
                as_dict=True
            )

            if (
                parent_comm
                and parent_comm.reference_doctype == 'HD Ticket'
                and parent_comm.reference_name
            ):
                target_ticket = parent_comm.reference_name

        # 2. Partner regex matching
        if not target_ticket and domain:

            sources = frappe.get_all(
                'Partner Email Source',
                filters={
                    'sender_domain': domain,
                    'active': 1
                },
                fields=[
                    'subject_regex',
                    'body_regex',
                    'capture_group'
                ],
            )

            for src in sources:

                grp = src.capture_group or 1

                if not (src.subject_regex or src.body_regex):
                    # No regex configured for this partner: behave exactly as
                    # the Server Script did (prefix scan on the subject).
                    partner_key = scan_partner_key(subject)
                    if partner_key:
                        break

                for pattern, text in (
                    (src.subject_regex, subject),
                    (src.body_regex, content)
                ):

                    if not pattern or not text:
                        continue

                    try:
                        m = re.search(pattern, text)

                    except re.error:
                        continue

                    if m:

                        try:
                            partner_key = m.group(grp)

                        except IndexError:
                            partner_key = m.group(0)

                        break

                if partner_key:
                    break

            # 3. Find existing ticket
            if partner_key:

                ref_field = _external_reference_field()
                if ref_field:
                    cutoff = add_days(now_datetime(), -THREADING_WINDOW_DAYS)

                    existing = frappe.get_all(
                        'HD Ticket',
                        filters={
                            ref_field: partner_key,
                            'modified': ['>', cutoff]
                        },
                        fields=['name'],
                        order_by='modified desc',
                        limit=1,
                    )

                    if existing:
                        target_ticket = existing[0].name

        # 4. Attach communication
        if target_ticket:

            doc.reference_doctype = 'HD Ticket'
            doc.reference_name = target_ticket
            doc.flags.skip_new_ticket_creation = True

        elif partner_key:

            frappe.local.hd_pending_external_reference = partner_key

    except Exception:

        frappe.log_error(
            frappe.get_traceback(),
            'HD Partner Email Threading'
        )