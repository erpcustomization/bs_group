"""Draft quotations may differ from their DCS; only an aligned, authorised one is issued.

* Draft save keeps identity, currency, valid-data and cancelled/superseded checks,
  records the server-derived differences and never blocks a commercial change.
  A DCS revision made after the draft was prepared stays visible ("Stale") until
  someone explicitly reviews it (``review_revision``); an unrelated save never
  acknowledges it.
* Submit, Sales Order conversion, ``Sent`` / ``Follow-up`` and email require the
  strict position (``quotation_control.validate_position``) and the existing
  commercial authority (``commercial_authority.authorised_position``, or the same
  policy for an initial revision-0 position).
* Legacy treatment needs server-owned evidence (``custom_dcs_legacy_basis``, set
  only by the migration for quotations already submitted before row mapping). An
  empty mapping is never evidence.
* Customer output (print view, PDF, email attachment) of a quotation that is not
  issuable is either visibly marked "NOT FOR CUSTOMER ISSUE" in the rendered
  body, or refused where the rendering path cannot be marked.
* Nothing here returns cost, margin or internal rows (resources, internal
  expenses); DCS selling figures are returned only to users who may read them.
"""
import re

import frappe
from frappe.utils import cint, flt

from bsgroup.dcs import quote_alignment_core as core

SELF_PDF_BODY_HOOK = "bsgroup.dcs.quote_alignment.pdf_body_html"
ISSUED_STAGES = ("Sent", "Follow-up", "Won", "Lost", "Expired")
ISSUE_CLAIM_STAGES = ("Sent", "Follow-up")
# Fields that must never reach a customer document from a DCS quotation, whatever the template.
CONFIDENTIAL_TEMPLATE = re.compile(
	r"\b(custom_cost_rate|custom_gp|cost_rate|cost_amount|gp_value|gp_percent|margin_value|margin_percent|"
	r"total_cost|valuation_rate|incoming_rate|gross_profit|addtional_charges|total_resource_cost)\b"
	r"|Deal Cost (Sheet|Item)|DCS Revision|Deal Cost Resource", re.IGNORECASE)


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
			"position": r.idx, "text": frappe.utils.strip_html_tags(r.get("description") or "")
				or r.get("customer_item_name") or r.get("item_name") or r.item_code})
	for r in sheet.get("addtional_charges") or []:
		if flt(r.get("selling_amount")) > 0:
			# The charge type is the customer-facing category; the internal note is never shown.
			rows.append({"token": row_token(r), "aliases": [r.name], "kind": "charge",
				"item_code": None, "qty": 1, "selling_rate": flt(r.selling_amount), "selling_amount": flt(r.selling_amount),
				"position": r.idx, "text": r.get("charges_type") or "Additional charge"})
		else:
			# Cost-only internal expense: never quoted, never mapped.
			internal += [row_token(r), r.name]
	return {
		"currency": currency, "revision_reference": sheet.get("custom_revision_reference"),
		"docstatus": sheet.docstatus, "superseded": bool(sheet.get("custom_superseded_by")),
		"selling_total": sheet_selling(sheet), "rows": rows, "internal_tokens": internal,
		"additional_item": frappe.db.get_single_value("BS Group Settings", "dcs_addtional_item"),
	}


def legacy_evidence(quotation):
	"""Server-owned: only a quotation the migration found already submitted without mapping."""
	return bool(quotation.docstatus == 1 and getattr(quotation, "_action", None) != "submit"
		and quotation.get("custom_dcs_legacy_basis")
		and not any(r.get("custom_dcs_source_rows") for r in quotation.get("items") or []))


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
		"lines": lines, "legacy_evidence": legacy_evidence(quotation),
	}


def analyse(sheet, quotation):
	return core.analyse(sheet_view(sheet), quote_view(quotation))


# ---------------------------------------------------------------- authority

