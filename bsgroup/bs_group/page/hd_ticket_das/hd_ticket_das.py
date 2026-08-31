import frappe
from frappe.utils import today, getdate, get_first_day, get_last_day

# HD Ticket uses Frappe's built-in `_assign` JSON field (e.g. '["user@example.com"]')
# There is no separate assignee child table in this version of Frappe Helpdesk.


@frappe.whitelist()
def get_helpdesk_agents():
	"""Return distinct agents from the _assign JSON field on HD Ticket."""
	user  = frappe.session.user
	roles = frappe.get_roles(user)

	if "System Manager" in roles or "HD Manager" in roles or "Support Manager" in roles:
		# _assign stores a JSON array; pull every distinct email out via JSON_TABLE (MySQL 8+)
		# Fallback: return users who appear anywhere in the _assign column
		return frappe.db.sql(
			"""
			SELECT DISTINCT jt.agent AS agent
			FROM `tabHD Ticket` t,
			     JSON_TABLE(
			         IF(t._assign IS NULL OR t._assign = '', '[]', t._assign),
			         '$[*]' COLUMNS (agent VARCHAR(200) PATH '$')
			     ) jt
			WHERE jt.agent IS NOT NULL AND jt.agent != ''
			ORDER BY jt.agent
			""",
			as_dict=True,
		)
	return []


