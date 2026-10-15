# HD Partner Email Threading - Communication Before Insert
# Sandbox-safe rewrite. No 'import' statements. No regex module.
# Goal: when an inbound email from a known partner domain (Partner Email Source)
# carries a partner ticket key in the subject (e.g. [#INC-188488]),
# attach this Communication to the existing HD Ticket that has matching
# external_reference, instead of letting Frappe create a duplicate ticket.
#
# Fail-safe: any exception is swallowed and logged. Email ingestion must
# never be blocked by this script.

try:
    # ------- Guards: only process inbound email Communications -------
    if doc.doctype != "Communication":
        pass
    elif (doc.communication_medium or "").lower() != "email":
        pass
    elif (doc.sent_or_received or "").lower() != "received":
        pass
    elif doc.reference_doctype and doc.reference_name:
        # Already attached (Frappe In-Reply-To matched). Nothing to do.
        pass
    else:
        sender = (doc.sender or "").lower().strip()
        domain = ""
        if "@" in sender:
            domain = sender.split("@")[-1].strip()

        subject = doc.subject or ""

        partner_key = None
        target_ticket = None

        if domain:
            # Check if this domain is a known partner ITSM
            active_partner = frappe.db.get_value(
                "Partner Email Source",
                {"sender_domain": domain, "active": 1},
                "name"
            )

            if active_partner:
                # ------- Sandbox-safe key extraction (no regex) -------
                # Scan subject for known ITSM prefixes. The prefixes cover
                # ServiceNow / Jira-style / generic ITSM naming.
                prefixes = ["INC-", "SR-", "REQ-", "CHG-", "PRB-", "TASK-", "TKT-"]

                # Walk subject char-by-char looking for any prefix.
                # When a prefix is matched, collect following digits.
                subj_upper = subject.upper()
                for prefix in prefixes:
                    idx = subj_upper.find(prefix)
                    if idx < 0:
                        continue
                    digit_start = idx + len(prefix)
                    digit_end = digit_start
                    n = len(subj_upper)
                    while digit_end < n and subj_upper[digit_end].isdigit():
                        digit_end += 1
                    if digit_end > digit_start:
                        # At least one digit found. e.g. INC-188488
                        partner_key = prefix + subj_upper[digit_start:digit_end]
                        break

                if partner_key:
                    # Find the oldest HD Ticket with this external_reference
                    matching = frappe.db.get_list(
                        "HD Ticket",
                        filters={"external_reference": partner_key},
                        fields=["name"],
                        order_by="creation asc",
                        limit=1
                    )
                    if matching:
                        target_ticket = matching[0].get("name")

        # ------- Attach to existing ticket if we found one -------
        if target_ticket:
            doc.reference_doctype = "HD Ticket"
            doc.reference_name = target_ticket
            # Flag so any downstream Helpdesk hook knows we already linked
            doc.flags.partner_threaded = True

except Exception:
    # Log and swallow. Never block the email pipeline.
    frappe.log_error(title="HD Partner Email Threading - non-fatal")
