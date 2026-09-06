# Copyright (c) 2026, Tridots Tech and contributors
# For license information, please see license.txt

"""Lead Intake — canonical staging record for inbound interactions.

Integrations (3CX, chat, web forms) write to this DocType only; an ERPNext
``Lead`` is created solely through :meth:`LeadIntake.convert_to_lead`, and only
from a qualified intake. Keeping this indirection lets us normalize, de-duplicate
and (optionally) AI-enrich before anything reaches the CRM.
"""

import hashlib
import re

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import now_datetime

# Company context preserved on the converted Lead where the field permits it.
LEAD_COMPANY = "Bits Secure IT Infrastructure LLC - AE"

# Default country used when a caller does not tell us where a number is from.
DEFAULT_COUNTRY = "AE"

# ISO country code -> international dialling code, for national-number expansion.
COUNTRY_DIAL = {
	"AE": "971",
	"OM": "968",
	"SA": "966",
	"QA": "974",
	"BH": "973",
	"KW": "965",
	"IN": "91",
	"GB": "44",
	"US": "1",
}

# Statuses that must not be treated as live duplicates when matching.
INACTIVE_MATCH_STATUSES = ("Disqualified", "Duplicate")


class LeadIntake(Document):
	def validate(self):
		self.normalize_identity()
		self.set_idempotency_key()
		self.set_defaults()
		self.match_duplicates()

	# --- normalization -------------------------------------------------

	def normalize_identity(self):
		self.full_name = (self.full_name or "").strip() or None
		self.organization_name = (self.organization_name or "").strip() or None
		self.email = (self.email or "").strip() or None
		self.normalized_email = normalize_email(self.email)
		self.normalized_phone = normalize_phone(self.phone, self.country)

	def set_idempotency_key(self):
		"""Composite uniqueness for external_system + external_interaction_id.

		Stored in a single ``unique`` column so the database — not application
		code — is the final arbiter of idempotency, even under concurrency.
		"""
		if self.external_interaction_id:
			system = (self.external_system or "3CX").strip()
			self.idempotency_key = f"{system}:{self.external_interaction_id}".strip()
		else:
			# No external id -> not an idempotent integration record.
			self.idempotency_key = None

	def set_defaults(self):
		if not self.status:
			self.status = "New"
		if not self.ai_status:
			self.ai_status = "Pending"
		if not self.external_system:
			self.external_system = "3CX"

	# --- duplicate matching --------------------------------------------

	def match_duplicates(self):
		"""Link the most likely existing records by normalized phone/email.

		Populates read-only routing fields only; it never mutates ``status`` to
		``Duplicate`` on its own so a human/AI decision stays authoritative.
		"""
		if not (self.normalized_phone or self.normalized_email):
			return

		self.duplicate_of = self.find_duplicate_intake()
		self.matched_lead = find_matching_lead(self.normalized_phone, self.normalized_email)
		self.matched_contact = find_matching_contact(self.normalized_phone, self.normalized_email)

	def find_duplicate_intake(self):
		filters = []
		if self.normalized_phone:
			filters.append(["normalized_phone", "=", self.normalized_phone])
		if self.normalized_email:
			filters.append(["normalized_email", "=", self.normalized_email])

		or_filters = filters
		base_filters = {"status": ["not in", INACTIVE_MATCH_STATUSES]}
		if not self.is_new():
			base_filters["name"] = ["!=", self.name]

		matches = frappe.get_all(
			"Lead Intake",
			filters=base_filters,
			or_filters=or_filters,
			order_by="creation asc",
			limit=1,
			pluck="name",
		)
		return matches[0] if matches else None

	# --- conversion -----------------------------------------------------

	@frappe.whitelist()
	def convert_to_lead(self):
		"""Create or link an ERPNext Lead from a qualified intake, idempotently.

		Returns the Lead name. Safe to call repeatedly: once ``converted_lead``
		is set it is returned unchanged.
		"""
		if self.converted_lead:
			return self.converted_lead

		if self.status != "Qualified":
			frappe.throw(
				_("Only a Qualified Lead Intake can be converted. Current status: {0}").format(self.status)
			)

		# Reuse an already-matched Lead rather than creating a second one.
		lead_name = self.matched_lead or find_matching_lead(self.normalized_phone, self.normalized_email)

		if not lead_name:
			lead = frappe.new_doc("Lead")
			lead.lead_name = self.full_name or self.organization_name or "Unknown"
			# Organization Name is mandatory on Lead; fall back to the person's
			# name for individual (no-organization) leads.
			lead.company_name = self.organization_name or self.full_name or "Unknown"
			lead.email_id = self.normalized_email or self.email
			lead.mobile_no = self.normalized_phone or self.phone
			if self.normalized_phone:
				lead.whatsapp_no = self.normalized_phone
			# Preserve company context only when that Company actually exists.
			if frappe.db.exists("Company", LEAD_COMPANY):
				lead.company = LEAD_COMPANY
			lead.insert()
			lead_name = lead.name

		self.db_set(
			{
				"converted_lead": lead_name,
				"matched_lead": lead_name,
				"converted_on": now_datetime(),
				"status": "Converted",
			}
		)
		return lead_name


