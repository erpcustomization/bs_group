"""Draft quotations may differ from their DCS; only an aligned, authorised one is issued.

* Draft save keeps identity, currency, valid-data and cancelled/superseded checks,
  records the server-derived differences and never blocks a commercial change.
* Submit, Sales Order conversion, ``Sent``, emailing and customer print of a draft
  require the strict position (``quotation_control.validate_position``) and the
  existing commercial authority (``commercial_authority.authorised_position``).
* Nothing here returns cost, margin or internal rows (resources, internal
  expenses); DCS selling figures are returned only to users who may read them.
"""
import frappe
from frappe.utils import cint, flt

from bsgroup.dcs import quote_alignment_core as core

INTERNAL_PREVIEW_FORMATS = ("Standard", "Enterprise Quotation format 2", "EnterPrise Quotation 3", "Proposal - UAE")


def row_token(row):
	return row.get("source_key") or row.name


def sheet_selling(sheet):
	return flt(sheet.custom_working_total_selling) if cint(sheet.custom_dcs_revision_no) else flt(sheet.total_selling)


def sheet_view(sheet):
	currency = sheet.currency or frappe.db.get_value("Company", sheet.company, "default_currency")
	rows, internal = [], []
	for r in sheet.get("items") or []:
		rows.append({"token": row_token(r), "aliases": [r.name], "kind": "item", "item_code": r.item_code,
			"qty": flt(r.qty), "selling_rate": flt(r.selling_rate), "selling_amount": flt(r.qty) * flt(r.selling_rate),
			"label": r.get("item_name") or r.item_code})
	for r in sheet.get("addtional_charges") or []:
		if flt(r.get("selling_amount")) > 0:
			rows.append({"token": row_token(r), "aliases": [r.name], "kind": "charge",
				"item_code": None, "qty": 1, "selling_rate": flt(r.selling_amount), "selling_amount": flt(r.selling_amount),
				"label": r.get("charges_type") or "Additional charge"})
		else:
			# Cost-only internal expense: never quoted, never mapped.
			internal += [row_token(r), r.name]
	return {
		"currency": currency, "revision_reference": sheet.get("custom_revision_reference"),
		"docstatus": sheet.docstatus, "superseded": bool(sheet.get("custom_superseded_by")),
		"selling_total": sheet_selling(sheet), "rows": rows, "internal_tokens": internal,
		"additional_item": frappe.db.get_single_value("BS Group Settings", "dcs_addtional_item"),
	}


def quote_view(quotation):
	lines = []
	for r in quotation.get("items") or []:
		lines.append({"idx": r.idx, "item_code": r.item_code, "qty": r.qty,
			"stock_qty": flt(r.qty) * (flt(r.get("conversion_factor")) or 1), "rate": r.rate, "amount": r.amount,
			"price_list_rate": r.get("price_list_rate"), "discount_percentage": r.get("discount_percentage"),
			"discount_amount": r.get("discount_amount"), "sources": r.get("custom_dcs_source_rows")})
	net = quotation.get("net_total")
	if net is None:
		net = sum(flt(r.amount) for r in quotation.get("items") or [])
	return {
		"currency": quotation.get("currency"), "revision_reference": quotation.get("custom_dcs_revision_reference"),
		"net_total": net, "total": quotation.get("total"), "discount_amount": quotation.get("discount_amount"),
		"additional_discount_percentage": quotation.get("additional_discount_percentage"),
		"taxes": [{"charge_type": t.charge_type, "rate": t.rate, "tax_amount": t.get("tax_amount")} for t in quotation.get("taxes") or []],
		"lines": lines,
	}


def analyse(sheet, quotation):
	return core.analyse(sheet_view(sheet), quote_view(quotation))


