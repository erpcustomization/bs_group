"""Pre-fix / post-fix reproduction probes for the rel-1 staging cycle (Section 7).

Run from <bench>/sites with the bench python, independent of the app commit:

    ../env/bin/python ~/rel1/prefix_probes.py <site> <mode> [probe ...]
    mode = prefix   (expectations for production commit 231ff58)
         | postfix  (expectations for fix/dcs-core-release-1)

Every probe runs as a NON-Administrator ZZTEST user created inside the probe's
own transaction, classifies what it observed into one of a few outcome codes,
compares that code with the expected code for the mode, prints one JSON line
and ALWAYS rolls back. The process exits 1 if any probe's outcome differs from
the expectation, so the calling phase fails.

Deferred-by-instruction outcomes are encoded as expectations too (S-01, S-19),
so the matrix stays honest: they show as PASS WITH EXCEPTION in the summary.
"""

import json
import sys
import traceback

import frappe

SITE, MODE = sys.argv[1], sys.argv[2]
ONLY = sys.argv[3:]
RESULTS = []

ROLE_SETS = {
	"nobody": ["Employee"],
	"sysmgr": ["System Manager"],
	"tech": ["Technical Engineer", "Project Manager"],
	"md": ["Sales Manager", "Commercial Controller", "Managing Director", "System Manager"],
	"sales": ["Sales User"],
}


# --------------------------------------------------------------------------- helpers
def user(kind):
	email = f"zztest-{kind}@example.invalid"
	if not frappe.db.exists("User", email):
		u = frappe.get_doc({"doctype": "User", "email": email, "first_name": f"ZZTEST {kind}", "send_welcome_email": 0, "enabled": 1})
		u.flags.ignore_permissions = True
		u.insert(ignore_permissions=True)
	u = frappe.get_doc("User", email)
	have = {r.role for r in u.roles}
	for role in ROLE_SETS[kind]:
		if role not in have and frappe.db.exists("Role", role):
			u.append("roles", {"role": role})
	u.save(ignore_permissions=True)
	return email


def as_user(kind):
	frappe.set_user(user(kind))


def admin():
	frappe.set_user("Administrator")


def has_party_model():
	return frappe.get_meta("Presales Request").has_field("party_type")


def any_item():
	return frappe.db.get_value("Item", {"disabled": 0}, "name")


def lead_opportunity():
	lead = frappe.db.get_value("Lead", {"company_name": ["!=", ""]}, "name") or frappe.db.get_value("Lead", {}, "name")
	opp = frappe.get_doc({"doctype": "Opportunity", "opportunity_from": "Lead", "party_name": lead, "custom_subject": "ZZTEST probe"})
	opp.flags.ignore_links = True
	opp.insert(ignore_permissions=True, ignore_mandatory=True)
	return opp, lead


def customer_opportunity():
	cust = frappe.db.get_value("Customer", {"disabled": 0}, "name")
	opp = frappe.get_doc({"doctype": "Opportunity", "opportunity_from": "Customer", "party_name": cust, "custom_subject": "ZZTEST probe"})
	opp.flags.ignore_links = True
	opp.insert(ignore_permissions=True, ignore_mandatory=True)
	return opp, cust


def new_pr(opp, **extra):
	values = {"doctype": "Presales Request", "opportunity": opp.name, "subject": "ZZTEST probe PR", "status": "Open"}
	if has_party_model():
		values.update({"party_type": opp.opportunity_from, "party": opp.party_name})
	else:
		values["customer"] = extra.pop("legacy_customer", None) or opp.party_name
	values.update(extra)
	pr = frappe.get_doc(values)
	pr.flags.ignore_links = True
	pr.insert(ignore_permissions=True, ignore_mandatory=True)
	return pr


def new_dcs(opp, **extra):
	values = {"doctype": "Deal Cost Sheet", "opportunity": opp.name, "subject": "ZZTEST probe DCS", "deal_owner": "Administrator",
		"items": [{"item_code": any_item(), "qty": 1, "cost_rate": 1000, "selling_rate": 1500}]}
	if has_party_model():
		values.update({"party_type": opp.opportunity_from, "party": opp.party_name})
	else:
		values["customer"] = opp.party_name
	values.update(extra)
	d = frappe.get_doc(values)
	d.flags.ignore_links = True
	d.insert(ignore_permissions=True, ignore_mandatory=True)
	return d


