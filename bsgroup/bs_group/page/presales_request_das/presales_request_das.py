import frappe
from frappe.utils import today, add_days, getdate, get_first_day, get_last_day

# Statuses that are no longer part of the active pipeline
CLOSED_STATUSES = ("Completed", "Won", "Lost", "Cancelled")

def _not_closed():
	"""Return a SQL fragment + value list for excluding closed statuses."""
	placeholders = ", ".join(["%s"] * len(CLOSED_STATUSES))
	return f" AND status NOT IN ({placeholders})", list(CLOSED_STATUSES)


def _get_team_users(user):
	"""Return the list of users a Manager can see (their team + themselves)."""
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
def get_presales_users():
	"""Return presales owners visible to the current user."""
	user  = frappe.session.user
	roles = frappe.get_roles(user)
	company = frappe.defaults.get_user_default("company")
	co_cond = " AND company = %s" if company else ""

	if "System Manager" in roles:
		return frappe.db.sql(
			f"""
			SELECT DISTINCT presales_owner AS user
			FROM `tabPresales Request`
			WHERE presales_owner IS NOT NULL AND presales_owner != ''
			{co_cond}
			ORDER BY presales_owner
			""",
			([company] if company else []),
			as_dict=True,
		)

	if "Sales Manager" in roles or "Presales Manager" in roles:
		team = _get_team_users(user)
		placeholders = ", ".join(["%s"] * len(team))
		params = team + ([company] if company else [])
		return frappe.db.sql(
			f"""
			SELECT DISTINCT presales_owner AS user
			FROM `tabPresales Request`
			WHERE presales_owner IN ({placeholders})
			  AND presales_owner IS NOT NULL AND presales_owner != ''
			{co_cond}
			ORDER BY presales_owner
			""",
			params,
			as_dict=True,
		)

	return []


