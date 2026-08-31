import frappe
from frappe.utils import today, getdate, get_first_day, get_last_day

CLOSED_STATUSES = ("Cancelled", "Rejected")
ACTIVE_STATUSES = (
    "Draft", "Pending Pre-Approval", "Pre-Approved",
    "Prepared", "Pending Signature", "Signed", "Issued"
)


def _get_team_users(user):
    employee = frappe.db.get_value("Employee", {"user_id": user}, "name")
    team = []
    if employee:
        team = frappe.get_all("Employee", filters={"reports_to": employee}, pluck="user_id")
    team.append(user)
    return team


@frappe.whitelist()
def get_cheque_users():
    user  = frappe.session.user
    roles = frappe.get_roles(user)

    if "System Manager" in roles:
        return frappe.db.sql(
            "SELECT DISTINCT requested_by AS user FROM `tabCheque Request` "
            "WHERE requested_by IS NOT NULL AND requested_by != '' ORDER BY requested_by",
            as_dict=True,
        )
    if "Accounts Manager" in roles:
        team = _get_team_users(user)
        ph   = ", ".join(["%s"] * len(team))
        return frappe.db.sql(
            f"SELECT DISTINCT requested_by AS user FROM `tabCheque Request` "
            f"WHERE requested_by IN ({ph}) AND requested_by IS NOT NULL ORDER BY requested_by",
            team, as_dict=True,
        )
    return []


@frappe.whitelist()
def get_departments():
    return frappe.db.sql(
        "SELECT DISTINCT department FROM `tabCheque Request` "
        "WHERE department IS NOT NULL AND department != '' ORDER BY department",
        as_dict=True,
    )