def exc_code(e):
	n = type(e).__name__
	if isinstance(e, frappe.PermissionError):
		return "PermissionError"
	if isinstance(e, frappe.LinkExistsError):
		return "LinkExistsError"
	if isinstance(e, frappe.LinkValidationError):
		return "LinkValidationError"
	if isinstance(e, frappe.DuplicateEntryError):
		return "DuplicateEntryError"
	if isinstance(e, frappe.ValidationError):
		return "ValidationError"
	return n


# --------------------------------------------------------------------------- probes
# each returns (observed_code, detail); EXPECT maps probe -> {mode: code}
EXPECT = {}


def probe(name, prefix, postfix):
	def deco(fn):
		EXPECT[name] = {"prefix": prefix, "postfix": postfix, "fn": fn}
		return fn
	return deco


@probe("S-01", prefix="LinkValidationError", postfix="LinkValidationError")  # H-1 not applied in this cycle (deferred): same outcome expected
def s01_save_bad_pr_unchanged():
	name = frappe.db.sql("""select p.name from `tabPresales Request` p where p.docstatus < 2 and not exists
		(select 1 from `tabCustomer` c where c.name = p.customer) limit 1""")
	if not name:
		return "NO_BAD_PR", "no bad-customer PR on this site"
	as_user("sysmgr")
	doc = frappe.get_doc("Presales Request", name[0][0])
	try:
		doc.save()
		return "SAVED", f"{doc.name} saved; customer={doc.customer!r}"
	except Exception as e:
		return exc_code(e), f"{doc.name}: {str(e)[:160]}"


@probe("S-02", prefix="FREE_TEXT_CUSTOMER", postfix="PARTY_LEAD_NO_CUSTOMER")
def s02_pr_from_lead_opportunity():
	opp, lead = lead_opportunity()
	org = frappe.db.get_value("Lead", lead, "company_name") or "ZZTEST Org"
	as_user("sales")
	try:
		pr = new_pr(opp, legacy_customer=org)
	except Exception as e:
		return exc_code(e), str(e)[:160]
	if has_party_model():
		if pr.get("party_type") == "Lead" and not pr.customer:
			return "PARTY_LEAD_NO_CUSTOMER", f"{pr.name} party={pr.party} org={pr.organisation_name}"
		return "OTHER", f"party_type={pr.get('party_type')} customer={pr.customer}"
	if pr.customer and not frappe.db.exists("Customer", pr.customer):
		return "FREE_TEXT_CUSTOMER", f"{pr.name} customer={pr.customer!r} is not a Customer"
	return "OTHER", f"customer={pr.customer!r}"


@probe("S-03", prefix="CUSTOMER_LINK", postfix="PARTY_CUSTOMER_LINK")
def s03_pr_from_customer_opportunity():
	opp, cust = customer_opportunity()
	as_user("sales")
	pr = new_pr(opp)
	if has_party_model():
		ok = pr.get("party_type") == "Customer" and pr.party == cust and pr.customer == cust
		return ("PARTY_CUSTOMER_LINK" if ok else "OTHER"), f"party={pr.get('party')} customer={pr.customer}"
	return ("CUSTOMER_LINK" if pr.customer == cust else "OTHER"), f"customer={pr.customer}"


@probe("S-04", prefix="SECOND_PR_SAVED", postfix="ValidationError")
def s04_two_prs_on_one_opportunity():
	opp, _ = customer_opportunity()
	as_user("sales")
	first = new_pr(opp)
	try:
		second = new_pr(opp)
		return "SECOND_PR_SAVED", f"{first.name} and {second.name} both exist on {opp.name}"
	except Exception as e:
		return exc_code(e), str(e)[:160]


@probe("S-14", prefix="DATA_RETURNED", postfix="PermissionError")
def s14_get_cost_summary_without_project_permission():
	from bsgroup.utils import project_cost_baseline as m
	project = frappe.db.get_value("Project", {}, "name")
	as_user("nobody")
	try:
		out = m.get_cost_summary(project)
		return "DATA_RETURNED", f"keys={sorted(out)[:6]}"
	except Exception as e:
		return exc_code(e), str(e)[:120]