def authority_problem(sheet):
	"""The existing commercial authority, applied at issue. "" when authorised."""
	from bsgroup.dcs.input_validation import position_is_valid
	if not position_is_valid(sheet):
		return "The DCS holds invalid commercial figures and cannot be issued."
	if not cint(sheet.get("custom_dcs_revision_no")):
		return _initial_authority(sheet)
	from bsgroup.dcs.commercial_authority import authorised_position
	if authorised_position(sheet):
		return ""
	state = sheet.get("custom_approval_state") or ""
	if state in ("Rejected", "Returned for Rework"):
		return "The current DCS position was " + state.lower() + ". A new commercial revision and fresh approval are required before issue."
	if sheet.get("custom_approval_required") == "Blocked" or state == "Blocked":
		return "The current DCS position is blocked and cannot be authorised."
	return "The current DCS position requires recorded commercial approval on its current revision before issue."


def _initial_authority(sheet):
	"""Revision 0 (no living position yet): the same policy on the sheet's own totals, no exemption."""
	from bsgroup.api.dcs.negotiation import pct, requirement
	from bsgroup.dcs.currency import money_tolerance
	cost, selling = flt(sheet.total_cost), flt(sheet.total_selling)
	required_now = requirement(0, pct(selling - cost, selling)) if selling > 0 else "None"
	tol = money_tolerance(sheet.currency)
	matches = bool(sheet.get("custom_approved_by")
		and abs(flt(sheet.get("custom_approved_total_selling")) - selling) <= tol
		and abs(flt(sheet.get("custom_approved_total_cost")) - cost) <= tol)
	return core.initial_authority(sheet.get("custom_approval_state"), sheet.get("custom_approval_required"),
		required_now, selling, approval_matches=matches)


def assert_issue_authority(sheet):
	why = authority_problem(sheet)
	if why:
		frappe.throw(why, title="Quotation cannot be issued")


# ---------------------------------------------------------------- draft save

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
	# Legacy evidence belongs to the migration only; a draft (or a copy, amendment or API
	# payload) can never carry it into issue.
	if quotation.meta.has_field("custom_dcs_legacy_basis"):
		quotation.custom_dcs_legacy_basis = None
	# The revision a draft was prepared against is kept until it is explicitly reviewed, so a
	# later DCS revision is shown as Stale and is never acknowledged by an unrelated save.
	if not quotation.get("custom_dcs_revision_reference"):
		quotation.custom_dcs_revision_reference = sheet.custom_revision_reference
	result = analyse(sheet, quotation)
	if quotation.meta.has_field("custom_dcs_alignment"):
		quotation.custom_dcs_alignment = ", ".join(result["labels"])[:140]
	return result


@frappe.whitelist(methods=["POST"])
def review_revision(quotation):
	"""Explicit review of a later DCS revision: re-validates the draft against it and records who reviewed it."""
	doc, sheet = _load(quotation, "write")
	if doc.docstatus != 0:
		frappe.throw("Only a draft quotation can be reviewed against a new DCS revision.")
	previous = doc.get("custom_dcs_revision_reference")
	current = sheet.get("custom_revision_reference")
	if previous == current:
		return {"changed": 0, "revision": current}
	# Re-validate the draft against the reviewed revision, then record only the review itself:
	# no other unsaved change is saved and unrelated mandatory fields are left to the form.
	doc.custom_dcs_revision_reference = current
	validate_draft(sheet, doc)
	doc.db_set({"custom_dcs_revision_reference": current, "custom_dcs_alignment": doc.get("custom_dcs_alignment")})
	doc.add_comment("Info", f"DCS revision reviewed by {frappe.session.user}: {previous or 'none'} to {current}. "
		f"Alignment after review: {doc.get('custom_dcs_alignment') or 'n/a'}.")
	return {"changed": 1, "previous": previous, "revision": current, "alignment": doc.get("custom_dcs_alignment")}


# ---------------------------------------------------------------- issue

def issue_message(result):
	"""Strict-gate wording; keeps the established phrases that operators and tests rely on."""
	parts = []
	if {"repriced", "scope_changed"} & set(result["states"]):
		parts.append("Quotation scope or selling rates differ from the current DCS BOQ.")
	if "total_changed" in result["states"]:
		parts.append("Quotation selling total differs from the current DCS position.")
	if "stale" in result["states"]:
		parts.append("Quotation is stale against the current DCS revision; review the revision first.")
	return " ".join(parts + [i["message"] for i in result["issues"]])