@frappe.whitelist()
def get_dashboard_data(
    selected_user=None,
    from_date=None,
    to_date=None,
    selected_status=None,
    selected_department=None,
):
    user  = frappe.session.user
    roles = frappe.get_roles(user)

    is_manager = "System Manager" in roles or "Accounts Manager" in roles
    today_date  = today()
    month_start = str(get_first_day(today_date))
    month_end   = str(get_last_day(today_date))
    due_start   = from_date if from_date else month_start
    due_end     = to_date   if to_date   else month_end

    # ── User filter ──────────────────────────────────────────────────────────
    user_cond, user_vals = "", []
    if "System Manager" in roles:
        if selected_user:
            user_cond = " AND requested_by = %s"
            user_vals = [selected_user]
    elif is_manager:
        if selected_user:
            user_cond = " AND requested_by = %s"
            user_vals = [selected_user]
        else:
            team      = _get_team_users(user)
            ph        = ", ".join(["%s"] * len(team))
            user_cond = f" AND requested_by IN ({ph})"
            user_vals = team
    else:
        user_cond = " AND requested_by = %s"
        user_vals = [user]

    # ── Extra filters ────────────────────────────────────────────────────────
    status_cond = f" AND status = %s" if selected_status else ""
    dept_cond   = f" AND department = %s" if selected_department else ""
    extra_vals  = (
        ([selected_status] if selected_status else []) +
        ([selected_department] if selected_department else [])
    )

    def _v(*pre):
        return (*pre, *user_vals, *extra_vals)

    def _dept_v(*pre):
        return (*pre, *user_vals, *([selected_department] if selected_department else []))

    # ── KPIs ─────────────────────────────────────────────────────────────────
    def _count(where, vals):
        return frappe.db.sql(f"SELECT COUNT(*) FROM `tabCheque Request` WHERE {where}", vals)[0][0] or 0

    def _sum(where, vals):
        return frappe.db.sql(f"SELECT COALESCE(SUM(amount),0) FROM `tabCheque Request` WHERE {where}", vals)[0][0] or 0

    pending_count  = _count(f"status = 'Pending Pre-Approval' {user_cond} {dept_cond}", _dept_v())
    pending_amount = _sum(f"status = 'Pending Pre-Approval' {user_cond} {dept_cond}", _dept_v())

    pre_approved_count  = _count(f"status = 'Pre-Approved' {user_cond} {dept_cond}", _dept_v())
    pre_approved_amount = _sum(f"status = 'Pre-Approved' {user_cond} {dept_cond}", _dept_v())

    issued_count  = _count(f"status = 'Issued' AND issued_on BETWEEN %s AND %s {user_cond} {dept_cond}", _dept_v(due_start, due_end))
    issued_amount = _sum(f"status = 'Issued' AND issued_on BETWEEN %s AND %s {user_cond} {dept_cond}", _dept_v(due_start, due_end))

    rejected_count = _count(f"status = 'Rejected' AND modified BETWEEN %s AND %s {user_cond} {dept_cond}", _dept_v(due_start, due_end))

    overdue_count = frappe.db.sql(
        f"SELECT COUNT(*) FROM `tabCheque Request` "
        f"WHERE cheque_date < %s AND status IN ('Pending Pre-Approval','Pre-Approved','Prepared','Pending Signature') "
        f"{user_cond} {dept_cond}",
        (today_date, *user_vals, *([selected_department] if selected_department else [])),
    )[0][0] or 0

    in_progress_count  = _count(f"status IN ('Prepared','Pending Signature','Signed') {user_cond} {dept_cond}", _dept_v())
    in_progress_amount = _sum(f"status IN ('Prepared','Pending Signature','Signed') {user_cond} {dept_cond}", _dept_v())

    # ── Amount by Status ──────────────────────────────────────────────────────
    status_data = frappe.db.sql(
        f"SELECT status, COALESCE(SUM(amount),0) AS amount, COUNT(*) AS count "
        f"FROM `tabCheque Request` WHERE status NOT IN ('Cancelled','Rejected') "
        f"{user_cond} {status_cond} {dept_cond} "
        f"GROUP BY status ORDER BY amount DESC",
        _v(), as_dict=True,
    )

    # ── Dept performance (% issued of total active) ───────────────────────────
    dept_perf = frappe.db.sql(
        f"SELECT department, COUNT(*) AS total, "
        f"SUM(CASE WHEN status='Issued' THEN 1 ELSE 0 END) AS issued, "
        f"COALESCE(SUM(amount),0) AS amount "
        f"FROM `tabCheque Request` "
        f"WHERE department IS NOT NULL AND department != '' "
        f"{user_cond} {dept_cond} "
        f"GROUP BY department ORDER BY total DESC LIMIT 6",
        _dept_v(), as_dict=True,
    )
    for row in dept_perf:
        row.pct = round((row.issued / row.total * 100) if row.total else 0, 1)

    # ── Top requesters ────────────────────────────────────────────────────────
    requester_data = frappe.db.sql(
        f"SELECT requested_by, COALESCE(SUM(amount),0) AS amount, COUNT(*) AS count "
        f"FROM `tabCheque Request` WHERE requested_by IS NOT NULL "
        f"AND status NOT IN ('Cancelled','Rejected') "
        f"{user_cond} {status_cond} {dept_cond} "
        f"GROUP BY requested_by ORDER BY amount DESC LIMIT 8",
        _v(), as_dict=True,
    )
    for row in requester_data:
        row.requester_short = (row.requested_by or "Unknown").split("@")[0].replace(".", " ").title()

    # ── Approval Queue (all active, non-terminal) ─────────────────────────────
    queue_list = frappe.db.sql(
        f"SELECT name, payee_name, amount, department, bank_account, "
        f"cheque_date, requested_by, status, creation, "
        f"DATEDIFF(%s, DATE(creation)) AS age_days "
        f"FROM `tabCheque Request` "
        f"WHERE status NOT IN ('Cancelled','Rejected','Issued') "
        f"{user_cond} {status_cond} {dept_cond} "
        f"ORDER BY creation ASC LIMIT 15",
        (today_date, *user_vals, *extra_vals), as_dict=True,
    )
    for row in queue_list:
        row.requester_short = (row.requested_by or "Unknown").split("@")[0].replace(".", " ").title()
        if row.cheque_date:
            row.cheque_date_display = getdate(row.cheque_date).strftime("%d-%b-%y")

    # ── Overdue list ──────────────────────────────────────────────────────────
    overdue_list = frappe.db.sql(
        f"SELECT name, payee_name, amount, department, cheque_date, requested_by, status, "
        f"DATEDIFF(%s, cheque_date) AS overdue_days "
        f"FROM `tabCheque Request` "
        f"WHERE cheque_date < %s "
        f"AND status IN ('Pending Pre-Approval','Pre-Approved','Prepared','Pending Signature') "
        f"{user_cond} {dept_cond} "
        f"ORDER BY overdue_days DESC LIMIT 8",
        (today_date, today_date, *user_vals, *([selected_department] if selected_department else [])),
        as_dict=True,
    )
    for row in overdue_list:
        if row.cheque_date:
            row.cheque_date_display = getdate(row.cheque_date).strftime("%d-%b-%y")
        row.requester_short = (row.requested_by or "Unknown").split("@")[0].replace(".", " ").title()

    # ── Recently Issued ───────────────────────────────────────────────────────
    issued_list = frappe.db.sql(
        f"SELECT name, payee_name, amount, department, bank_account, issued_on, issued_by, requested_by "
        f"FROM `tabCheque Request` "
        f"WHERE status = 'Issued' AND issued_on BETWEEN %s AND %s "
        f"{user_cond} {dept_cond} "
        f"ORDER BY issued_on DESC LIMIT 8",
        (due_start, due_end, *user_vals, *([selected_department] if selected_department else [])),
        as_dict=True,
    )
    for row in issued_list:
        if row.issued_on:
            row.issued_on_display = getdate(str(row.issued_on)).strftime("%d-%b-%y")
        row.issued_by_short   = (row.issued_by or "—").split("@")[0].replace(".", " ").title()
        row.requester_short   = (row.requested_by or "Unknown").split("@")[0].replace(".", " ").title()

    # ── High-value pending ────────────────────────────────────────────────────
    highval_pending_amount = _sum(
        f"status NOT IN ('Cancelled','Rejected','Issued') AND amount > 0 {user_cond} {dept_cond}",
        _dept_v()
    )
    highval_pending_count = _count(
        f"status NOT IN ('Cancelled','Rejected','Issued') AND amount > 0 {user_cond} {dept_cond}",
        _dept_v()
    )

    # ── Aging: avg days pending per requester ─────────────────────────────────
    aging_data = frappe.db.sql(
        f"SELECT requested_by, COUNT(*) AS count, "
        f"ROUND(AVG(DATEDIFF(%s, creation)), 1) AS avg_days "
        f"FROM `tabCheque Request` "
        f"WHERE status = 'Pending Pre-Approval' {user_cond} {dept_cond} "
        f"GROUP BY requested_by ORDER BY avg_days DESC LIMIT 6",
        (today_date, *user_vals, *([selected_department] if selected_department else [])),
        as_dict=True,
    )
    for row in aging_data:
        row.requester_short = (row.requested_by or "Unknown").split("@")[0].replace(".", " ").title()

    return {
        "kpis": {
            "pending_count":        int(pending_count),
            "pending_amount":       float(pending_amount),
            "pre_approved_count":   int(pre_approved_count),
            "pre_approved_amount":  float(pre_approved_amount),
            "in_progress_count":    int(in_progress_count),
            "in_progress_amount":   float(in_progress_amount),
            "issued_count":         int(issued_count),
            "issued_amount":        float(issued_amount),
            "rejected_count":       int(rejected_count),
            "overdue_count":        int(overdue_count),
            "highval_pending_amount": float(highval_pending_amount),
            "highval_pending_count":  int(highval_pending_count),
        },
        "status_data":    status_data,
        "dept_perf":      dept_perf,
        "requester_data": requester_data,
        "queue_list":     queue_list,
        "overdue_list":   overdue_list,
        "issued_list":    issued_list,
        "aging_data":     aging_data,
        "is_manager":     is_manager,
        "active_filters": {
            "from_date":      due_start,
            "to_date":        due_end,
            "is_custom_date": bool(from_date or to_date),
        },
        "generated_at": frappe.utils.now_datetime().strftime("%d %b %Y, %I:%M %p"),
    }