@probe("S-14b", prefix="MODULE_ABSENT", postfix="PermissionError")
def s14b_governed_endpoint_without_dcs_permission():
	try:
		from bsgroup.api.dcs import negotiation
	except ImportError:
		return "MODULE_ABSENT", "bsgroup.api.dcs not on this commit"
	dcs = frappe.db.get_value("Deal Cost Sheet", {"docstatus": 1}, "name")
	as_user("nobody")
	try:
		negotiation.dcs_screen3(dcs=dcs)
		return "DATA_RETURNED", "screen3 answered a user with no DCS permission"
	except Exception as e:
		return exc_code(e), str(e)[:120]


@probe("S-16", prefix="MODIFIED_MOVED", postfix="MODIFIED_STABLE")
def s16_scheduler_leaves_cancelled_pr_alone():
	from bsgroup.bs_group.doctype.presales_request import presales_request as m
	opp, _ = customer_opportunity()
	pr = new_pr(opp, due_date=frappe.utils.add_days(frappe.utils.nowdate(), -5))
	frappe.db.set_value("Presales Request", pr.name, {"status": "Cancelled", "docstatus": 2, "overdue": 0, "delay_days": 0}, update_modified=False)
	before = frappe.db.get_value("Presales Request", pr.name, ["modified", "overdue", "delay_days"], as_dict=True)
	m.calculate_due_date()
	after = frappe.db.get_value("Presales Request", pr.name, ["modified", "overdue", "delay_days"], as_dict=True)
	moved = before.modified != after.modified or before.overdue != after.overdue
	return ("MODIFIED_MOVED" if moved else "MODIFIED_STABLE"), f"before={before} after={after}"


@probe("S-18", prefix="SAVED_BLANK", postfix="ValidationError")
def s18_dcs_with_blank_party():
	as_user("sales")
	values = {"doctype": "Deal Cost Sheet", "subject": "ZZTEST blank party", "deal_owner": "Administrator",
		"items": [{"item_code": any_item(), "qty": 1, "cost_rate": 1, "selling_rate": 2}]}
	d = frappe.get_doc(values)
	d.flags.ignore_links = True
	try:
		d.insert(ignore_permissions=True)  # mandatory checks still apply
		return "SAVED_BLANK", f"{d.name} saved with no party / customer"
	except Exception as e:
		return exc_code(e), str(e)[:160]


@probe("S-19", prefix="DELETED", postfix="DELETED")  # ignore_links_on_delete change deferred by instruction: same outcome expected this cycle
def s19_delete_pr_linked_from_dcs():
	opp, _ = customer_opportunity()
	pr = new_pr(opp)
	new_dcs(opp, presales_request=pr.name)
	as_user("sysmgr")
	try:
		frappe.delete_doc("Presales Request", pr.name)
		return "DELETED", f"{pr.name} deleted while a DCS links to it"
	except Exception as e:
		return exc_code(e), str(e)[:160]


@probe("S-21", prefix="TWO_EVENTS_SHARED_KEYS", postfix="ONE_APP_OWNED_EVENT")
def s21_dcs_on_pr_event_count():
	opp, _ = customer_opportunity()
	pr = new_pr(opp, presales_owner="Administrator", estimated_hours=3)
	as_user("md")
	d = new_dcs(opp, presales_request=pr.name)
	evs = frappe.get_all("DCS Governance Event", {"dcs": d.name}, ["name", "event_code", "reason", "correlation_id", "source_event_id"] if frappe.get_meta("DCS Governance Event").has_field("source_event_id") else ["name", "event_code", "reason", "correlation_id"])
	detail = [(e.event_code, e.reason, e.correlation_id, e.get("source_event_id")) for e in evs]
	if len(evs) == 1:
		# Post-retirement: the app's single writer is the only writer left. It stamps a
		# request key and a server-generated correlation id; the legacy Server Scripts
		# set neither, so this distinguishes an app-owned event from a script-owned one.
		e = evs[0]
		key = e.get("source_event_id")
		corr = e.get("correlation_id")
		if key and corr and not str(corr).startswith("AUTH-"):
			return "ONE_APP_OWNED_EVENT", str(detail)
		return "ONE_EVENT_NOT_APP_OWNED", str(detail)
	if len(evs) != 2:
		return f"EVENTS_{len(evs)}", str(detail)
	corr = {e.correlation_id for e in evs}
	keys = {e.get("source_event_id") for e in evs}
	if len(corr) == 1 and len(keys) == 2 and None not in keys and "" not in keys:
		return "TWO_EVENTS_DISTINCT_KEYS_ONE_CORRELATION", str(detail)
	return "TWO_EVENTS_SHARED_KEYS", str(detail)


