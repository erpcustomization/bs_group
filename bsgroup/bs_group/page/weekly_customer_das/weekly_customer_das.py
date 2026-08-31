import frappe
from frappe.utils import today, add_days, getdate, get_first_day, get_last_day, nowdate


# ── Helper: short name from email ─────────────────────────────────────────
def _short(email):
	if not email:
		return "Unassigned"
	return email.split("@")[0].replace(".", " ").title()


# ── List projects visible to the current user ─────────────────────────────
@frappe.whitelist()
def get_projects():
	"""Return projects the current user is associated with or can manage."""
	user  = frappe.session.user
	roles = frappe.get_roles(user)

	# Managers and System Admins see all active projects
	if "System Manager" in roles or "Projects Manager" in roles or "Project Manager" in roles:
		return frappe.db.sql(
			"""
			SELECT name, project_name, status, project_type, company
			FROM `tabProject`
			WHERE status != 'Cancelled'
			ORDER BY modified DESC
			LIMIT 200
			""",
			as_dict=True,
		)

	# Regular users see only projects they are members of or own
	member_projects = frappe.db.sql(
		"""
		SELECT DISTINCT p.name, p.project_name, p.status, p.project_type, p.company
		FROM `tabProject` p
		LEFT JOIN `tabProject User` pu ON pu.parent = p.name
		WHERE (pu.user = %(user)s OR p.owner = %(user)s)
		  AND p.status != 'Cancelled'
		ORDER BY p.modified DESC
		LIMIT 200
		""",
		{"user": user},
		as_dict=True,
	)

	return member_projects


