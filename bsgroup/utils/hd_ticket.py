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


def _domain_from_email(email):
	if not email or "@" not in email:
		return None
	return email.rsplit("@", 1)[-1].strip().lower()


def _find_customer_by_domain(domain):
	"""Match `domain` against HD Customer.domain. That field is stored
	inconsistently across existing records - sometimes a bare domain
	("alamar.com"), sometimes a full email ("support@alamar.com") - so
	compare on the domain part of whatever is stored, not the raw value."""

	if not domain:
		return None

	customers = frappe.get_all("HD Customer", filters={"domain": ["!=", ""]}, fields=["name", "domain"])
	for c in customers:
		stored_domain = _domain_from_email(c.domain) or (c.domain or "").strip().lower()
		if stored_domain == domain:
			return c.name

	return None


def set_customer_from_domain(doc, method=None):
	"""Auto-populate HD Ticket.customer from HD Customer.domain, matched against
	the raised_by email's domain, whenever no customer is set yet."""

	if doc.customer:
		return

	domain = _domain_from_email(doc.raised_by)
	customer = _find_customer_by_domain(domain)
	if customer:
		doc.customer = customer


@frappe.whitelist()
def get_customer_by_domain(email):
	"""Return the HD Customer name whose domain matches `email`'s domain, or None."""
	return _find_customer_by_domain(_domain_from_email(email))


def sync_zztest_scheduler_status(doc, method=None):
	"""ZZTEST POC v2: derive Tech Task Scheduler List status from the linked
	Scheduler Execution and the HD Ticket itself ONLY - never from whether the
	Timesheet is Draft, Submitted or Cancelled.

	Performs NO action unless the ticket's subject starts with "ZZTEST"."""

	if not (doc.subject or "").startswith("ZZTEST"):
		return

	rows = frappe.get_all(
		"Tech Task Scheduler List",
		filters={"ticket": doc.name},
		fields=["name", "status"],
	)

	for row in rows:
		if row.status in ("Cancelled", "Cancelled/Reassigned"):
			continue

		execution = frappe.db.get_value(
			"Scheduler Execution",
			{"scheduler_row": row.name},
			["name", "actual_start", "actual_end", "blocker_category", "blocker_details", "operational_status"],
			as_dict=True,
		)

		if doc.status in ("Resolved", "Closed"):
			new_status = "Closed"
		elif not execution:
			new_status = "Scheduled"
		elif execution.operational_status == "Cancelled":
			new_status = "Cancelled/Reassigned"
		elif execution.blocker_category or execution.blocker_details:
			new_status = "Pending/Blocked"
		elif execution.actual_end:
			new_status = "Work Logged"
		elif execution.actual_start:
			new_status = "In Progress"
		else:
			new_status = "Scheduled"

		if new_status != row.status:
			frappe.db.set_value(
				"Tech Task Scheduler List",
				row.name,
				"status",
				new_status,
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


@frappe.whitelist()
def resolve_ticket(ticket_name, resolution_details, status=None):
	"""Set an HD Ticket's resolution details and mark it resolved, from the
	backend only. Setting `status` to a "Resolved"-category status and
	saving triggers HD Ticket's own before_save -> apply_sla(), which
	recomputes resolution_date/agreement_status - so the Resolution SLA
	badge in the Helpdesk UI updates automatically; no frontend change
	needed."""
	if not frappe.db.exists("HD Ticket", ticket_name):
		frappe.throw(f"HD Ticket {ticket_name} does not exist")

	doc = frappe.get_doc("HD Ticket", ticket_name)

	if not status:
		status = frappe.db.get_value(
			"HD Ticket Status", {"category": "Resolved"}, "name"
		)
		if not status:
			frappe.throw("No HD Ticket Status with category 'Resolved' is configured")

	doc.resolution_details = resolution_details
	doc.status = status
	doc.save(ignore_permissions=True)

	return {
		"status": doc.status,
		"resolution_details": doc.resolution_details,
		"resolution_date": doc.resolution_date,
		"agreement_status": doc.agreement_status,
	}
