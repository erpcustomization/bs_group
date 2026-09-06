# Copyright (c) 2026, Tridots Tech and contributors
# For license information, please see license.txt

"""3CX (and generic external system) integration endpoints.

Every write endpoint:
  * authenticates through normal Frappe API auth and rejects ``Guest``;
  * restricts the HTTP method and validates payload sizes;
  * creates or updates a :class:`Lead Intake` **idempotently** keyed on
    ``external_system`` + ``external_interaction_id``;
  * returns a stable JSON envelope;
  * writes a redacted Integration Request log (no transcript / PII).

Business writes rely on the *calling API user's* permissions — we never use
``ignore_permissions`` for the Lead Intake itself. Only the infrastructure log
is written with elevated rights.
"""

import frappe
from frappe import _
from frappe.rate_limiter import rate_limit
from frappe.utils import get_datetime

from bsgroup.bs_group.doctype.lead_intake.lead_intake import (
	enqueue_ai_processing,
	normalize_email,
	normalize_phone,
	payload_hash,
)

# --- limits ----------------------------------------------------------------

MAX_TRANSCRIPT_CHARS = 100_000
MAX_TEXT_CHARS = 2_000
MAX_PAYLOAD_BYTES = 512 * 1024  # 512 KB overall guard on a single request

DEFAULT_SYSTEM = "3CX"


# ===========================================================================
# Public endpoints
# ===========================================================================


@frappe.whitelist(methods=["GET", "POST"])
@rate_limit(key="phone", limit=120, seconds=60)
def lookup(phone=None, email=None):
	"""Look up existing CRM records by phone/email. Read-only, no writes.

	Returns a stable envelope describing any matching Lead / Contact / prior
	Lead Intake so 3CX can screen-pop or de-dupe before journaling.
	"""
	_reject_guest()

	if not (phone or email):
		frappe.throw(_("Provide at least one of: phone, email."), frappe.ValidationError)

	norm_phone = normalize_phone(phone)
	norm_email = normalize_email(email)

	from bsgroup.bs_group.doctype.lead_intake.lead_intake import (
		find_matching_contact,
		find_matching_lead,
	)

	lead = find_matching_lead(norm_phone, norm_email)
	contact = find_matching_contact(norm_phone, norm_email)

	intake = frappe.get_all(
		"Lead Intake",
		or_filters=_identity_or_filters(norm_phone, norm_email),
		filters={"status": ["not in", ("Disqualified", "Duplicate")]},
		fields=["name", "status", "full_name", "converted_lead"],
		order_by="creation desc",
		limit=1,
	)

	return {
		"ok": True,
		"normalized_phone": norm_phone,
		"normalized_email": norm_email,
		"matched": bool(lead or contact or intake),
		"lead": lead,
		"contact": contact,
		"lead_intake": intake[0] if intake else None,
	}


@frappe.whitelist(methods=["POST"])
@rate_limit(key="external_interaction_id", limit=60, seconds=60)
def create_contact(
	full_name=None,
	organization_name=None,
	email=None,
	phone=None,
	country=None,
	external_interaction_id=None,
	external_system=DEFAULT_SYSTEM,
	source_channel="API",
	source_detail=None,
	source_url=None,
	request_id=None,
):
	"""Stage a contact captured in 3CX as a Lead Intake (idempotent)."""
	_reject_guest()

	values = _collect(
		full_name=full_name,
		organization_name=organization_name,
		email=email,
		phone=phone,
		country=country,
		source_channel=source_channel,
		source_detail=source_detail,
		source_url=source_url,
	)
	return _upsert(external_system, external_interaction_id, values, request_id, "create_contact")


@frappe.whitelist(methods=["POST"])
@rate_limit(key="external_interaction_id", limit=60, seconds=60)
def chat_journal(
	external_interaction_id=None,
	external_system=DEFAULT_SYSTEM,
	full_name=None,
	organization_name=None,
	email=None,
	phone=None,
	country=None,
	subject=None,
	transcript=None,
	direction="Inbound",
	agent_name=None,
	agent_extension=None,
	interaction_started_on=None,
	interaction_ended_on=None,
	source_channel="Website Chat",
	source_detail=None,
	source_url=None,
	request_id=None,
):
	"""Record a chat/WhatsApp interaction as a Lead Intake (idempotent)."""
	_reject_guest()

	values = _collect(
		full_name=full_name,
		organization_name=organization_name,
		email=email,
		phone=phone,
		country=country,
		subject=subject,
		transcript=transcript,
		direction=_clean_direction(direction),
		agent_name=agent_name,
		agent_extension=agent_extension,
		interaction_started_on=_clean_datetime(interaction_started_on),
		interaction_ended_on=_clean_datetime(interaction_ended_on),
		source_channel=source_channel,
		source_detail=source_detail,
		source_url=source_url,
	)
	return _upsert(external_system, external_interaction_id, values, request_id, "chat_journal")


