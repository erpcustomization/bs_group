"""Hash-checked rewrite of the "Quotation - Link Back to DCS and Close Presales" Server Script.

The script wrote the DCS and Presales Request deal status "Quoted" on every Quotation
save, drafts included. The deal status now has one owner
(``bsgroup.dcs.quote_alignment.sync_quote_status``). This module removes exactly
those two writes from the known production version and nothing else: the
quotation/DCS/presales links, the presales status ladder and the canonical
projection sync are unchanged. Any other (customised) version is left untouched.

No Frappe import, so the transform is testable without a site.
"""
import hashlib
import pathlib

NAME = "Quotation - Link Back to DCS and Close Presales"
ORIGINAL_SHA256 = "39be1445d34c3756ee8598164b3e4768b71a88b265fb98999e07516bbc13840f"
ORIGINAL_PATH = pathlib.Path(__file__).with_name("server_script_export") / "Quotation_Link_Back_to_DCS_and_Close_Presales.py"

DCS_STATUS_WRITE = (
	"    cur = frappe.db.get_value('Deal Cost Sheet', dcs, 'custom_deal_status')\n"
	"    if cur not in ['Won', 'Lost', 'Dropped / No Bid']:\n"
	"        frappe.db.set_value('Deal Cost Sheet', dcs, 'custom_deal_status', 'Quoted', update_modified=False)\n"
)
PRESALES_STATUS_WRITE = "    frappe.db.set_value('Presales Request', pr, 'custom_deal_status', 'Quoted', update_modified=False)\n"
OWNER_NOTE = "    # Deal status (Submitted to Sales / Quoted) is owned by bsgroup.dcs.quote_alignment.sync_quote_status.\n"


def sha256(text):
	return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def original():
	text = ORIGINAL_PATH.read_text(encoding="utf-8")
	if sha256(text) != ORIGINAL_SHA256:
		raise ValueError("The stored original link-back script does not match its recorded checksum.")
	return text


def convert(text):
	"""Remove the two status writes; refuses anything but the exact known version."""
	if sha256(text) != ORIGINAL_SHA256:
		raise ValueError("Not the known version of the link-back script; refusing to change it.")
	if text.count(DCS_STATUS_WRITE) != 1 or text.count(PRESALES_STATUS_WRITE) != 1:
		raise ValueError("Status writes not found exactly once.")
	return text.replace(DCS_STATUS_WRITE, OWNER_NOTE).replace(PRESALES_STATUS_WRITE, OWNER_NOTE)


def converted_sha256():
	return sha256(convert(original()))


def plan(current):
	"""Decide what migration does with the live script text: convert, already, or skip (customised/absent)."""
	if current is None:
		return "absent"
	digest = sha256(current)
	if digest == ORIGINAL_SHA256:
		return "convert"
	if digest == converted_sha256():
		return "already"
	return "customised"