def issue_problems(sheet, quotation, result=None):
	"""Everything that stops this quotation being a valid customer offer now, for drafts and submitted ones."""
	problems = []
	if quotation.get("custom_dcs_superseded_revision"):
		problems.append("This quotation has been superseded by a later DCS revision.")
	result = result or analyse(sheet, quotation)
	if not result["issuable"]:
		problems += [core.headline(result)] + [i["message"] for i in result["issues"]]
	why = authority_problem(sheet)
	if why:
		problems.append(why)
	return problems


def output_problems(doc):
	"""Problems for customer output of ``doc``; [] for non-DCS, cancelled or issuable quotations."""
	if doc.doctype != "Quotation" or doc.docstatus == 2 or not doc.get("custom_deal_cost_sheet"):
		return []
	if not frappe.db.exists("Deal Cost Sheet", doc.custom_deal_cost_sheet):
		return ["The linked Deal Cost Sheet no longer exists."]
	if doc.flags.get("dcs_issue_problems") is not None:
		return doc.flags.dcs_issue_problems
	sheet = frappe.get_doc("Deal Cost Sheet", doc.custom_deal_cost_sheet)
	problems = issue_problems(sheet, doc)
	doc.flags.dcs_issue_problems = problems
	return problems


def guard_issue_stage(doc, method=None):
	"""``Sent`` / ``Follow-up`` record that the offer reached the customer.

	For a DCS quotation the offer must first be submitted (approved and ready), and must
	still be issuable when it is marked. Only the move into these stages is checked, so
	existing records already at Sent keep saving.
	"""
	if not doc.get("custom_deal_cost_sheet") or doc.docstatus == 2:
		return
	if doc.get("custom_pipeline_stage") not in ISSUE_CLAIM_STAGES:
		return
	previous = None if doc.is_new() else doc.get_doc_before_save()
	if previous and previous.get("custom_pipeline_stage") in ISSUE_CLAIM_STAGES:
		return
	if doc.docstatus == 0:
		frappe.throw("Submit the quotation before marking it " + doc.custom_pipeline_stage
			+ ": a DCS quotation is issued only once it is approved and submitted.", title="Not issued")
	doc.flags.dcs_issue_problems = None
	problems = output_problems(doc)
	if problems:
		frappe.throw("This quotation cannot be marked " + doc.custom_pipeline_stage + ". " + " ".join(problems),
			title="Not issuable")


# ---------------------------------------------------------------- customer output

def before_print(doc, method=None, settings=None):
	"""Computes the issue problems once per render; templates read ``doc.flags.dcs_issue_block``."""
	doc.flags.dcs_issue_problems = None
	problems = output_problems(doc)
	doc.flags.dcs_issue_block = " ".join(problems) if problems else None
	if problems and frappe.get_hooks("pdf_body_html")[-1:] != [SELF_PDF_BODY_HOOK]:
		# Another app's renderer runs last, so the body cannot be marked reliably.
		frappe.throw("This quotation is not approved for customer issue and cannot be printed on this site "
			"configuration: " + " ".join(problems), title="Not for customer issue")


def _template_text(print_format):
	if not print_format:
		return ""
	parts = [print_format.get(f) or "" for f in ("html", "format_data", "print_designer_body", "print_designer_header",
		"print_designer_footer", "print_designer_after_table", "print_designer_print_format", "print_designer_settings")]
	if not parts[0] and print_format.get("standard") == "Yes" and not print_format.get("format_data"):
		from frappe.www.printview import get_print_format
		try:
			parts.append(get_print_format(print_format.doc_type, print_format) or "")
		except Exception:
			pass
	return "\n".join(str(p) for p in parts)


def assert_confidential_template(print_format):
	"""A DCS quotation is never rendered by a template that names cost, margin or DCS internals."""
	match = CONFIDENTIAL_TEMPLATE.search(_template_text(print_format))
	if match:
		frappe.throw(f"Print format {frappe.utils.escape_html(print_format.name)} references internal commercial data "
			f"({frappe.utils.escape_html(match.group(0))}) and cannot print a DCS quotation.", title="Confidential data")