# ── Main dashboard data ───────────────────────────────────────────────────
@frappe.whitelist()
def get_dashboard_data(project, from_date=None, to_date=None, selected_status=None):
	"""
	Return all data needed to render the project weekly dashboard.
	"""
	if not project:
		frappe.throw("Project is required")

	_today     = today()
	_week_ago  = add_days(_today, -7)
	_week_next = add_days(_today, 7)

	period_start = from_date if from_date else _week_ago
	period_end   = to_date   if to_date   else _today
	next_start   = period_end
	next_end     = add_days(period_end, 7)

	# ── Project details ───────────────────────────────────────────────────
	proj = frappe.db.get_value(
		"Project",
		project,
		[
			"name", "project_name", "status", "project_type",
			"is_active", "percent_complete", "priority", "company",
			"expected_start_date", "expected_end_date", "owner",
			"customer", "custom_project_description",
		],
		as_dict=True,
	)

	if not proj:
		frappe.throw(f"Project {project} not found")

	# ── Project manager (first project-user with Is Project Manager ticked, else owner) ──
	pm_user = frappe.db.get_value(
		"Project User",
		{"parent": project, "view_attachments": 1},
		"user",
	) or proj.owner or ""
	project_manager = _short(pm_user)

	# ── Status filter clause ──────────────────────────────────────────────
	status_cond  = ""
	status_vals  = []
	if selected_status:
		status_cond = " AND t.status = %s"
		status_vals = [selected_status]

	# ── KPI 1: Total tasks in project ────────────────────────────────────
	all_tasks = frappe.db.sql(
		f"""
		SELECT COUNT(*) FROM `tabTask` t
		WHERE t.project = %s AND t.is_group = 0
		{status_cond}
		""",
		[project] + status_vals,
	)[0][0] or 0

	# ── KPI 2: Open tasks ─────────────────────────────────────────────────
	open_tasks = frappe.db.sql(
		f"""
		SELECT COUNT(*) FROM `tabTask` t
		WHERE t.project = %s
		  AND t.is_group = 0
		  AND t.status NOT IN ('Completed', 'Cancelled')
		{status_cond}
		""",
		[project] + status_vals,
	)[0][0] or 0

	# ── KPI 3: Completed in period ────────────────────────────────────────
	completed_period = frappe.db.sql(
		f"""
		SELECT COUNT(*) FROM `tabTask` t
		WHERE t.project = %s
		  AND t.is_group = 0
		  AND t.status = 'Completed'
		  AND t.completed_on BETWEEN %s AND %s
		{status_cond}
		""",
		[project, period_start, period_end] + status_vals,
	)[0][0] or 0

	# ── KPI 4: Overdue tasks ──────────────────────────────────────────────
	overdue_tasks = frappe.db.sql(
		f"""
		SELECT COUNT(*) FROM `tabTask` t
		WHERE t.project = %s
		  AND t.is_group = 0
		  AND t.status NOT IN ('Completed', 'Cancelled')
		  AND t.exp_end_date < %s
		  AND t.exp_end_date IS NOT NULL
		{status_cond}
		""",
		[project, _today] + status_vals,
	)[0][0] or 0

	# ── Completed tasks this period (list) ────────────────────────────────
	completed_tasks = frappe.db.sql(
		f"""
		SELECT t.name, t.subject, t.status, t.priority,
		       t.completed_on, t.parent_task,
		       t.exp_end_date, t.progress
		FROM `tabTask` t
		WHERE t.project = %s
		  AND t.is_group = 0
		  AND t.status = 'Completed'
		  AND t.completed_on BETWEEN %s AND %s
		{status_cond}
		ORDER BY t.completed_on DESC
		LIMIT 8
		""",
		[project, period_start, period_end] + status_vals,
		as_dict=True,
	)

	# Enrich with parent label
	for row in completed_tasks:
		if row.parent_task:
			row.parent_label = frappe.db.get_value("Task", row.parent_task, "subject") or ""
		else:
			row.parent_label = ""

	# ── Planned next period (list) ────────────────────────────────────────
	planned_tasks = frappe.db.sql(
		f"""
		SELECT t.name, t.subject, t.status, t.priority,
		       t.exp_start_date, t.exp_end_date, t.progress, t.parent_task
		FROM `tabTask` t
		WHERE t.project = %s
		  AND t.is_group = 0
		  AND t.status NOT IN ('Completed', 'Cancelled')
		  AND (
		      t.exp_start_date BETWEEN %s AND %s
		      OR t.exp_end_date BETWEEN %s AND %s
		  )
		{status_cond}
		ORDER BY t.exp_end_date ASC
		LIMIT 8
		""",
		[project, next_start, next_end, next_start, next_end] + status_vals,
		as_dict=True,
	)

	for row in planned_tasks:
		if row.parent_task:
			row.parent_label = frappe.db.get_value("Task", row.parent_task, "subject") or ""
		else:
			row.parent_label = ""

	# ── Open / overdue items (key open items panel) ────────────────────────
	open_items = frappe.db.sql(
		f"""
		SELECT t.name, t.subject, t.status, t.priority,
		       t.exp_end_date, t.progress, t.parent_task
		FROM `tabTask` t
		WHERE t.project = %s
		  AND t.is_group = 0
		  AND t.status NOT IN ('Completed', 'Cancelled')
		{status_cond}
		ORDER BY
		  CASE WHEN t.exp_end_date < %s THEN 0 ELSE 1 END ASC,
		  CASE t.priority
		    WHEN 'Urgent' THEN 0 WHEN 'High' THEN 1 WHEN 'Medium' THEN 2 ELSE 3
		  END ASC,
		  t.exp_end_date ASC
		LIMIT 8
		""",
		[project] + status_vals + [_today],
		as_dict=True,
	)

	for row in open_items:
		row.is_overdue = bool(
			row.exp_end_date and getdate(row.exp_end_date) < getdate(_today)
		)
		if row.parent_task:
			row.parent_label = frappe.db.get_value("Task", row.parent_task, "subject") or ""
		else:
			row.parent_label = ""

	# ── Scope / Task Groups (parent tasks with is_group = 1) ─────────────
	scope_groups = frappe.db.sql(
		"""
		SELECT t.name, t.subject, t.status, t.progress
		FROM `tabTask` t
		WHERE t.project = %s
		  AND t.is_group = 1
		  AND (t.parent_task IS NULL OR t.parent_task = '')
		ORDER BY t.lft ASC
		LIMIT 12
		""",
		[project],
		as_dict=True,
	)

	for group in scope_groups:
		# Compute progress from child tasks
		child_stats = frappe.db.sql(
			"""
			SELECT COUNT(*) AS total,
			       SUM(CASE WHEN status = 'Completed' THEN 1 ELSE 0 END) AS done
			FROM `tabTask`
			WHERE parent_task = %s AND is_group = 0
			""",
			[group.name],
			as_dict=True,
		)
		if child_stats and child_stats[0].total:
			grp_total = child_stats[0].total
			grp_done  = child_stats[0].done or 0
			group.progress = round((grp_done / grp_total) * 100)
		else:
			group.progress = int(group.progress or 0)

		# Remark based on status / progress
		pct = group.progress
		if group.status == "Completed" or pct >= 100:
			group.remark = "Completed"
		elif pct >= 75:
			group.remark = "Near completion"
		elif pct >= 40:
			group.remark = "In progress"
		elif pct > 0:
			group.remark = "Started"
		else:
			group.remark = "Not started"

	# ── Milestones (tasks with is_milestone = 1) ──────────────────────────
	milestones = frappe.db.sql(
		"""
		SELECT t.name, t.subject, t.status, t.progress,
		       t.exp_end_date, t.completed_on
		FROM `tabTask` t
		WHERE t.project = %s
		  AND t.is_milestone = 1
		ORDER BY t.exp_end_date ASC
		LIMIT 10
		""",
		[project],
		as_dict=True,
	)

	for m in milestones:
		if m.status == "Completed":
			m.progress = 100
		else:
			m.progress = int(m.progress or 0)

	# If no milestone tasks, fall back to scope groups for milestone display
	if not milestones:
		milestones = []

	return {
		"project": proj,
		"project_manager": project_manager,
		"kpis": {
			"all_tasks":        int(all_tasks),
			"open_tasks":       int(open_tasks),
			"completed_period": int(completed_period),
			"overdue_tasks":    int(overdue_tasks),
		},
		"completed_tasks": completed_tasks,
		"planned_tasks":   planned_tasks,
		"open_items":      open_items,
		"scope_groups":    scope_groups,
		"milestones":      milestones,
		"filters": {
			"from_date": period_start,
			"to_date":   period_end,
		},
		"generated_at": frappe.utils.now_datetime().strftime("%d %b %Y, %I:%M %p"),
	}