def authority_problem(sheet):
	"""The existing commercial authority, applied at issue. Revision-zero legacy sheets keep prior behaviour."""
	if not cint(sheet.get("custom_dcs_revision_no")):
		return ""
	from bsgroup.dcs.commercial_authority import authorised_position
	if authorised_position(sheet):
		return ""
	state = sheet.get("custom_approval_state") or ""
	if state in ("Rejected", "Returned for Rework"):
		return "The current DCS position was " + state.lower() + ". A new commercial revision and fresh approval are required before issue."
	if sheet.get("custom_approval_required") == "Blocked" or state == "Blocked":
		return "The current DCS position is blocked and cannot be authorised."
	return "The current DCS position requires recorded commercial approval on its current revision before issue."


def validate_identity(sheet, quotation):
	"""Checks that hold for drafts: wrong deal, company, party, currency or a dead sheet never saves."""
	from bsgroup.bs_group.doctype.deal_cost_sheet.deal_cost_sheet import quotation_deal_identity
	from bsgroup.dcs.input_validation import validate_position as validate_commercial_inputs
	validate_commercial_inputs(sheet)
	if sheet.docstatus == 2:
		frappe.throw("This quotation refers to a cancelled Deal Cost Sheet. Link it to the current sheet.")
	if sheet.docstatus != 1:
		frappe.throw("This quotation refers to an unsubmitted Deal Cost Sheet.")
	if sheet.get("custom_superseded_by"):
		frappe.throw(f"This quotation refers to a superseded Deal Cost Sheet. Link it to {sheet.custom_superseded_by}.")
	currency = sheet.currency or frappe.db.get_value("Company", sheet.company, "default_currency")
	if currency and quotation.currency != currency:
		frappe.throw("Quotation currency differs from the Deal Cost Sheet.")
	why = quotation_deal_identity(sheet, quotation)
	if why:
		frappe.throw("Quotation identity does not match its Deal Cost Sheet: " + why)
	if quotation.get("custom_dcs_superseded_revision"):
		frappe.throw("This quotation is superseded. Create a replacement quotation for the current DCS revision.")
	for row in quotation.get("items") or []:
		for field in ("qty", "rate", "price_list_rate", "discount_percentage", "discount_amount", "conversion_factor"):
			if not core.finite(row.get(field)):
				frappe.throw(f"Row {row.idx}: {field.replace('_', ' ')} must be a finite number.")
		if flt(row.qty) <= 0 or flt(row.rate) < 0:
			frappe.throw(f"Row {row.idx}: quantity must be positive and rate non-negative on a DCS quotation.")
		for token in core.parse_sources(row.get("custom_dcs_source_rows")):
			if len(token) > 140 or not token.replace("-", "").replace("_", "").isalnum():
				frappe.throw(f"Row {row.idx}: DCS source reference '{frappe.utils.escape_html(token)}' is malformed.")
	for field in ("discount_amount", "additional_discount_percentage", "net_total", "total"):
		if not core.finite(quotation.get(field)):
			frappe.throw(f"Quotation {field.replace('_', ' ')} must be a finite number.")


def validate_draft(sheet, quotation):
	validate_identity(sheet, quotation)
	quotation.custom_dcs_revision_reference = sheet.custom_revision_reference
	result = analyse(sheet, quotation)
	if quotation.meta.has_field("custom_dcs_alignment"):
		quotation.custom_dcs_alignment = ", ".join(result["labels"])[:140]
	return result


def issue_message(result):
	"""Strict-gate wording; keeps the established phrases that operators and tests rely on."""
	parts = []
	if {"repriced", "scope_changed"} & set(result["states"]):
		parts.append("Quotation scope or selling rates differ from the current DCS BOQ.")
	if "total_changed" in result["states"]:
		parts.append("Quotation selling total differs from the current DCS position.")
	if "stale" in result["states"]:
		parts.append("Quotation is stale against the current DCS revision.")
	return " ".join(parts + [i["message"] for i in result["issues"]])


def issue_problems(sheet, quotation, result=None):
	result = result or analyse(sheet, quotation)
	problems = [] if result["issuable"] else [core.headline(result)] + [i["message"] for i in result["issues"]]
	why = authority_problem(sheet)
	if why:
		problems.append(why)
	return problems


