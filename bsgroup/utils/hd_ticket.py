import re
import frappe

# HD Ticket status -> Tech Task Scheduler List status.
# Statuses not listed here (e.g. custom ones the mapping doesn't cover) are left alone.
HD_TICKET_TTS_STATUS_MAP = {
	"Open": "Open",
	"Replied": "Pending",
	"Awaiting Customer Response": "Pending",
	"Resolved": "Completed",
	"Closed": "Completed",
}


def sync_tts_status(doc, method=None):
	"""Push an HD Ticket's status onto every Tech Task Scheduler List row
	linked to it (category = HD Ticket, category_name = this ticket),
	so schedulers reflect the ticket's current state without manual edits."""

	tts_status = HD_TICKET_TTS_STATUS_MAP.get(doc.status)
	if not tts_status:
		return

	rows = frappe.get_all(
		"Tech Task Scheduler List",
		filters={
			"category": "HD Ticket",
			"category_name": doc.name,
			"status": ["not in", ["Cancelled", tts_status]],
		},
		fields=["name", "parent"],
	)

	for row in rows:
		if frappe.db.get_value("Tech Task Scheduler", row.parent, "docstatus") == 2:
			continue

		frappe.db.set_value(
			"Tech Task Scheduler List",
			row.name,
			"status",
			tts_status,
			update_modified=False,
		)


def _clean_subject(subject):
	"""Strip Re:/Fwd: prefixes and any [#...] ticket references."""
	subject = re.sub(r'\[#[^\]]+\]', '', subject or '')
	subject = re.sub(r'^(re|fw|fwd)\s*:\s*', '', subject.strip(), flags=re.IGNORECASE)
	return subject.strip().lower()


def _find_original_ticket(doc):
	"""Return the name of an existing open ticket with the same cleaned subject, or None."""
	clean = _clean_subject(doc.subject)
	if not clean:
		return None

	candidates = frappe.db.get_all(
		'HD Ticket',
		filters={
			'name': ('!=', doc.name),
			'raised_by': doc.raised_by,
			'status': ('not in', ['Closed', 'Resolved']),
			'is_merged': 0,
		},
		fields=['name', 'subject'],
		order_by='creation asc',
		limit=20,
	)

	for ticket in candidates:
		if _clean_subject(ticket.subject) == clean:
			return ticket.name

	return None


def thread_email_to_existing_ticket(doc, method):
	"""
	After a new HD Ticket is inserted via email, if an open ticket with the
	same subject already exists for the same sender, move the communication
	to the original ticket and enqueue deletion of this duplicate.
	Deletion is deferred via frappe.enqueue to avoid a deadlock with
	Helpdesk's own after_insert which still holds a lock on this record.
	"""
	if doc.via_customer_portal or not doc.raised_by:
		return

	original = _find_original_ticket(doc)
	if not original:
		return

	frappe.logger().info(
		f"HD Ticket {doc.name}: duplicate of {original} "
		f"(subject: '{doc.subject}'). Scheduling cleanup."
	)

	# Move communications NOW (safe — no lock conflict on Communication table)
	frappe.db.sql(
		"""
		UPDATE `tabCommunication`
		SET reference_name = %s
		WHERE reference_doctype = 'HD Ticket'
		AND reference_name = %s
		""",
		(original, doc.name),
	)

	# Enqueue deletion so it runs after this transaction fully commits,
	# avoiding the deadlock caused by Helpdesk's own after_insert lock.
	frappe.enqueue(
		'bsgroup.utils.hd_ticket.delete_duplicate_ticket',
		ticket_name=doc.name,
		original_name=original,
		queue='short',
		now=frappe.flags.in_test,  # run synchronously in test mode
	)


def delete_duplicate_ticket(ticket_name, original_name):
	"""Enqueued job: delete the duplicate ticket after the insert transaction commits."""
	if not frappe.db.exists('HD Ticket', ticket_name):
		return

	frappe.delete_doc('HD Ticket', ticket_name, ignore_permissions=True, force=True)
	frappe.db.commit()

	frappe.logger().info(
		f"HD Ticket {ticket_name} deleted. "
		f"Communication threaded into #{original_name}."
	)