# --- module-level normalization helpers ------------------------------------


def normalize_email(email):
	"""Lower-case and trim an email; return ``None`` when empty/invalid-ish."""
	if not email:
		return None
	value = str(email).strip().lower()
	# Require a bare ``local@domain`` shape; otherwise it is not matchable.
	if "@" not in value or value.startswith("@") or value.endswith("@"):
		return None
	return value


def normalize_phone(phone, country=None):
	"""Return an E.164-style ``+<cc><national>`` string, or ``None``.

	Handles UAE/Oman/international shapes: a leading ``+`` or ``00`` is treated
	as already international; a national number (optionally with a trunk ``0``)
	is expanded using ``country`` (default UAE).
	"""
	if phone is None:
		return None
	raw = str(phone).strip()
	if not raw:
		return None

	is_intl = raw.startswith("+") or raw.startswith("00")
	digits = re.sub(r"\D", "", raw)
	if not digits:
		return None

	if is_intl:
		if raw.startswith("00"):
			digits = digits[2:]
		return "+" + digits if digits else None

	cc = COUNTRY_DIAL.get((country or DEFAULT_COUNTRY).upper(), COUNTRY_DIAL[DEFAULT_COUNTRY])

	# Number already carries its country code but lost the ``+`` (e.g. 971501234567).
	if digits.startswith(cc) and len(digits) >= len(cc) + 7:
		return "+" + digits

	national = digits[1:] if digits.startswith("0") else digits
	return "+" + cc + national


def payload_hash(payload):
	"""Stable SHA-256 of a payload dict/string for change detection."""
	if isinstance(payload, (dict, list)):
		payload = frappe.as_json(payload)
	return hashlib.sha256((payload or "").encode("utf-8")).hexdigest()


def find_matching_lead(normalized_phone, normalized_email):
	"""Find an existing ERPNext Lead by normalized phone or email."""
	or_filters = []
	if normalized_phone:
		or_filters += [
			["mobile_no", "=", normalized_phone],
			["phone", "=", normalized_phone],
			["whatsapp_no", "=", normalized_phone],
		]
	if normalized_email:
		or_filters.append(["email_id", "=", normalized_email])
	if not or_filters:
		return None

	matches = frappe.get_all("Lead", or_filters=or_filters, order_by="creation asc", limit=1, pluck="name")
	return matches[0] if matches else None


def find_matching_contact(normalized_phone, normalized_email):
	"""Find an existing Contact by normalized phone or email (child tables)."""
	if normalized_email:
		rows = frappe.get_all(
			"Contact Email", filters={"email_id": normalized_email}, limit=1, pluck="parent"
		)
		if rows:
			return rows[0]
	if normalized_phone:
		rows = frappe.get_all("Contact Phone", filters={"phone": normalized_phone}, limit=1, pluck="parent")
		if rows:
			return rows[0]
	return None


# --- background AI placeholder ---------------------------------------------


def enqueue_ai_processing(intake_name):
	"""Queue the (placeholder) AI enrichment job for an intake.

	Kept in the background so the API request returns fast. No AI key is
	required — :func:`run_ai_placeholder` degrades gracefully.
	"""
	frappe.db.set_value("Lead Intake", intake_name, "ai_status", "Queued")
	try:
		frappe.enqueue(
			"bsgroup.bs_group.doctype.lead_intake.lead_intake.run_ai_placeholder",
			queue="short",
			job_id=f"lead-intake-ai::{intake_name}",
			deduplicate=True,
			intake_name=intake_name,
		)
	except Exception:
		# A broker hiccup must not fail the integration write; the daily/hourly
		# sweep (or a manual retry) can still enrich a stuck "Queued" intake.
		frappe.log_error(title="Lead Intake AI enqueue failed", message=frappe.get_traceback())


def run_ai_placeholder(intake_name):
	"""Deterministic, key-free enrichment stub.

	Sets a summary and a heuristic qualification so downstream flows work end to
	end today; swapping in a real model later only changes this function.
	Idempotent: skips work if already ``Completed``.
	"""
	doc = frappe.get_doc("Lead Intake", intake_name)
	if doc.ai_status == "Completed":
		return

	doc.db_set("ai_status", "Processing", commit=False)

	has_contact = bool(doc.normalized_phone or doc.normalized_email)
	qualification = "Needs Review" if has_contact else "Disqualified"
	confidence = 40 if has_contact else 10

	summary = _build_placeholder_summary(doc)
	doc.db_set(
		{
			"ai_status": "Completed",
			"ai_summary": summary,
			"ai_intent": doc.subject or "Unknown",
			"ai_qualification": qualification,
			"ai_confidence": confidence,
			"ai_next_action": "Review and qualify manually (AI model not configured).",
			"ai_processed_on": now_datetime(),
		}
	)


def _build_placeholder_summary(doc):
	"""Short, PII-light summary line for the intake."""
	bits = []
	if doc.source_channel:
		bits.append(doc.source_channel)
	if doc.direction:
		bits.append(doc.direction)
	if doc.organization_name:
		bits.append(f"org={doc.organization_name}")
	channel = ", ".join(bits) or "interaction"
	return f"Auto-staged {channel}. Awaiting qualification."
