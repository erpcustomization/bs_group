import frappe


def execute():
	"""Backfill blank `company` on Lead records with the site's default company.

	Leads without a company are invisible to users who only have a company-scoped
	User Permission, since the wildcard permission_query_conditions filters on
	`company = <user's default company>`.
	"""

	default_company = frappe.defaults.get_global_default("company")
	if not default_company:
		return

	frappe.db.sql(
		"""
		UPDATE `tabLead`
		SET company = %s
		WHERE company IS NULL OR company = ''
		""",
		(default_company,),
	)