@probe("S-22", prefix="FORGED_INSERT_ACCEPTED", postfix="PermissionError")
def s22_direct_governance_insert_as_system_manager():
	dcs = frappe.db.get_value("Deal Cost Sheet", {"docstatus": 1}, "name")
	as_user("sysmgr")
	ev = frappe.get_doc({"doctype": "DCS Governance Event", "dcs": dcs, "event_code": "ZZTEST_FORGED",
		"actor": "Guest", "event_timestamp": "2000-01-01 00:00:00", "correlation_id": "FORGED", "outcome": "Success",
		"changes": json.dumps([{"fieldname": "subject", "old_value": "a", "new_value": "b"}]), "change_count": 1})
	try:
		ev.insert()
		return "FORGED_INSERT_ACCEPTED", f"{ev.name} actor={ev.actor} corr={ev.correlation_id}"
	except Exception as e:
		return exc_code(e), str(e)[:160]


@probe("S-22a", prefix="EXECUTED_OVER_HANDLER", postfix="PermissionError")
def s22a_presales_sync_over_api_method_as_nobody():
	from frappe.handler import execute_cmd
	pr = frappe.db.get_value("Presales Request", {"docstatus": ["<", 2]}, "name")
	as_user("nobody")
	frappe.local.form_dict = frappe._dict({"presales_request": pr, "source": "injected"})
	try:
		out = execute_cmd("bsgroup.bs_group.doctype.deal_cost_sheet.deal_cost_sheet.dcs_presales_sync")
		return "EXECUTED_OVER_HANDLER", f"returned {str(out)[:120]}"
	except Exception as e:
		return exc_code(e), str(e)[:160]


@probe("S-22b", prefix="JSON", postfix="JSON_NO_ORPHAN")
def s22b_changes_fieldtype_and_orphan():
	ft = frappe.get_meta("DCS Governance Event").get_field("changes").fieldtype
	orphan = frappe.db.exists("DocType", "DCS Governance Event Change")
	if ft != "JSON":
		return ft, "changes is not JSON"
	return ("JSON_NO_ORPHAN" if not orphan else "JSON"), f"fieldtype={ft} orphan_doctype={'present' if orphan else 'absent'}"


@probe("S-23", prefix="SCRIPT_TWO_EVENTS", postfix="APP_ONE_EVENT_REPLAY")
def s23_governed_endpoint_twice():
	as_user("md")
	opp, _ = customer_opportunity()
	d = new_dcs(opp)
	d.flags.ignore_links = True
	d.submit()
	before = frappe.db.count("DCS Governance Event", {"dcs": d.name})
	try:
		from bsgroup.api.dcs import negotiation
		r1 = negotiation.dcs_apply_revision(dcs=d.name, source="Customer", reason="ZZTEST twice", new_total_selling=1400)
		r2 = negotiation.dcs_apply_revision(dcs=d.name, source="Customer", reason="ZZTEST twice", new_total_selling=1400)
		after = frappe.db.count("DCS Governance Event", {"dcs": d.name})
		if r1.get("ok") == 1 and r2.get("idempotent_replay") == 1 and after - before == 1:
			return "APP_ONE_EVENT_REPLAY", f"events +{after - before}; second call replayed {r2.get('governance_event')}"
		return "OTHER", f"r1={r1.get('ok')} r1err={r1.get('error')} r2={r2.get('idempotent_replay')} events +{after - before}"
	except ImportError:
		pass
	script = frappe.get_doc("Server Script", "dcs_apply_revision")
	for _ in range(2):
		frappe.local.form_dict = frappe._dict({"dcs": d.name, "source": "Customer", "reason": "ZZTEST twice", "new_total_selling": 1400})
		frappe.local.response = frappe._dict()
		script.execute_method()
	after = frappe.db.count("DCS Governance Event", {"dcs": d.name})
	return ("SCRIPT_TWO_EVENTS" if after - before >= 2 else f"SCRIPT_EVENTS_{after - before}"), f"events +{after - before} via Server Script"


