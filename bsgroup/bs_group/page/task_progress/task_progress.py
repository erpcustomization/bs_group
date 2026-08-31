import json

import frappe


@frappe.whitelist()
def get_projects():
	return frappe.get_all(
		"Project",
		filters={"status": ["!=", "Cancelled"]},
		fields=["name", "project_name", "status", "percent_complete"],
		order_by="modified desc",
		limit_page_length=200,
	)


@frappe.whitelist()
def get_project_tasks(project):
	tasks = frappe.get_all(
		"Task",
		filters={"project": project},
		fields=[
			"name",
			"subject",
			"status",
			"priority",
			"exp_start_date",
			"exp_end_date",
			"progress",
			"parent_task",
			"is_group",
			"_assign",
		],
		order_by="parent_task asc, exp_start_date asc, idx asc",
	)

	by_name = {t.name: t for t in tasks}
	for t in tasks:
		t["children"] = []
		assignees = []
		if t.get("_assign"):
			try:
				assignees = json.loads(t["_assign"])
			except (TypeError, ValueError):
				assignees = []
		t["assigned_to"] = ", ".join(assignees) if assignees else ""

	roots = []
	for t in tasks:
		parent = t.get("parent_task")
		if parent and parent in by_name:
			by_name[parent]["children"].append(t)
		else:
			roots.append(t)

	return roots