@frappe.whitelist()
def get_dashboard_data(selected_user=None, from_date=None, to_date=None, selected_status=None, selected_priority=None):
	user  = frappe.session.user
	roles = frappe.get_roles(user)

	is_system_manager = "System Manager"      in roles
	is_manager        = is_system_manager or "Sales Manager" in roles or "Presales Manager" in roles
	can_filter        = is_manager

	today_date     = today()
	month_start    = str(get_first_day(today_date))
	month_end      = str(get_last_day(today_date))
	seven_days_ago = str(add_days(today_date, -7))

	due_start = from_date if from_date else month_start
	due_end   = to_date   if to_date   else month_end

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
	owner_filter   = None

	if is_system_manager and selected_user:
		user_condition = " AND presales_owner = %s"
		user_values    = [selected_user]
		owner_filter   = ["presales_owner", "=", selected_user]
	elif is_system_manager:
		pass  # sees all
	elif is_manager and selected_user:
		user_condition = " AND presales_owner = %s"
		user_values    = [selected_user]
		owner_filter   = ["presales_owner", "=", selected_user]
	elif is_manager:
		team           = _get_team_users(user)
		placeholders   = ", ".join(["%s"] * len(team))
		user_condition = f" AND presales_owner IN ({placeholders})"
		user_values    = team
		owner_filter   = ["presales_owner", "in", team]
	else:
		user_condition = " AND presales_owner = %s"
		user_values    = [user]
		owner_filter   = ["presales_owner", "=", user]

	# ── EXTRA FILTERS ────────────────────────────────────────────────────
	status_condition   = ""
	priority_condition = ""
	extra_values       = []

	if selected_status:
		status_condition = " AND status = %s"
		extra_values.append(selected_status)
	if selected_priority:
		priority_condition = " AND priority = %s"
		extra_values.append(selected_priority)

	all_extra = f"{status_condition}{priority_condition}"

	_nc_sql, _nc_vals = _not_closed()

	def _vals(*prepend):
		"""For queries that include {_nc_sql} — injects closed-status params."""
		return (*prepend, *_nc_vals, *user_values, *extra_values, *company_values)

	def _vals_plain(*prepend):
		"""For queries with an explicit status condition — no closed-status params."""
		return (*prepend, *user_values, *extra_values, *company_values)

	# ── KPI 1: Total Active Requests ─────────────────────────────────────
	total_active = frappe.db.sql(
		f"""
		SELECT COUNT(*)
		FROM `tabPresales Request`
		WHERE 1=1
		{_nc_sql}
		{user_condition}
		{all_extra}
		{company_condition}
		""",
		_vals(),
	)[0][0] or 0

	# ── KPI 2: Total Pipeline Value (active) ─────────────────────────────
	total_pipeline = frappe.db.sql(
		f"""
		SELECT COALESCE(SUM(estimated_value), 0)
		FROM `tabPresales Request`
		WHERE 1=1
		{_nc_sql}
		{user_condition}
		{all_extra}
		{company_condition}
		""",
		_vals(),
	)[0][0] or 0

	# ── KPI 3: Overdue Count ─────────────────────────────────────────────
	overdue_count = frappe.db.sql(
		f"""
		SELECT COUNT(*)
		FROM `tabPresales Request`
		WHERE overdue = 1
		{_nc_sql}
		{user_condition}
		{all_extra}
		{company_condition}
		""",
		_vals(),
	)[0][0] or 0

	# ── KPI 4: Due This Period ────────────────────────────────────────────
	due_period_count = frappe.db.sql(
		f"""
		SELECT COUNT(*)
		FROM `tabPresales Request`
		WHERE due_date BETWEEN %s AND %s
		{_nc_sql}
		{user_condition}
		{all_extra}
		{company_condition}
		""",
		_vals(due_start, due_end),
	)[0][0] or 0

	# ── KPI 5: Avg Quality Score (completed) ─────────────────────────────
	avg_quality = frappe.db.sql(
		f"""
		SELECT COALESCE(AVG(quality_score), 0)
		FROM `tabPresales Request`
		WHERE status = 'Completed'
		  AND quality_score > 0
		{user_condition}
		{company_condition}
		""",
		(*user_values, *company_values),
	)[0][0] or 0

	# ── KPI 6: Completed This Month ───────────────────────────────────────
	completed_month = frappe.db.sql(
		f"""
		SELECT COUNT(*)
		FROM `tabPresales Request`
		WHERE status = 'Completed'
		  AND completion_date BETWEEN %s AND %s
		{user_condition}
		{all_extra}
		{company_condition}
		""",
		_vals_plain(month_start, month_end),
	)[0][0] or 0

	# ── Pipeline by Status ────────────────────────────────────────────────
	status_data = frappe.db.sql(
		f"""
		SELECT status,
		       COALESCE(SUM(estimated_value), 0) AS amount,
		       COUNT(*) AS count
		FROM `tabPresales Request`
		WHERE 1=1
		{_nc_sql}
		{user_condition}
		{all_extra}
		{company_condition}
		GROUP BY status
		ORDER BY amount DESC
		""",
		_vals(),
		as_dict=True,
	)

	# ── Pipeline by Priority ──────────────────────────────────────────────
	priority_data = frappe.db.sql(
		f"""
		SELECT priority,
		       COALESCE(SUM(estimated_value), 0) AS amount,
		       COUNT(*) AS count
		FROM `tabPresales Request`
		WHERE 1=1
		{_nc_sql}
		{user_condition}
		{all_extra}
		{company_condition}
		GROUP BY priority
		ORDER BY FIELD(priority, 'Critical', 'High', 'Medium', 'Low')
		""",
		_vals(),
		as_dict=True,
	)

	# ── Owner-wise Pipeline ───────────────────────────────────────────────
	owner_data = frappe.db.sql(
		f"""
		SELECT presales_owner,
		       COALESCE(SUM(estimated_value), 0) AS amount,
		       COUNT(*) AS count
		FROM `tabPresales Request`
		WHERE presales_owner IS NOT NULL AND presales_owner != ''
		{_nc_sql}
		{user_condition}
		{all_extra}
		{company_condition}
		GROUP BY presales_owner
		ORDER BY amount DESC
		LIMIT 10
		""",
		_vals(),
		as_dict=True,
	)

	for row in owner_data:
		row.owner_short = (row.presales_owner or "Unassigned").split("@")[0].replace(".", " ").title()

	# ── Overdue List ──────────────────────────────────────────────────────
	overdue_list = frappe.db.sql(
		f"""
		SELECT name, customer, opportunity, status, priority,
		       estimated_value, due_date, delay_days, presales_owner
		FROM `tabPresales Request`
		WHERE overdue = 1
		{_nc_sql}
		{user_condition}
		{all_extra}
		{company_condition}
		ORDER BY delay_days DESC
		LIMIT 8
		""",
		_vals(),
		as_dict=True,
	)

	for row in overdue_list:
		if row.due_date:
			row.due_display = getdate(row.due_date).strftime("%d-%b")
		row.owner_short = (row.presales_owner or "Unassigned").split("@")[0].replace(".", " ").title()

	# ── Due This Period List ──────────────────────────────────────────────
	due_list = frappe.db.sql(
		f"""
		SELECT name, customer, opportunity, status, priority,
		       estimated_value, due_date, expected_close_date, presales_owner
		FROM `tabPresales Request`
		WHERE due_date BETWEEN %s AND %s
		{_nc_sql}
		{user_condition}
		{all_extra}
		{company_condition}
		ORDER BY due_date ASC
		LIMIT 8
		""",
		_vals(due_start, due_end),
		as_dict=True,
	)

	for row in due_list:
		if row.due_date:
			row.due_display = getdate(row.due_date).strftime("%d-%b")
		row.owner_short = (row.presales_owner or "Unassigned").split("@")[0].replace(".", " ").title()

	# ── No Updates in 7 Days ─────────────────────────────────────────────
	no_update_count = frappe.db.sql(
		f"""
		SELECT COUNT(*)
		FROM `tabPresales Request`
		WHERE modified < %s
		{_nc_sql}
		{user_condition}
		{all_extra}
		{company_condition}
		""",
		_vals(seven_days_ago),
	)[0][0] or 0

	# ── High-Value Active Requests ────────────────────────────────────────
	highval_list = frappe.db.sql(
		f"""
		SELECT name, customer, opportunity, status, priority,
		       estimated_value, expected_close_date, presales_owner,
		       actual_hours, estimated_hours,
		       decision_maker_known, budget_confirmed
		FROM `tabPresales Request`
		WHERE estimated_value > 0
		{_nc_sql}
		{user_condition}
		{all_extra}
		{company_condition}
		ORDER BY estimated_value DESC
		LIMIT 8
		""",
		_vals(),
		as_dict=True,
	)

	for row in highval_list:
		if row.expected_close_date:
			row.close_display = getdate(row.expected_close_date).strftime("%d-%b-%y")
		row.owner_short = (row.presales_owner or "Unassigned").split("@")[0].replace(".", " ").title()

	# ── Completion Stats (hours efficiency) ───────────────────────────────
	# Include all statuses except Cancelled — hours on Won/Completed are valid
	_nc_hours_sql  = " AND status != 'Cancelled'"
	hours_data = frappe.db.sql(
		f"""
		SELECT presales_owner,
		       COALESCE(SUM(actual_hours), 0)    AS actual,
		       COALESCE(SUM(estimated_hours), 0) AS estimated,
		       COUNT(*) AS count
		FROM `tabPresales Request`
		WHERE 1=1
		{_nc_hours_sql}
		{user_condition}
		{company_condition}
		GROUP BY presales_owner
		ORDER BY actual DESC
		LIMIT 8
		""",
		(*user_values, *company_values),
		as_dict=True,
	)

	for row in hours_data:
		row.owner_short = (row.presales_owner or "Unassigned").split("@")[0].replace(".", " ").title()
		row.efficiency  = round((row.estimated / row.actual * 100), 1) if row.actual > 0 else 0

	return {
		"kpis": {
			"total_active":     int(total_active),
			"total_pipeline":   float(total_pipeline),
			"overdue_count":    int(overdue_count),
			"due_period_count": int(due_period_count),
			"avg_quality":      round(float(avg_quality), 1),
			"completed_month":  int(completed_month),
			"no_update_count":  int(no_update_count),
		},
		"status_data":    status_data,
		"priority_data":  priority_data,
		"owner_data":     owner_data,
		"overdue_list":   overdue_list,
		"due_list":       due_list,
		"highval_list":   highval_list,
		"hours_data":     hours_data,
		"is_manager":     can_filter,
		"currency":       currency,
		"active_filters": {
			"selected_user":     selected_user,
			"selected_status":   selected_status,
			"selected_priority": selected_priority,
			"from_date":         due_start,
			"to_date":           due_end,
			"is_custom_date":    bool(from_date or to_date),
		},
		"generated_at": frappe.utils.now_datetime().strftime("%d %b %Y, %I:%M %p"),
	}