@frappe.whitelist(methods=["POST"])
@rate_limit(key="external_interaction_id", limit=60, seconds=60)
def call_journal(
	external_interaction_id=None,
	external_system=DEFAULT_SYSTEM,
	full_name=None,
	organization_name=None,
	email=None,
	phone=None,
	country=None,
	subject=None,
	transcript=None,
	direction="Inbound",
	agent_name=None,
	agent_extension=None,
	interaction_started_on=None,
	interaction_ended_on=None,
	source_channel="Call",
	source_detail=None,
	source_url=None,
	request_id=None,
):
	"""Record a phone call interaction as a Lead Intake (idempotent)."""
	_reject_guest()

	values = _collect(
		full_name=full_name,
		organization_name=organization_name,
		email=email,
		phone=phone,
		country=country,
		subject=subject,
		transcript=transcript,
		direction=_clean_direction(direction),
		agent_name=agent_name,
		agent_extension=agent_extension,
		interaction_started_on=_clean_datetime(interaction_started_on),
		interaction_ended_on=_clean_datetime(interaction_ended_on),
		source_channel=source_channel,
		source_detail=source_detail,
		source_url=source_url,
	)
	return _upsert(external_system, external_interaction_id, values, request_id, "call_journal")


@frappe.whitelist(methods=["GET", "POST"])
@rate_limit(key="external_interaction_id", limit=120, seconds=60)
def get_intake_status(external_interaction_id, external_system=DEFAULT_SYSTEM):
	"""Return the processing status of a previously journaled interaction."""
	_reject_guest()

	if not external_interaction_id:
		frappe.throw(_("external_interaction_id is required."), frappe.ValidationError)

	key = f"{(external_system or DEFAULT_SYSTEM).strip()}:{str(external_interaction_id).strip()}"
	name = frappe.db.get_value("Lead Intake", {"idempotency_key": key}, "name")
	if not name:
		return {"ok": True, "found": False, "idempotency_key": key}

	# get_doc runs the read permission check for the calling user.
	doc = frappe.get_doc("Lead Intake", name)
	doc.check_permission("read")
	return {
		"ok": True,
		"found": True,
		"intake": doc.name,
		"status": doc.status,
		"ai_status": doc.ai_status,
		"ai_qualification": doc.ai_qualification,
		"converted_lead": doc.converted_lead,
		"duplicate_of": doc.duplicate_of,
		"matched_lead": doc.matched_lead,
	}


# ===========================================================================
# Internal helpers
# ===========================================================================


def _reject_guest():
	if frappe.session.user == "Guest":
		frappe.throw(_("Authentication required."), frappe.PermissionError)


def _identity_or_filters(norm_phone, norm_email):
	or_filters = []
	if norm_phone:
		or_filters.append(["normalized_phone", "=", norm_phone])
	if norm_email:
		or_filters.append(["normalized_email", "=", norm_email])
	# Guard against an all-empty filter selecting every row.
	return or_filters or [["name", "=", "__none__"]]


def _clean_direction(direction):
	if direction in ("Inbound", "Outbound", "Unknown"):
		return direction
	return "Unknown"


def _clean_datetime(value):
	if not value:
		return None
	try:
		return get_datetime(value)
	except (ValueError, TypeError):
		return None


def _collect(**kwargs):
	"""Trim, size-validate and drop empty values from caller input."""
	values = {}
	for field, value in kwargs.items():
		if value is None:
			continue
		text = str(value).strip()
		if not text:
			continue
		limit = MAX_TRANSCRIPT_CHARS if field == "transcript" else MAX_TEXT_CHARS
		if len(text) > limit:
			frappe.throw(
				_("Field '{0}' exceeds the maximum length of {1} characters.").format(field, limit),
				frappe.ValidationError,
			)
		values[field] = value if field in ("interaction_started_on", "interaction_ended_on") else text
	return values


