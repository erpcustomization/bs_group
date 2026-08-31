import frappe
from frappe.utils import today, add_days, getdate, get_first_day, get_last_day


def _get_team_users(user):
	"""Return the list of users a Sales Manager can see (their team + themselves)."""
	employee = frappe.db.get_value("Employee", {"user_id": user}, "name")
	team = []
	if employee:
		team = frappe.get_all(
			"Employee",
			filters={"reports_to": employee},
			pluck="user_id",
		)
	team.append(user)
	return team


@frappe.whitelist()
def get_sales_users():
	"""Return opportunity owners visible to the current user."""
	user  = frappe.session.user
	roles = frappe.get_roles(user)
	company = frappe.defaults.get_user_default("company")
	co_cond = " AND company = %s" if company else ""

	if "System Manager" in roles:
		return frappe.db.sql(
			f"""
			SELECT DISTINCT opportunity_owner AS user
			FROM `tabOpportunity`
			WHERE opportunity_owner IS NOT NULL AND opportunity_owner != ''
			{co_cond}
			ORDER BY opportunity_owner
			""",
			([company] if company else []),
			as_dict=True,
		)

	if "Sales Manager" in roles:
		team = _get_team_users(user)
		placeholders = ", ".join(["%s"] * len(team))
		params = team + ([company] if company else [])
		return frappe.db.sql(
			f"""
			SELECT DISTINCT opportunity_owner AS user
			FROM `tabOpportunity`
			WHERE opportunity_owner IN ({placeholders})
			  AND opportunity_owner IS NOT NULL AND opportunity_owner != ''
			{co_cond}
			ORDER BY opportunity_owner
			""",
			params,
			as_dict=True,
		)

	return []


