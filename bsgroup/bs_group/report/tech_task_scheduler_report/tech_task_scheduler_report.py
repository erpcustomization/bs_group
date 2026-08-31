# Copyright (c) 2026, Tridots Tech and contributors
# For license information, please see license.txt

import frappe
from datetime import datetime, timedelta

def execute(filters=None):
	columns = get_columns()
	data = get_data(filters)
	return columns, data


def get_columns():
	return [
		{"label": "Date", "fieldname": "date", "fieldtype": "Date", "width": 100},
		{"label": "Category", "fieldname": "category", "fieldtype": "Data", "width": 120},
		{"label": "Project / Ticket", "fieldname": "category_name", "fieldtype": "Data", "width": 150},
		{"label": "Task", "fieldname": "task", "fieldtype": "Data", "width": 150},
		{"label": "Assigned To", "fieldname": "resource", "fieldtype": "Data", "width": 180},
		{"label": "Status", "fieldname": "status", "fieldtype": "Data", "width": 100},
		{"label": "Activity Details", "fieldname": "activity_details", "fieldtype": "Data", "width": 200},
	]


def get_data(filters):
	conditions = []
	values = {}

	# Date filter logic
	if filters.get("date_filter") and filters.get("date_filter") != "All":
		today = datetime.today().date()

		if filters.get("date_filter") == "Today":
			conditions.append("date = %(today)s")
			values["today"] = today

		elif filters.get("date_filter") == "Tomorrow":
			conditions.append("date = %(tomorrow)s")
			values["tomorrow"] = today + timedelta(days=1)

		elif filters.get("date_filter") == "This Week":
			start = today - timedelta(days=today.weekday())
			end = start + timedelta(days=6)
			conditions.append("date BETWEEN %(start)s AND %(end)s")
			values.update({"start": start, "end": end})

		elif filters.get("date_filter") == "This Month":
			start = today.replace(day=1)
			if start.month == 12:
				end = start.replace(year=start.year + 1, month=1, day=1) - timedelta(days=1)
			else:
				end = start.replace(month=start.month + 1, day=1) - timedelta(days=1)

			conditions.append("date BETWEEN %(start)s AND %(end)s")
			values.update({"start": start, "end": end})

		elif filters.get("date_filter") == "Custom":
			if filters.get("from_date") and filters.get("to_date"):
				conditions.append("date BETWEEN %(from_date)s AND %(to_date)s")
				values["from_date"] = filters.get("from_date")
				values["to_date"] = filters.get("to_date")

	# Other filters
	if filters.get("category"):
		conditions.append("category = %(category)s")
		values["category"] = filters.get("category")

	if filters.get("category_name"):
		conditions.append("category_name = %(category_name)s")
		values["category_name"] = filters.get("category_name")

	if filters.get("task"):
		conditions.append("task = %(task)s")
		values["task"] = filters.get("task")

	if filters.get("assigned_to"):
		conditions.append("resource = %(assigned_to)s")
		values["assigned_to"] = filters.get("assigned_to")

	if filters.get("status"):
		conditions.append("status = %(status)s")
		values["status"] = filters.get("status")

	company = frappe.defaults.get_user_default("company")
	if company:
		conditions.append("(ttsl.category != 'Project' OR proj.company = %(company)s)")
		values["company"] = company

	where_clause = " AND ".join(conditions) if conditions else "1=1"

	data = frappe.db.sql(f"""
		SELECT
			ttsl.date,
			ttsl.category,
			
			CASE 
				WHEN ttsl.category = 'Project' THEN proj.project_name
				WHEN ttsl.category = 'HD Ticket' THEN hd.subject
				ELSE ttsl.category_name
			END as category_name,

			task.subject as task,
			ttsl.resource,
			ttsl.status,
			ttsl.activity_details

		FROM `tabTech Task Scheduler List` ttsl

		LEFT JOIN `tabProject` proj 
			ON ttsl.category_name = proj.name

		LEFT JOIN `tabHD Ticket` hd 
			ON ttsl.category_name = hd.name

		LEFT JOIN `tabTask` task 
			ON ttsl.task = task.name

		WHERE {where_clause}
		ORDER BY ttsl.date DESC
""", values, as_dict=True)
	
	return data