def _upsert(external_system, external_interaction_id, values, request_id, endpoint):
	"""Idempotent create-or-update of a Lead Intake, keyed on external ids."""
	external_system = (external_system or DEFAULT_SYSTEM).strip()
	external_interaction_id = str(external_interaction_id).strip() if external_interaction_id else None

	if not external_interaction_id:
		frappe.throw(_("external_interaction_id is required."), frappe.ValidationError)

	raw_payload = dict(
		values, external_system=external_system, external_interaction_id=external_interaction_id
	)
	_validate_payload_size(raw_payload)

	key = f"{external_system}:{external_interaction_id}"
	digest = payload_hash(raw_payload)

	existing = frappe.db.get_value("Lead Intake", {"idempotency_key": key}, "name")
	created = False
	try:
		if existing:
			doc = _apply_update(existing, values, request_id, digest, raw_payload)
		else:
			doc = _apply_create(
				external_system, external_interaction_id, values, request_id, digest, raw_payload
			)
			created = True
	except frappe.exceptions.DuplicateEntryError:
		# Lost an insert race — the other writer won; fold our data into theirs.
		frappe.db.rollback()
		existing = frappe.db.get_value("Lead Intake", {"idempotency_key": key}, "name")
		doc = _apply_update(existing, values, request_id, digest, raw_payload)

	if created or doc.ai_status in (None, "Pending"):
		enqueue_ai_processing(doc.name)

	_log_integration(endpoint, "Completed", doc, request_id, created)

	return {
		"ok": True,
		"created": created,
		"intake": doc.name,
		"idempotency_key": key,
		"status": doc.status,
		"ai_status": doc.ai_status,
		"duplicate_of": doc.duplicate_of,
		"matched_lead": doc.matched_lead,
		"matched_contact": doc.matched_contact,
	}


def _apply_create(external_system, external_interaction_id, values, request_id, digest, raw_payload):
	doc = frappe.new_doc("Lead Intake")
	doc.external_system = external_system
	doc.external_interaction_id = external_interaction_id
	for field, value in values.items():
		doc.set(field, value)
	doc.request_id = request_id
	doc.payload_hash = digest
	doc.raw_payload_json = frappe.as_json(raw_payload)
	doc.insert()  # honours the calling user's create permission
	return doc


def _apply_update(name, values, request_id, digest, raw_payload):
	doc = frappe.get_doc("Lead Intake", name)
	# Unchanged re-delivery: nothing to do, stay idempotent.
	if doc.payload_hash == digest:
		return doc

	for field, value in values.items():
		# Never blank an existing value with an omitted field.
		if value not in (None, ""):
			doc.set(field, value)
	if request_id:
		doc.request_id = request_id
	doc.payload_hash = digest
	doc.raw_payload_json = frappe.as_json(raw_payload)
	doc.save()  # honours the calling user's write permission
	return doc


def _validate_payload_size(raw_payload):
	size = len(frappe.as_json(raw_payload).encode("utf-8"))
	if size > MAX_PAYLOAD_BYTES:
		frappe.throw(
			_("Payload too large: {0} bytes (max {1}).").format(size, MAX_PAYLOAD_BYTES),
			frappe.ValidationError,
		)


def _log_integration(endpoint, status, doc, request_id, created):
	"""Write a redacted Integration Request. Never raises into the caller.

	Deliberately excludes transcript, subject, name, email and phone so logs
	are safe to retain and share. Written with elevated rights because logging
	is infrastructure, not business data governed by the API user's roles.
	"""
	try:
		safe = {
			"endpoint": endpoint,
			"external_system": doc.external_system,
			"external_interaction_id": doc.external_interaction_id,
			"request_id": request_id,
			"source_channel": doc.source_channel,
			"created": created,
			"has_email": bool(doc.normalized_email),
			"has_phone": bool(doc.normalized_phone),
			"transcript_chars": len(doc.transcript or ""),
			"intake": doc.name,
			"status": doc.status,
		}
		log = frappe.new_doc("Integration Request")
		log.integration_request_service = f"3CX Lead Intake:{endpoint}"
		log.status = status
		log.request_description = f"3CX {endpoint}"
		log.data = frappe.as_json(safe)
		log.reference_doctype = "Lead Intake"
		log.reference_docname = doc.name
		log.flags.ignore_permissions = True
		log.insert(ignore_permissions=True)
	except Exception:
		# Logging must never break the integration write.
		frappe.log_error(title="Lead Intake integration log failed", message=frappe.get_traceback())