@frappe.whitelist()
def get_dashboard_data(selected_user=None, from_date=None, to_date=None):
	user = frappe.session.user

	roles             = frappe.get_roles(user)
	is_system_manager = "System Manager" in roles
	is_sales_manager  = "Sales Manager"  in roles
	can_filter        = is_system_manager or is_sales_manager

	# Common conditions
	today_date     = today()
	month_start    = str(get_first_day(today_date))
	month_end      = str(get_last_day(today_date))
	seven_days_ago = str(add_days(today_date, -7))

	# Date range for closing queries
	closing_start = from_date if from_date else month_start
	closing_end   = to_date   if to_date   else month_end

	# ── COMPANY FILTER ───────────────────────────────────────────────────
	company           = frappe.defaults.get_user_default("company")
	company_condition = " AND company = %s" if company else ""
	company_values    = [company] if company else []
	currency          = (
		frappe.db.get_value("Company", company, "default_currency")
		if company else frappe.defaults.get_global_default("currency")
	)

	# ── USER FILTER CONDITION ────────────────────────────────────────────
	user_condition = ""
	user_values    = []
	owner_filter   = None   # used for frappe.db.count calls

	if is_system_manager and selected_user:
		user_condition = " AND opportunity_owner = %s"
		user_values    = [selected_user]
		owner_filter   = ["opportunity_owner", "=", selected_user]

	elif is_system_manager:
		pass  # no restriction — sees all

	elif is_sales_manager and selected_user:
		user_condition = " AND opportunity_owner = %s"
		user_values    = [selected_user]
		owner_filter   = ["opportunity_owner", "=", selected_user]

	elif is_sales_manager:
		team           = _get_team_users(user)
		placeholders   = ", ".join(["%s"] * len(team))
		user_condition = f" AND opportunity_owner IN ({placeholders})"
		user_values    = team
		owner_filter   = ["opportunity_owner", "in", team]

	else:
		user_condition = " AND opportunity_owner = %s"
		user_values    = [user]
		owner_filter   = ["opportunity_owner", "=", user]

	def _p(*prepend):
		"""Build param tuple: prepend + user_values + company_values."""
		return (*prepend, *user_values, *company_values)

	# ── KPI 1: Total Pipeline ────────────────────────────────────────────
	total_pipeline = frappe.db.sql(
		f"""
		SELECT COALESCE(SUM(opportunity_amount), 0)
		FROM `tabOpportunity`
		WHERE sales_stage NOT IN ('Lost', 'Won', 'Closed')
		{user_condition}
		{company_condition}
		""",
		_p(),
	)[0][0] or 0

	# ── KPI 2: Closing in Selected Range ────────────────────────────────
	closing_month = frappe.db.sql(
		f"""
		SELECT COALESCE(SUM(opportunity_amount), 0)
		FROM `tabOpportunity`
		WHERE sales_stage NOT IN ('Lost', 'Won', 'Closed')
		  AND expected_closing BETWEEN %s AND %s
		{user_condition}
		{company_condition}
		""",
		_p(closing_start, closing_end),
	)[0][0] or 0

	# ── KPI 3: Overdue Follow-ups ────────────────────────────────────────
	filters = [
		["sales_stage", "not in", ["Lost", "Won", "Closed"]],
		["custom_next_action_date", "<", today_date],
		["custom_next_action_date", "is", "set"],
	]

	if owner_filter:
		filters.append(owner_filter)
	if company:
		filters.append(["company", "=", company])

	overdue_count = frappe.db.count("Opportunity", filters=filters)

	# ── KPI 4: No Updates in 7 Days ──────────────────────────────────────
	filters = [
		["sales_stage", "not in", ["Lost", "Won", "Closed"]],
		["modified", "<", seven_days_ago],
	]

	if owner_filter:
		filters.append(owner_filter)
	if company:
		filters.append(["company", "=", company])

	no_update_count = frappe.db.count("Opportunity", filters=filters)

	# ── Pipeline by Stage ────────────────────────────────────────────────
	stage_data = frappe.db.sql(
		f"""
		SELECT IFNULL(NULLIF(sales_stage, ''), 'Unset') AS sales_stage,
		       COALESCE(SUM(opportunity_amount), 0) AS amount,
		       COUNT(*) AS count
		FROM `tabOpportunity`
		WHERE sales_stage NOT IN ('Lost', 'Won', 'Closed')
		{user_condition}
		{company_condition}
		GROUP BY sales_stage
		ORDER BY amount DESC
		""",
		_p(),
		as_dict=True,
	)

	# ── Owner-wise Pipeline ──────────────────────────────────────────────
	owner_data = frappe.db.sql(
		f"""
		SELECT opportunity_owner,
		       COALESCE(SUM(opportunity_amount), 0) AS amount,
		       COUNT(*) AS count
		FROM `tabOpportunity`
		WHERE sales_stage NOT IN ('Lost', 'Won', 'Closed')
		  AND opportunity_owner IS NOT NULL
		  AND opportunity_owner != ''
		{user_condition}
		{company_condition}
		GROUP BY opportunity_owner
		ORDER BY amount DESC
		LIMIT 10
		""",
		_p(),
		as_dict=True,
	)

	for row in owner_data:
		if row.opportunity_owner:
			row.owner_short = row.opportunity_owner.split("@")[0].split(" ")[0].title()
		else:
			row.owner_short = "Unassigned"

	# ── Overdue List ─────────────────────────────────────────────────────
	overdue_list = frappe.db.sql(
		f"""
		SELECT name, customer_name, party_name, sales_stage,
		       custom_next_action, custom_next_action_date, opportunity_owner
		FROM `tabOpportunity`
		WHERE sales_stage NOT IN ('Lost', 'Won', 'Closed')
		  AND custom_next_action_date < %s
		  AND custom_next_action_date IS NOT NULL
		{user_condition}
		{company_condition}
		ORDER BY custom_next_action_date ASC
		LIMIT 6
		""",
		_p(today_date),
		as_dict=True,
	)

	for row in overdue_list:
		row.display_name = row.customer_name or row.party_name or row.name
		if row.custom_next_action_date:
			d = getdate(row.custom_next_action_date)
			row.due_display = d.strftime("%d-%b")

	# ── Closing List ─────────────────────────────────────────────────────
	closing_list = frappe.db.sql(
		f"""
		SELECT name, customer_name, party_name, sales_stage,
		       opportunity_amount, probability, expected_closing, opportunity_owner
		FROM `tabOpportunity`
		WHERE sales_stage NOT IN ('Lost', 'Won', 'Closed')
		  AND expected_closing BETWEEN %s AND %s
		{user_condition}
		{company_condition}
		ORDER BY opportunity_amount DESC
		LIMIT 6
		""",
		_p(closing_start, closing_end),
		as_dict=True,
	)

	for row in closing_list:
		row.display_name = row.customer_name or row.party_name or row.name

	# ── Latest Updates ───────────────────────────────────────────────────
	updates_list = frappe.db.sql(
		f"""
		SELECT name, customer_name, party_name, title,
		       custom_last_sales_update, custom_last_update_date,
		       opportunity_owner, modified
		FROM `tabOpportunity`
		WHERE sales_stage NOT IN ('Lost', 'Won', 'Closed')
		  AND custom_last_sales_update IS NOT NULL
		  AND custom_last_sales_update != ''
		{user_condition}
		{company_condition}
		ORDER BY COALESCE(custom_last_update_date, modified) DESC
		LIMIT 6
		""",
		_p(),
		as_dict=True,
	)

	for row in updates_list:
		row.display_name = row.customer_name or row.party_name or row.name
		row.owner_short = (
			row.opportunity_owner.split("@")[0].title()
			if row.opportunity_owner else "Unassigned"
		)

	# ── Stuck Deals ──────────────────────────────────────────────────────
	stuck_list = frappe.db.sql(
		f"""
		SELECT name, customer_name, party_name, sales_stage,
		       custom_stage_age_days, opportunity_owner, opportunity_amount
		FROM `tabOpportunity`
		WHERE sales_stage NOT IN ('Lost', 'Won', 'Closed')
		  AND custom_stage_age_days > 14
		{user_condition}
		{company_condition}
		ORDER BY custom_stage_age_days DESC
		LIMIT 6
		""",
		_p(),
		as_dict=True,
	)

	for row in stuck_list:
		row.display_name = row.customer_name or row.party_name or row.name
		row.owner_short = (
			row.opportunity_owner.split("@")[0].title()
			if row.opportunity_owner else "Unassigned"
		)

	return {
		"kpis": {
			"total_pipeline": float(total_pipeline),
			"closing_month": float(closing_month),
			"overdue_count": overdue_count,
			"no_update_count": no_update_count,
		},
		"pipeline_by_stage": stage_data,
		"owner_pipeline": owner_data,
		"overdue_list": overdue_list,
		"closing_list": closing_list,
		"updates_list": updates_list,
		"stuck_list": stuck_list,
		"is_manager": can_filter,
		"currency": currency,
		"active_filters": {
			"selected_user": selected_user,
			"from_date": closing_start,
			"to_date": closing_end,
			"is_custom_date": bool(from_date or to_date),
		},
		"generated_at": frappe.utils.now_datetime().strftime("%d %b %Y, %I:%M %p"),
	}