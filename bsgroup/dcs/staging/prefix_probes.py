"""Standalone pre-fix / post-fix probes for the rel-1 staging cycle.

Run from <bench>/sites with the bench python, independent of the app commit:
    ../env/bin/python ~/rel1/prefix_probes.py dcs-test.local <probe>

Each probe prints one OBSERVED line and ALWAYS rolls back its transaction, so
the restored production data is never changed by a probe. The expected
outcome on 231ff58 (pre-fix) and on rel-1 (post-fix) is printed alongside.
"""

import json
import sys
import traceback

import frappe

SITE, PROBE = sys.argv[1], sys.argv[2]


def line(scenario, observed, pre, post):
	print(json.dumps({"scenario": scenario, "observed": observed, "expected_prefix": pre, "expected_postfix": post}))


def any_dcs():
	return frappe.db.get_value("Deal Cost Sheet", {"docstatus": 1}, "name") or frappe.db.get_value("Deal Cost Sheet", {}, "name")


def s22_direct_governance_insert():
	ev = frappe.get_doc({"doctype": "DCS Governance Event", "dcs": any_dcs(), "event_code": "ZZTEST_PROBE",
		"actor": "Guest", "event_timestamp": "2000-01-01 00:00:00", "correlation_id": "FORGED", "outcome": "Success",
		"changes": json.dumps([{"fieldname": "subject", "old_value": "a", "new_value": "b"}]), "change_count": 1})
	try:
		ev.insert(ignore_permissions=True)
		line("S-22 direct insert without audit flag", f"INSERTED as {ev.name} actor={ev.actor} corr={ev.correlation_id}", "inserted (defect R5-1)", "PermissionError")
	except Exception as e:
		line("S-22 direct insert without audit flag", f"REFUSED: {type(e).__name__}: {str(e)[:120]}", "inserted (defect R5-1)", "PermissionError")


def s22a_edit_delete_event():
	name = frappe.db.get_value("DCS Governance Event", {}, "name")
	doc = frappe.get_doc("DCS Governance Event", name)
	doc.reason = (doc.reason or "") + " [probe]"
	try:
		doc.save(ignore_permissions=True); res_e = "EDIT ALLOWED"
	except Exception as e:
		res_e = f"edit refused: {type(e).__name__}"
	try:
		frappe.delete_doc("DCS Governance Event", name, ignore_permissions=True); res_d = "DELETE ALLOWED"
	except Exception as e:
		res_d = f"delete refused: {type(e).__name__}"
	line("S-22a edit/delete governance event", f"{res_e}; {res_d}", "depends on the enabled Server Script guards", "both refused by controller (with the scripts disabled too)")


def s23a_presales_sync_whitelisted():
	from bsgroup.bs_group.doctype.deal_cost_sheet import deal_cost_sheet as m
	w = m.dcs_presales_sync in frappe.whitelisted
	line("S-23a dcs_presales_sync whitelisted", f"whitelisted={w}", "True (defect R5-3)", "False")


def s04_duplicate_dcs():
	src = frappe.get_doc("Deal Cost Sheet", any_dcs())
	dup = frappe.get_doc({"doctype": "Deal Cost Sheet", "opportunity": src.opportunity, "subject": "ZZTEST probe dup",
		"customer": src.customer, "party_type": src.get("party_type"), "party": src.get("party"),
		"deal_owner": "Administrator", "items": [{"item_code": src.items[0].item_code, "qty": 1, "cost_rate": 1, "selling_rate": 2}] if src.items else []})
	dup.flags.ignore_links = True
	try:
		dup.insert(ignore_permissions=True, ignore_mandatory=True)
		line("S-04 second DCS on same Opportunity", f"INSERTED {dup.name}", "inserted or blocked only by the enabled Server Script", "refused by app guard (ungated)")
	except Exception as e:
		line("S-04 second DCS on same Opportunity", f"REFUSED: {type(e).__name__}: {str(e)[:140]}", "inserted or blocked only by the enabled Server Script", "refused by app guard (ungated)")


def s14_helper_permissions():
	from bsgroup.bs_group.doctype.deal_cost_sheet import deal_cost_sheet as m
	import inspect
	src = inspect.getsource(m.make_quotation)
	line("S-14 permission check in make_quotation", "has_permission present" if "has_permission" in src else "NO permission check", "absent (R2-11)", "present")


def s01_pr_from_lead():
	lead = frappe.db.get_value("Lead", {}, "name")
	opp = frappe.get_doc({"doctype": "Opportunity", "opportunity_from": "Lead", "party_name": lead})
	opp.flags.ignore_links = True
	opp.insert(ignore_permissions=True, ignore_mandatory=True)
	pr = frappe.get_doc({"doctype": "Presales Request", "opportunity": opp.name, "subject": "ZZTEST probe", "status": "Open",
		"customer": frappe.db.get_value("Lead", lead, "company_name") or "ZZTEST Org"})
	pr.flags.ignore_links = True
	try:
		pr.insert(ignore_permissions=True, ignore_mandatory=True)
		line("S-01 PR from Lead-sourced Opportunity", f"INSERTED {pr.name} customer={pr.customer!r} party_type={pr.get('party_type')!r}", "inserted with free text in customer (R1-1) or link error", "inserted with party_type=Lead, customer empty")
	except Exception as e:
		line("S-01 PR from Lead-sourced Opportunity", f"REFUSED: {type(e).__name__}: {str(e)[:140]}", "inserted with free text in customer (R1-1) or link error", "inserted with party_type=Lead, customer empty")


def s19_handover_controller():
	from frappe.model.base_document import get_controller
	row = frappe.db.get_value("DocType", "DCS Handover Condition", ["custom", "module"], as_dict=True)
	line("S-19 Handover Condition controller", f"custom={row.custom} module={row.module} controller={get_controller('DCS Handover Condition').__name__}", "custom=1 Custom Document", "custom=0 BS Group DCSHandoverCondition")


def s16_scheduler_touch():
	from bsgroup.bs_group.doctype.presales_request import presales_request as m
	name = frappe.db.get_value("Presales Request", {"status": "Lost"}, "name") or frappe.db.get_value("Presales Request", {}, "name")
	before = frappe.db.get_value("Presales Request", name, "modified")
	out = m.calculate_due_date()
	after = frappe.db.get_value("Presales Request", name, "modified")
	line("S-16 scheduler touches closed / unchanged records", f"return={out} modified_moved={before != after} sample={name}", "writes every record with due_date, modified bumped (R4-1..3)", "only open+changed, modified unchanged")


try:
	frappe.init(site=SITE)
	frappe.connect()
	frappe.set_user("Administrator")
	globals()[PROBE]()
except Exception:
	print(json.dumps({"scenario": PROBE, "observed": "PROBE ERROR", "trace": traceback.format_exc()[-800:]}))
finally:
	try:
		frappe.db.rollback()
	finally:
		frappe.destroy()
