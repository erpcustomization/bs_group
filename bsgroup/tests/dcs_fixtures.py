"""Shared fixtures for the rel-1 DCS tests. Every record is prefixed ZZTEST so
staging cleanup can find it; nothing here is ever run against production."""

import frappe
from frappe.utils import nowdate

PREFIX = "ZZTEST"


def ensure(doctype, name, values, insert=True):
	if frappe.db.exists(doctype, name):
		return name
	doc = frappe.get_doc({"doctype": doctype, "name": name, **values})
	doc.flags.ignore_permissions = True
	doc.flags.ignore_mandatory = True
	if insert:
		doc.insert(ignore_permissions=True, ignore_mandatory=True, ignore_links=True)
	else:
		doc.db_insert()
	return doc.name


def make_customer(suffix="A"):
	name = f"{PREFIX}-Customer-{suffix}"
	return ensure("Customer", name, {"customer_name": name, "customer_type": "Company"}, insert=False)


def make_lead(suffix="A"):
	name = f"{PREFIX}-Lead-{suffix}"
	return ensure(
		"Lead", name,
		{"lead_name": f"{PREFIX} Lead {suffix}", "company_name": f"{PREFIX} Lead Co {suffix}", "status": "Lead"},
		insert=False,
	)


def make_opportunity(party_type="Customer", party=None, suffix="A"):
	party = party or (make_customer(suffix) if party_type == "Customer" else make_lead(suffix))
	opp = frappe.get_doc(
		{
			"doctype": "Opportunity",
			"opportunity_from": party_type,
			"party_name": party,
			"custom_subject": f"{PREFIX} opportunity {suffix}",
		}
	)
	opp.flags.ignore_links = True
	opp.insert(ignore_permissions=True, ignore_mandatory=True)
	return opp


def make_dcs(party_type="Customer", suffix="A", submit=False, **extra):
	opp = make_opportunity(party_type=party_type, suffix=suffix)
	dcs = frappe.get_doc(
		{
			"doctype": "Deal Cost Sheet",
			"opportunity": opp.name,
			"party_type": party_type,
			"party": opp.party_name,
			"subject": f"{PREFIX} DCS {suffix}",
			"deal_owner": "Administrator",
			"items": [{"item_code": _any_item(), "qty": 1, "cost_rate": 1000, "selling_rate": 1500}],
			**extra,
		}
	)
	dcs.flags.ignore_links = True
	dcs.insert(ignore_permissions=True, ignore_mandatory=True)
	if submit:
		dcs.flags.ignore_links = True
		dcs.submit()
	return dcs


def _any_item():
	item = frappe.db.get_value("Item", {"disabled": 0}, "name")
	if not item:
		item = ensure("Item", f"{PREFIX}-Item", {"item_code": f"{PREFIX}-Item", "item_name": f"{PREFIX} Item",
			"item_group": frappe.db.get_value("Item Group", {}, "name"), "stock_uom": frappe.db.get_value("UOM", {}, "name")})
	return item


def make_user(email, roles):
	if not frappe.db.exists("User", email):
		user = frappe.get_doc({"doctype": "User", "email": email, "first_name": email.split("@")[0], "send_welcome_email": 0})
		user.insert(ignore_permissions=True)
	user = frappe.get_doc("User", email)
	have = {r.role for r in user.roles}
	for r in roles:
		if r not in have and frappe.db.exists("Role", r):
			user.append("roles", {"role": r})
	user.save(ignore_permissions=True)
	return email


def today():
	return nowdate()
