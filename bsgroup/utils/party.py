"""Party model shared by Presales Request and Deal Cost Sheet (A-5, A-6; D1-D3).

A request or cost sheet is raised for a *party*: either a Lead (a prospect
that is not yet a Customer) or a Customer. ``organisation_name`` is derived on
the server from the party record and is what the document is named after.
``customer`` is a plain Link that is set only when the party *is* a Customer;
it is never accepted from the client.

Business decisions implemented here:

* D1 - a Lead-sourced opportunity may be costed without inventing a Customer.
* D2 - the organisation name shown and used for naming comes from the party
  record, not from free text.
* D3 - a Customer record is required before the deal is Won or a Project is
  linked.
"""

import re

import frappe
from frappe import _

PARTY_TYPES = ("Lead", "Customer")


def organisation_name_for(party_type, party):
	"""Return the display/naming organisation name for a party record."""
	if party_type == "Customer":
		return frappe.db.get_value("Customer", party, "customer_name") or party
	if party_type == "Lead":
		row = frappe.db.get_value("Lead", party, ["company_name", "lead_name"], as_dict=True) or {}
		return row.get("company_name") or row.get("lead_name") or party
	return ""


def party_from_opportunity(opportunity):
	"""(party_type, party) as recorded on the Opportunity, or (None, None)."""
	if not opportunity:
		return None, None
	row = frappe.db.get_value("Opportunity", opportunity, ["opportunity_from", "party_name"], as_dict=True)
	if not row or row.opportunity_from not in PARTY_TYPES or not row.party_name:
		return None, None
	return row.opportunity_from, row.party_name


def slug(text):
	"""Naming slug identical to the historical `customer` slug: strip non-alphanumerics, spaces -> '-'."""
	text = re.sub(r"[^a-zA-Z0-9\s]", "", text or "")
	return re.sub(r"\s+", "-", text.strip())


def apply_party_model(doc):
	"""Normalise and validate the party fields on ``doc`` (call from ``validate``).

	* fills party_type/party from the Opportunity when both are blank;
	* derives organisation_name from the party record (never from the client);
	* sets ``customer`` = party when party_type is Customer, clears it otherwise;
	* refuses a customer that does not match the party.
	"""
	if not doc.get("party_type") and not doc.get("party") and doc.get("opportunity"):
		pt, p = party_from_opportunity(doc.opportunity)
		if pt:
			doc.party_type, doc.party = pt, p

	if doc.get("party_type") and doc.party_type not in PARTY_TYPES:
		frappe.throw(_("Party Type must be Lead or Customer."))
	if doc.get("party_type") and not doc.get("party"):
		frappe.throw(_("Party is required when Party Type is set."))
	if doc.get("party") and not doc.get("party_type"):
		frappe.throw(_("Party Type is required when Party is set."))

	if doc.get("party_type") and doc.get("party"):
		if not frappe.db.exists(doc.party_type, doc.party):
			frappe.throw(_("{0} {1} does not exist.").format(doc.party_type, doc.party))
		doc.organisation_name = organisation_name_for(doc.party_type, doc.party)
		if doc.party_type == "Customer":
			if doc.get("customer") and doc.customer != doc.party:
				frappe.throw(
					_("Customer {0} does not match the Party {1}. Customer is derived from the Party and cannot be set independently.")
					.format(doc.customer, doc.party)
				)
			doc.customer = doc.party
		else:
			# A Lead is not a Customer. The Customer link stays empty until the
			# party is switched to the Customer record created for it (D1, D3).
			doc.customer = None


def require_customer(doc, why):
	"""D3 gate: raise unless the document carries a Customer record."""
	if not doc.get("customer"):
		frappe.throw(
			_("A Customer record is required before {0}. This document is for {1} {2}; create or select the Customer, "
			  "set Party Type to Customer and choose it as the Party first.")
			.format(why, doc.get("party_type") or "an unknown party type", doc.get("party") or "(no party)")
		)
	if not frappe.db.exists("Customer", doc.customer):
		frappe.throw(_("Customer {0} does not exist.").format(doc.customer))