MARK = ('<div class="dcs-not-for-issue" style="border:3px solid #b91c1c;color:#b91c1c;background:#fff;'
	'font:700 13px Arial,Helvetica,sans-serif;padding:8px 10px;margin:0 0 8px 0;text-align:center;">'
	'NOT FOR CUSTOMER ISSUE &mdash; this quotation is not an approved offer</div>'
	'<div class="dcs-not-for-issue-watermark" style="position:fixed;top:42%;left:0;right:0;text-align:center;'
	'font:700 54px Arial,Helvetica,sans-serif;color:rgba(185,28,28,0.16);transform:rotate(-28deg);'
	'z-index:9999;pointer-events:none;">NOT FOR CUSTOMER ISSUE</div>')


def mark_html(rendered):
	return MARK + (rendered or "")


def pdf_body_html(template=None, args=None, print_format=None, jenv=None, **kwargs):
	"""Wraps the site's body renderer (Frappe or Print Designer) for every non-beta print path.

	Runs after ``before_print`` for print view, PDF download and ``attach_print``. A DCS
	quotation is refused when the template names confidential data; when it is not
	issuable it is refused on system/attachment paths and visibly marked otherwise.
	"""
	args = args or {}
	doc = args.get("doc")
	problems = []
	if doc is not None and getattr(doc, "doctype", None) == "Quotation" and doc.get("custom_deal_cost_sheet") \
			and doc.docstatus != 2:
		assert_confidential_template(print_format)
		problems = output_problems(doc)
		if problems and frappe.flags.ignore_print_permissions:
			frappe.throw("This quotation is not approved for customer issue and cannot be attached or sent: "
				+ " ".join(problems), title="Not for customer issue")
	hooks = [h for h in frappe.get_hooks("pdf_body_html") if h != SELF_PDF_BODY_HOOK]
	rendered = frappe.get_attr(hooks[-1])(template=template, args=args, print_format=print_format, jenv=jenv, **kwargs)
	return mark_html(rendered) if problems else rendered


def _requested_format(doc):
	fd = frappe.form_dict or {}
	return fd.get("format") or fd.get("print_format") or frappe.get_meta(doc.doctype).default_print_format or "Standard"


def unmarkable_format(name):
	"""Print Format Builder (beta) formats render through WeasyPrint, outside ``before_print`` and ``pdf_body_html``."""
	if not name or name == "Standard" or not frappe.db.exists("Print Format", name):
		return False
	return bool(frappe.db.get_value("Print Format", name, "print_format_builder_beta"))


def has_print_permission(doc, ptype=None, user=None, debug=False):
	"""Controller permission for Quotation: only ever narrows ``print`` for an unmarkable format.

	Frappe treats a falsy return as a denial, so every other case returns True.
	"""
	if ptype != "print" or not hasattr(doc, "get") or not doc.get("custom_deal_cost_sheet"):
		return True
	if not unmarkable_format(_requested_format(doc)) or not output_problems(doc):
		return True
	frappe.msgprint("This quotation is not approved for customer issue. Print it with a format that marks it, "
		"or align and submit it first.", title="Not for customer issue", indicator="red")
	return False


def on_print_pdf(doctype=None, name=None, print_format=None, **kwargs):
	"""PDF generation of an unmarkable format is refused for a quotation that is not issuable."""
	if doctype != "Quotation" or not name or not unmarkable_format(print_format):
		return
	doc = frappe.get_doc("Quotation", name)
	problems = output_problems(doc)
	if problems:
		frappe.throw("This quotation is not approved for customer issue: " + " ".join(problems), title="Not for customer issue")


def guard_email(doctype=None, name=None, print_html=None, print_format=None, send_email=False):
	if doctype != "Quotation" or not name or not cint(send_email) or not (print_format or print_html):
		return
	doc = frappe.get_doc("Quotation", name)
	if not doc.get("custom_deal_cost_sheet"):
		return
	if print_html:
		frappe.throw("A DCS quotation is attached only from the server rendering; client HTML cannot be attached.",
			title="Not for customer issue")
	if print_format and print_format != "Standard" and frappe.db.exists("Print Format", print_format):
		assert_confidential_template(frappe.get_doc("Print Format", print_format))
	problems = output_problems(doc)
	if problems:
		frappe.throw("This quotation is not approved for customer issue and cannot be emailed with its print: "
			+ " ".join(problems), title="Not for customer issue")