@probe("S-23a", prefix="SAME_CORRELATION_ACROSS_REQUESTS", postfix="DIFFERENT_CORRELATION_PER_REQUEST")
def s23a_correlation_per_request():
	from bsgroup.bs_group.doctype.deal_cost_sheet.deal_cost_sheet import dcs_presales_sync
	opp, _ = customer_opportunity()
	pr = new_pr(opp, presales_owner="Administrator", estimated_hours=1)
	d = new_dcs(opp, presales_request=pr.name)
	corr = []
	for hours in (5, 9):
		try:
			from bsgroup.dcs import governance
			governance.reset_correlation_id()  # simulates a new request on rel-1; no-op on 231ff58
		except ImportError:
			pass
		frappe.db.set_value("Presales Request", pr.name, "estimated_hours", hours, update_modified=False)
		dcs_presales_sync(pr.name, source="interactive")
		ev = frappe.get_all("DCS Governance Event", {"dcs": d.name}, ["correlation_id"], order_by="creation desc", limit=1)
		corr.append(ev[0].correlation_id if ev else None)
	if None in corr:
		return "NO_EVENT", str(corr)
	return ("DIFFERENT_CORRELATION_PER_REQUEST" if corr[0] != corr[1] else "SAME_CORRELATION_ACROSS_REQUESTS"), str(corr)


@probe("STEP4-HC", prefix="CUSTOM_DOCTYPE_GENERIC_CONTROLLER", postfix="STANDARD_DOCTYPE_APP_CONTROLLER")
def step4_handover_condition_controller():
	from frappe.model.base_document import get_controller
	row = frappe.db.get_value("DocType", "DCS Handover Condition", ["custom", "module"], as_dict=True)
	ctrl = get_controller("DCS Handover Condition").__name__
	rows = frappe.db.count("DCS Handover Condition")
	if not frappe.utils.cint(row.custom) and row.module == "BS Group" and ctrl == "DCSHandoverCondition":
		return "STANDARD_DOCTYPE_APP_CONTROLLER", f"rows={rows}"
	return "CUSTOM_DOCTYPE_GENERIC_CONTROLLER", f"custom={row.custom} module={row.module} controller={ctrl} rows={rows}"


@probe("STEP8-PCB", prefix="PCB_OPEN", postfix="PCB_LOCKED")
def step8_pcb_locked():
	roles = {p.role for p in frappe.get_meta("Project Cost Baseline").permissions}
	policy = frappe.db.get_single_value("BS Group Settings", "cost_overrun_policy")
	if roles == {"System Manager"} and policy == "None":
		return "PCB_LOCKED", f"roles={sorted(roles)} policy={policy}"
	return "PCB_OPEN", f"roles={sorted(roles)} policy={policy}"


# --------------------------------------------------------------------------- runner
def run(name):
	spec = EXPECT[name]
	expected = spec[MODE]
	frappe.db.begin()
	try:
		admin()
		observed, detail = spec["fn"]()
	except Exception:
		observed, detail = "PROBE_ERROR", traceback.format_exc()[-600:]
	finally:
		frappe.db.rollback()
		admin()
	status = "PASS" if observed == expected else "FAIL"
	if status == "PASS" and name in ("S-01", "S-19"):
		status = "PASS-EXCEPTION"  # deferred by instruction; outcome unchanged in this cycle
	RESULTS.append({"probe": name, "mode": MODE, "status": status, "expected": expected, "observed": observed, "detail": detail})
	print(json.dumps(RESULTS[-1]))


frappe.init(site=SITE)
frappe.connect()
frappe.flags.mute_emails = True
frappe.flags.in_test = True
frappe.local.form_dict = frappe._dict()
names = ONLY or list(EXPECT)
try:
	for n in names:
		run(n)
finally:
	frappe.db.rollback()
	frappe.destroy()
failed = [r["probe"] for r in RESULTS if r["status"] == "FAIL"]
print(json.dumps({"summary": MODE, "pass": sum(r["status"] == "PASS" for r in RESULTS),
	"pass_exception": sum(r["status"] == "PASS-EXCEPTION" for r in RESULTS), "fail": failed}))
sys.exit(1 if failed else 0)
