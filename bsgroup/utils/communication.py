import re
import frappe
from frappe.utils import add_days, now_datetime


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

                cutoff = add_days(now_datetime(), -180)

                existing = frappe.get_all(
                    'HD Ticket',
                    filters={
                        'custom_external_reference': partner_key,
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