def assert_issue_authority(sheet):
	why = authority_problem(sheet)
	if why:
		frappe.throw(why, title="Quotation cannot be issued")


def _can_read_selling(sheet):
	try:
		return frappe.has_permission("Deal Cost Sheet", "read", doc=sheet) and 1 in sheet.get_permlevel_access("read")
	except Exception:
		return False


def _load(quotation, ptype):
	doc = frappe.get_doc("Quotation", quotation)
	doc.check_permission(ptype)
	if not doc.get("custom_deal_cost_sheet"):
		frappe.throw("This quotation is not linked to a Deal Cost Sheet.")
	return doc, frappe.get_doc("Deal Cost Sheet", doc.custom_deal_cost_sheet)


@frappe.whitelist()
def alignment_summary(quotation):
	"""Banner payload. Selling-side only; DCS figures need DCS selling read access."""
	doc, sheet = _load(quotation, "read")
	result = analyse(sheet, doc)
	problems = issue_problems(sheet, doc, result)
	figures = _can_read_selling(sheet)
	approved = None
	if figures and sheet.get("custom_approval_state") == "Approved" and sheet.get("custom_approved_total_selling"):
		approved = {"selling": flt(sheet.custom_approved_total_selling),
			"current_revision": cint(sheet.custom_approved_revision_no) == cint(sheet.custom_dcs_revision_no)}
	actions = []
	if (not result["mapped"] and "scope_changed" in result["states"]) or result["unknown"] or result["uncovered"] or result["duplicates"]:
		actions.append("map_rows")
	if {"repriced", "total_changed"} & set(result["states"]):
		actions.append("request_revision")
	if "stale" in result["states"]:
		actions.append("regenerate")
	if authority_problem(sheet):
		actions.append("obtain_approval")
	lines = [{k: l.get(k) for k in ("idx", "sources", "status")} | (
		{"expected_amount": l.get("expected_amount"), "actual_amount": l.get("actual_amount")} if figures else {})
		for l in result["lines"]]
	return {
		"states": result["states"], "labels": result["labels"], "issuable": not problems,
		"headline": core.headline(result), "problems": problems, "actions": actions,
		"mapped": result["mapped"], "lines": lines, "docstatus": doc.docstatus,
		"uncovered": len(result["uncovered"]), "unknown": result["unknown"], "duplicates": result["duplicates"],
		"currency": result["currency"], "quote_net": result["quote_net"],
		"dcs_selling": result["dcs_selling"] if figures else None,
		"variance": result["variance"] if figures else None,
		"approved": approved, "approval_state": sheet.get("custom_approval_state"),
		"dcs": sheet.name, "dcs_revision": sheet.get("custom_revision_reference"),
		"quote_revision": doc.get("custom_dcs_revision_reference"),
	}


@frappe.whitelist()
def source_rows(quotation):
	"""Quotable DCS rows for the mapping dialog. Never returns cost, margin, resources or internal expenses."""
	doc, sheet = _load(quotation, "write")
	view = sheet_view(sheet)
	figures = _can_read_selling(sheet)
	rows = [{"token": r["token"], "kind": r["kind"], "item_code": r["item_code"], "label": r["label"],
		"qty": r["qty"]} | ({"selling_amount": r["selling_amount"]} if figures else {}) for r in view["rows"]]
	return {"rows": rows, "suggestions": core.suggest(view, quote_view(doc)), "additional_item": view["additional_item"]}


# ---------------------------------------------------------------- issue paths

def guard_issue_stage(doc, method=None):
	"""``Sent`` / ``Follow-up`` claim the offer reached the customer; a draft must be issuable first."""
	if doc.docstatus != 0 or not doc.get("custom_deal_cost_sheet"):
		return
	if doc.get("custom_pipeline_stage") not in ("Sent", "Follow-up"):
		return
	previous = None if doc.is_new() else doc.get_doc_before_save()
	if previous and previous.get("custom_pipeline_stage") in ("Sent", "Follow-up"):
		return  # only the move into Sent is a claim of issue; existing records keep saving
	sheet = frappe.get_doc("Deal Cost Sheet", doc.custom_deal_cost_sheet)
	problems = issue_problems(sheet, doc)
	if problems:
		frappe.throw("A draft that differs from its approved DCS position cannot be marked "
			+ doc.custom_pipeline_stage + ". " + " ".join(problems), title="Not issuable")


