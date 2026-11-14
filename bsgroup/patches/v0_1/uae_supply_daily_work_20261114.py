"""Recover the seven approved, pre-integration work notes without replaying work."""
import frappe
from html.parser import HTMLParser
from bsgroup.project_daily_work import enabled, install
from bsgroup.project_plan import WORK_SUBJECT

PROJECT = "PROJ-2525"
DAY = "2026-11-14"
EXPECTED = {
    ("TASK-2026-00901", "12:27:03"): "Done",
    ("TASK-2026-00901", "12:27:34"): "Coordinated with sekhar and arranged a hdd",
    ("TASK-2026-00902", "12:28:03"): "Coordinated with sekhar and arranged a hdd",
    ("TASK-2026-00903", "12:28:26"): "Items collected by shalikram",
    ("TASK-2026-00904", "12:28:42"): "verfied the hdd model and size",
    ("TASK-2026-00905", "12:29:07"): "handed over to selvam",
    ("TASK-2026-00906", "12:29:22"): "handed over to selvam and he took it to the site",
}


class Text(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.parts = []
        self.feed(html)

    def handle_data(self, data):
        if data.strip():
            self.parts.append(data.strip())


def execute():
    if not enabled() or not frappe.db.exists("Project", PROJECT):
        return
    project = frappe.get_doc("Project", PROJECT)
    if project.project_name != "Supply Surveillance HDD - QTN-2026-01317":
        return
    install()
    notes = frappe.get_all("Comment", filters={"reference_doctype": "Task",
        "reference_name": ["in", sorted({key[0] for key in EXPECTED})],
        "comment_type": "Comment", "subject": WORK_SUBJECT,
        "creation": ["between", [DAY + " 12:27:00", DAY + " 12:30:00"]]},
        fields=["name", "reference_name", "creation", "comment_email", "comment_by", "content"],
        order_by="creation asc")
    assert len(notes) == len(EXPECTED), "Expected seven original work notes; no data changed"
    users = {note.comment_email for note in notes}
    assert len(users) == 1 and None not in users, "Work author is ambiguous"
    user = users.pop()
    frappe.get_doc("User", user, for_update=True)
    employees = frappe.get_all("Employee", filters={"user_id": user,
        "status": "Active", "company": project.company}, fields=["name", "employee_name"])
    assert len(employees) == 1 and employees[0].employee_name == "Manikandan D", "Employee mismatch"
    employee = employees[0].name
    pending, seen = [], set()
    for note in notes:
        key = (note.reference_name, str(note.creation)[11:19])
        assert key in EXPECTED and key not in seen, "Unexpected work note"
        seen.add(key)
        text = " ".join(Text(note.content).parts)
        assert text == "Today's work — " + DAY + " " + EXPECTED[key], "Work content changed"
        assert frappe.db.get_value("Task", note.reference_name, "project") == PROJECT
        existing = frappe.get_all("Timesheet Detail", filters={"custom_bs_work_entry": note.name},
            fields=["parent", "project", "task", "custom_bs_work_date", "description", "docstatus"])
        assert len(existing) <= 1, "Duplicate source links already exist"
        if existing:
            row = existing[0]
            assert row.docstatus != 2 and row.project == PROJECT and row.task == note.reference_name
            assert str(row.custom_bs_work_date) == DAY and row.description == EXPECTED[key]
            parent = frappe.get_doc("Timesheet", row.parent)
            assert parent.user == user and parent.employee == employee, "Existing entry owner mismatch"
        else:
            pending.append((note, EXPECTED[key]))
    if not pending:
        return
    drafts = frappe.get_all("Timesheet", filters={"owner": user, "user": user,
        "company": project.company, "custom_date": DAY, "docstatus": 0,
        "parent_project": ["is", "not set"]}, pluck="name", order_by="creation asc", limit_page_length=1)
    sheet = frappe.get_doc("Timesheet", drafts[0], for_update=True) if drafts else frappe.new_doc("Timesheet")
    if not drafts:
        sheet.update(dict(owner=user, user=user, employee=employee,
                          company=project.company, custom_date=DAY, parent_project=None))
    assert sheet.user == user and sheet.employee == employee
    for note, description in pending:
        sheet.append("time_logs", dict(project=PROJECT, task=note.reference_name,
            custom_reference_type="Project", custom_reference=PROJECT, description=description,
            custom_bs_work_date=DAY, custom_bs_work_entry=note.name, hours=0, is_billable=0))
    sheet.save(ignore_permissions=True)
    # Source comments stay intact; native save runs and the patch transaction is atomic.
    frappe.logger().info("Restored %s original daily work notes to %s", len(pending), sheet.name)