@frappe.whitelist()
def make_communication(doctype=None, name=None, print_html=None, print_format=None, send_email=False, **kwargs):
	"""Override of ``frappe.core.doctype.communication.email.make``: refuses before any Communication exists."""
	guard_email(doctype, name, print_html, print_format, send_email)
	from frappe.core.doctype.communication.email import make
	return make(doctype=doctype, name=name, print_html=print_html, print_format=print_format,
		send_email=send_email, **kwargs)


# ---------------------------------------------------------------- banner and mapping UI

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
	mapping_codes = {"unmapped", "unknown_source", "duplicate_source", "internal_source"}
	if any(mapping_codes & set(l["status"]) for l in result["lines"]) or result["uncovered"]:
		actions.append("map_rows")
	if {"repriced", "total_changed"} & set(result["states"]):
		actions.append("request_revision")
	if any(i["code"] == "revision_changed" for i in result["issues"]) and doc.docstatus == 0:
		actions.append("review_revision")
	elif "stale" in result["states"]:
		actions.append("regenerate")
	if authority_problem(sheet):
		actions.append("obtain_approval")
	lines = [{k: l.get(k) for k in ("idx", "sources", "status")} | (
		{"expected_amount": l.get("expected_amount"), "actual_amount": l.get("actual_amount")} if figures else {})
		for l in result["lines"]]
	return {
		"states": result["states"], "labels": result["labels"], "issuable": not problems,
		"headline": core.headline(result), "problems": problems, "actions": actions,
		"mapped": result["mapped"], "legacy": result["legacy"], "lines": lines, "docstatus": doc.docstatus,
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
	uoms = {}
	for r in view["rows"]:
		if r["item_code"] and r["item_code"] not in uoms:
			uoms[r["item_code"]] = frappe.db.get_value("Item", r["item_code"], "stock_uom")
	rows = [{"token": r["token"], "kind": r["kind"], "item_code": r["item_code"], "qty": r["qty"],
		"label": core.row_label(r["kind"], r["position"], r["text"], r["qty"], uoms.get(r["item_code"]))}
		| ({"selling_amount": r["selling_amount"]} if figures else {}) for r in view["rows"]]
	return {"rows": rows, "suggestions": core.suggest(view, quote_view(doc)), "additional_item": view["additional_item"]}


# ---------------------------------------------------------------- prepared, ready, issued

def issued_quotation(dcs):
	"""A submitted, current quotation with a documented issue (Sent or later), or a pre-mapping issued record."""
	rows = frappe.get_all("Quotation", filters={"custom_deal_cost_sheet": dcs, "docstatus": 1,
		"custom_dcs_superseded_revision": ["is", "not set"]},
		fields=["name", "custom_pipeline_stage", "custom_dcs_legacy_basis"], order_by="modified desc")
	for row in rows:
		if row.custom_pipeline_stage in ISSUED_STAGES or row.custom_dcs_legacy_basis:
			return row.name
	return None


def sync_quote_status(doc, method=None):
	"""The single owner of the DCS "Quoted" status (the link-back Server Script no longer writes it).

	Draft = prepared and submitted = approved/ready: the sheet stays "Submitted to Sales"
	with its quotation link. "Quoted" means a submitted quotation was documented as sent
	(Sent / Follow-up or a later outcome). Won and Lost are never touched.
	"""
	dcs = doc.get("custom_deal_cost_sheet")
	if not dcs or not frappe.db.exists("Deal Cost Sheet", dcs):
		return
	sheet = frappe.db.get_value("Deal Cost Sheet", dcs, ["custom_deal_status", "docstatus", "presales_request"], as_dict=True)
	if sheet.docstatus != 1 or sheet.custom_deal_status not in ("Quoted", "Submitted to Sales"):
		return
	target = "Quoted" if issued_quotation(dcs) else "Submitted to Sales"
	if sheet.custom_deal_status != target:
		frappe.db.set_value("Deal Cost Sheet", dcs, "custom_deal_status", target, update_modified=False)
	pr = sheet.presales_request
	if pr and frappe.get_meta("Presales Request").has_field("custom_deal_status"):
		current = frappe.db.get_value("Presales Request", pr, "custom_deal_status")
		if current in ("Quoted", "Submitted to Sales") and current != target:
			frappe.db.set_value("Presales Request", pr, "custom_deal_status", target, update_modified=False)