@frappe.whitelist()
def get_dashboard_data(
	selected_agent=None,
	from_date=None,
	to_date=None,
	selected_status=None,
	selected_priority=None,
):
	user  = frappe.session.user
	roles = frappe.get_roles(user)

	is_manager = (
		"System Manager" in roles
		or "HD Manager"      in roles
		or "Support Manager" in roles
	)

	today_date  = today()
	month_start = str(get_first_day(today_date))
	month_end   = str(get_last_day(today_date))
	date_start  = from_date if from_date else month_start
	date_end    = to_date   if to_date   else month_end

	# ── Agent filter using JSON_CONTAINS on _assign ───────────────────────
	# _assign example value: '["antony@example.com","karthik@example.com"]'
	agent_condition = ""
	agent_values    = []

	if is_manager and selected_agent:
		agent_condition = " AND JSON_CONTAINS(_assign, JSON_QUOTE(%s))"
		agent_values    = [selected_agent]
	elif not is_manager:
		agent_condition = " AND JSON_CONTAINS(_assign, JSON_QUOTE(%s))"
		agent_values    = [user]

	# ── Extra filters ─────────────────────────────────────────────────────
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

	def _v(*prepend):
		return (*prepend, *agent_values, *extra_values)

	def _v_plain(*prepend):
		return (*prepend, *agent_values)

	# ── Unassigned: _assign is NULL, empty string, or empty JSON array ────
	unassigned_cond = "(_assign IS NULL OR _assign = '' OR _assign = '[]')"

	# ── KPI: Open ────────────────────────────────────────────────────────
	open_count = frappe.db.sql(
		f"SELECT COUNT(*) FROM `tabHD Ticket` WHERE status = 'Open' {agent_condition}{all_extra}",
		_v()
	)[0][0] or 0

	# ── KPI: Total in date range ──────────────────────────────────────────
	total_count = frappe.db.sql(
		f"SELECT COUNT(*) FROM `tabHD Ticket` WHERE creation BETWEEN %s AND %s {agent_condition}{all_extra}",
		_v(date_start, date_end)
	)[0][0] or 0

	# ── KPI: Replied ─────────────────────────────────────────────────────
	replied_count = frappe.db.sql(
		f"SELECT COUNT(*) FROM `tabHD Ticket` WHERE status = 'Replied' {agent_condition}{all_extra}",
		_v()
	)[0][0] or 0

	# ── KPI: Urgent ───────────────────────────────────────────────────────
	urgent_count = frappe.db.sql(
		f"""SELECT COUNT(*) FROM `tabHD Ticket`
		WHERE priority = 'Urgent' AND status NOT IN ('Resolved','Closed')
		{agent_condition}{all_extra}""",
		_v()
	)[0][0] or 0

	# ── KPI: High ────────────────────────────────────────────────────────
	high_count = frappe.db.sql(
		f"""SELECT COUNT(*) FROM `tabHD Ticket`
		WHERE priority = 'High' AND status NOT IN ('Resolved','Closed')
		{agent_condition}{all_extra}""",
		_v()
	)[0][0] or 0

	urgent_high_count = urgent_count + high_count

	# ── KPI: SLA Failed ──────────────────────────────────────────────────
	sla_failed = frappe.db.sql(
		f"SELECT COUNT(*) FROM `tabHD Ticket` WHERE agreement_status = 'Failed' {agent_condition}{all_extra}",
		_v()
	)[0][0] or 0

	# ── KPI: SLA Near Breach ─────────────────────────────────────────────
	sla_near_breach = frappe.db.sql(
		f"""SELECT COUNT(*) FROM `tabHD Ticket`
		WHERE agreement_status IN ('First Response Due','Resolution Due')
		{agent_condition}{all_extra}""",
		_v()
	)[0][0] or 0

	# ── KPI: SLA Fulfilled ────────────────────────────────────────────────
	sla_fulfilled = frappe.db.sql(
		f"SELECT COUNT(*) FROM `tabHD Ticket` WHERE agreement_status = 'Fulfilled' {agent_condition}{all_extra}",
		_v()
	)[0][0] or 0

	# ── KPI: Resolved this month ──────────────────────────────────────────
	resolved_month = frappe.db.sql(
		f"""SELECT COUNT(*) FROM `tabHD Ticket`
		WHERE status IN ('Resolved','Closed') AND modified BETWEEN %s AND %s
		{agent_condition}""",
		_v_plain(month_start, month_end)
	)[0][0] or 0

	# ── KPI: Avg first response (seconds) ─────────────────────────────────
	avg_first_response = frappe.db.sql(
		f"""SELECT COALESCE(AVG(first_response_time), 0)
		FROM `tabHD Ticket`
		WHERE first_response_time IS NOT NULL AND first_response_time > 0
		  AND creation BETWEEN %s AND %s
		{agent_condition}""",
		_v_plain(month_start, month_end)
	)[0][0] or 0

	# ── KPI: Avg feedback ─────────────────────────────────────────────────
	avg_feedback = frappe.db.sql(
		f"SELECT COALESCE(AVG(feedback_rating), 0) FROM `tabHD Ticket` WHERE feedback_rating > 0 {agent_condition}",
		_v_plain()
	)[0][0] or 0

	# ── KPI: Via portal ───────────────────────────────────────────────────
	portal_count = frappe.db.sql(
		f"SELECT COUNT(*) FROM `tabHD Ticket` WHERE via_customer_portal = 1 {agent_condition}{all_extra}",
		_v()
	)[0][0] or 0

	# ── KPI: Merged ───────────────────────────────────────────────────────
	merged_count = frappe.db.sql(
		f"SELECT COUNT(*) FROM `tabHD Ticket` WHERE is_merged = 1 {agent_condition}{all_extra}",
		_v()
	)[0][0] or 0

	# ── KPI: Next Action Overdue ──────────────────────────────────────────
	next_action_overdue = frappe.db.sql(
		f"""SELECT COUNT(*) FROM `tabHD Ticket`
		WHERE custom_next_action_date IS NOT NULL
		  AND custom_next_action_date < %s
		  AND status NOT IN ('Resolved','Closed')
		{agent_condition}{all_extra}""",
		_v(today_date)
	)[0][0] or 0

	# ── KPI: Next Action Due Today ────────────────────────────────────────
	next_action_today = frappe.db.sql(
		f"""SELECT COUNT(*) FROM `tabHD Ticket`
		WHERE custom_next_action_date = %s
		  AND status NOT IN ('Resolved','Closed')
		{agent_condition}{all_extra}""",
		_v(today_date)
	)[0][0] or 0

	# ── KPI: Unassigned ───────────────────────────────────────────────────
	unassigned_count = frappe.db.sql(
		f"""SELECT COUNT(*) FROM `tabHD Ticket`
		WHERE {unassigned_cond} AND status NOT IN ('Resolved','Closed')
		{all_extra}""",
		tuple(extra_values)
	)[0][0] or 0

	# ── Priority Action Queue ─────────────────────────────────────────────
	priority_queue = frappe.db.sql(
		f"""
		SELECT name, subject, status, priority, agreement_status,
		       custom_category, custom_next_action, custom_next_action_date, creation,
		       raised_by, customer, _assign
		FROM `tabHD Ticket`
		WHERE priority IN ('Urgent','High')
		  AND status NOT IN ('Resolved','Closed')
		{agent_condition}{all_extra}
		ORDER BY FIELD(priority,'Urgent','High'), creation ASC
		LIMIT 10
		""", _v(), as_dict=True
	)

	for row in priority_queue:
		if row.creation:
			delta = frappe.utils.time_diff_in_seconds(frappe.utils.now(), str(row.creation))
			h = int(delta // 3600)
			row.age_display = f"{h}h ago" if h < 24 else f"{int(h // 24)}d ago"
		# Parse _assign JSON array for display
		import json
		try:
			agents = json.loads(row._assign or "[]")
			short  = [a.split("@")[0].replace(".", " ").title() for a in agents]
			row.agent_short = ", ".join(short[:2]) or "Unassigned"
		except Exception:
			row.agent_short = "Unassigned"

	# ── Category breakdown ────────────────────────────────────────────────
	category_data = frappe.db.sql(
		f"""
		SELECT
			COALESCE(NULLIF(custom_category,''), 'Unspecified') AS category,
			COUNT(*) AS count,
			SUM(CASE WHEN agreement_status = 'Failed' THEN 1 ELSE 0 END) AS sla_failed_count,
			MAX(agreement_status) AS sla_status
		FROM `tabHD Ticket`
		WHERE status NOT IN ('Resolved','Closed')
		{agent_condition}{all_extra}
		GROUP BY custom_category
		ORDER BY count DESC
		LIMIT 8
		""", _v(), as_dict=True
	)

	# ── Agent workload via JSON_TABLE (MySQL 8+) ──────────────────────────
	# Expands _assign array into rows so we can group by individual agent
	join_extra = all_extra.replace(" AND status", " AND t.status").replace(" AND priority", " AND t.priority")

	agent_data = frappe.db.sql(
		f"""
		SELECT
			jt.agent,
			SUM(CASE WHEN t.status = 'Open'    THEN 1 ELSE 0 END) AS open_count,
			SUM(CASE WHEN t.status = 'Replied' THEN 1 ELSE 0 END) AS replied_count,
			SUM(CASE WHEN t.agreement_status = 'Failed'    THEN 1 ELSE 0 END) AS overdue_count,
			SUM(CASE WHEN t.agreement_status = 'Fulfilled' THEN 1 ELSE 0 END) AS sla_ok,
			COUNT(*) AS total,
			COALESCE(AVG(t.first_response_time), 0) AS avg_first_response
		FROM `tabHD Ticket` t,
		     JSON_TABLE(
		         IF(t._assign IS NULL OR t._assign = '' OR t._assign = '[]', '[""]', t._assign),
		         '$[*]' COLUMNS (agent VARCHAR(200) PATH '$')
		     ) jt
		WHERE jt.agent IS NOT NULL AND jt.agent != ''
		{join_extra}
		GROUP BY jt.agent
		ORDER BY open_count DESC
		LIMIT 10
		""", tuple(extra_values), as_dict=True
	)

	for row in agent_data:
		row.agent_short = (row.agent or "").split("@")[0].replace(".", " ").title()
		row.sla_pct     = round(row.sla_ok / row.total * 100, 1) if row.total > 0 else 0

	# ── Recent activity ───────────────────────────────────────────────────
	recent_activity = frappe.db.sql(
		f"""
		SELECT name, subject, status, priority, customer, raised_by, modified
		FROM `tabHD Ticket`
		WHERE 1=1
		{agent_condition}{all_extra}
		ORDER BY modified DESC
		LIMIT 8
		""", _v(), as_dict=True
	)

	for row in recent_activity:
		if row.modified:
			delta = frappe.utils.time_diff_in_seconds(frappe.utils.now(), str(row.modified))
			h = int(delta // 3600)
			row.age_display = f"{h}h ago" if h < 24 else f"{int(h // 24)}d ago"

	# ── Customer volume ───────────────────────────────────────────────────
	customer_data = frappe.db.sql(
		f"""
		SELECT
			customer,
			COUNT(*) AS total,
			SUM(CASE WHEN status NOT IN ('Resolved','Closed') THEN 1 ELSE 0 END) AS open_count,
			MAX(agreement_status) AS agreement_status,
			MAX(creation) AS last_ticket
		FROM `tabHD Ticket`
		WHERE customer IS NOT NULL AND customer != ''
		{agent_condition}{all_extra}
		GROUP BY customer
		ORDER BY total DESC
		LIMIT 8
		""", _v(), as_dict=True
	)

	for row in customer_data:
		if row.last_ticket:
			row.last_ticket = getdate(row.last_ticket).strftime("%d-%b-%y")

	# ── Agent group load ──────────────────────────────────────────────────
	agent_group_data = frappe.db.sql(
		f"""
		SELECT
			COALESCE(NULLIF(agent_group,''), 'Unassigned') AS agent_group,
			COUNT(*) AS count
		FROM `tabHD Ticket`
		WHERE status NOT IN ('Resolved','Closed')
		{agent_condition}{all_extra}
		GROUP BY agent_group
		ORDER BY count DESC
		LIMIT 8
		""", _v(), as_dict=True
	)

	return {
		"kpis": {
			"open_count":         int(open_count),
			"total_count":        int(total_count),
			"replied_count":      int(replied_count),
			"urgent_count":       int(urgent_count),
			"high_count":         int(high_count),
			"urgent_high_count":  int(urgent_high_count),
			"sla_failed":         int(sla_failed),
			"sla_near_breach":    int(sla_near_breach),
			"sla_fulfilled":      int(sla_fulfilled),
			"resolved_month":     int(resolved_month),
			"avg_first_response": int(avg_first_response),
			"avg_feedback":       round(float(avg_feedback), 1),
			"portal_count":       int(portal_count),
			"merged_count":          int(merged_count),
			"next_action_overdue":   int(next_action_overdue),
			"next_action_today":     int(next_action_today),
			"unassigned_count":   int(unassigned_count),
		},
		"priority_queue":   priority_queue,
		"category_data":    category_data,
		"agent_data":       agent_data,
		"recent_activity":  recent_activity,
		"customer_data":    customer_data,
		"agent_group_data": agent_group_data,
		"is_manager":       is_manager,
		"active_filters": {
			"selected_agent":    selected_agent,
			"selected_status":   selected_status,
			"selected_priority": selected_priority,
			"from_date":         date_start,
			"to_date":           date_end,
			"is_custom_date":    bool(from_date or to_date),
		},
		"generated_at": frappe.utils.now_datetime().strftime("%d %b %Y, %I:%M %p"),
	}