def _print_format_name():
	fd = frappe.form_dict or {}
	return fd.get("format") or fd.get("print_format") or ""


def before_print(doc, method=None, settings=None):
	"""Customer output of an unaligned or unauthorised DCS quotation is marked or refused.

	Every print path (print view, PDF download, email attachment via
	``frappe.attach_print``) renders through ``get_rendered_html`` which runs
	``before_print``. Interactive previews of a draft stay available with the
	formats' "NOT FOR CUSTOMER ISSUE" notice; attaching it to an email is refused.
	"""
	if doc.docstatus == 2 or not doc.get("custom_deal_cost_sheet"):
		return
	if not frappe.db.exists("Deal Cost Sheet", doc.custom_deal_cost_sheet):
		return
	sheet = frappe.get_doc("Deal Cost Sheet", doc.custom_deal_cost_sheet)
	if doc.docstatus == 1:
		# Issued under the strict gate; only later supersession is reported.
		if not (doc.get("custom_dcs_superseded_revision") or sheet.get("custom_superseded_by") or sheet.docstatus == 2):
			return
		problems = ["This quotation has been superseded by a later DCS revision."]
	else:
		problems = issue_problems(sheet, doc)
	if not problems:
		return
	doc.flags.dcs_issue_block = " ".join(problems)
	if frappe.flags.ignore_print_permissions and doc.docstatus == 0:
		frappe.throw("This draft quotation differs from its approved DCS position and cannot be attached to an email "
			"or issued: " + " ".join(problems), title="Not for customer issue")
	fmt = _print_format_name()
	if doc.docstatus == 0 and fmt and fmt not in INTERNAL_PREVIEW_FORMATS:
		frappe.throw(f"Print format {frappe.utils.escape_html(fmt)} does not mark drafts as not for customer issue. "
			"Use an internal preview format, or align and submit the quotation first.", title="Not for customer issue")


# ---------------------------------------------------------------- prepared vs issued

def issued_quotation(dcs):
	return frappe.db.get_value("Quotation", {"custom_deal_cost_sheet": dcs, "docstatus": 1,
		"custom_dcs_superseded_revision": ["is", "not set"]}, "name")


def sync_quote_status(doc, method=None):
	"""Runs on ``on_change``, after the After-Save link-back Server Script.

	A saved draft is *prepared*: the sheet keeps its link to the draft but its
	deal status stays "Submitted to Sales". Only a submitted (issued) quotation
	makes the deal "Quoted"; cancelling the last issued one returns it.
	"""
	dcs = doc.get("custom_deal_cost_sheet")
	if not dcs or not frappe.db.exists("Deal Cost Sheet", dcs):
		return
	sheet = frappe.db.get_value("Deal Cost Sheet", dcs, ["custom_deal_status", "docstatus", "presales_request"], as_dict=True)
	issued = issued_quotation(dcs)
	if sheet.custom_deal_status == "Quoted" and not issued and sheet.docstatus == 1:
		frappe.db.set_value("Deal Cost Sheet", dcs, "custom_deal_status", "Submitted to Sales", update_modified=False)
		target = "Submitted to Sales"
	elif sheet.custom_deal_status == "Submitted to Sales" and issued:
		frappe.db.set_value("Deal Cost Sheet", dcs, "custom_deal_status", "Quoted", update_modified=False)
		target = "Quoted"
	else:
		return
	pr = sheet.presales_request
	if pr and frappe.get_meta("Presales Request").has_field("custom_deal_status"):
		current = frappe.db.get_value("Presales Request", pr, "custom_deal_status")
		if current in ("Quoted", "Submitted to Sales") and current != target:
			frappe.db.set_value("Presales Request", pr, "custom_deal_status", target, update_modified=False)
