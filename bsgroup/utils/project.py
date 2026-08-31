import frappe


def validate_project_completion(doc, method):
    if doc.status != "Completed":
        return

    excluded_task_statuses = ["Completed", "Advance Payment - Invoice", "Pending Invoicing", "Active 3CX AMC Clients", "Active Infra AMC Clients"]

    incomplete_tasks = frappe.get_all("Task", filters={"project": doc.name, "status": ["not in", excluded_task_statuses]}, fields=["name", "subject", "status"], limit_page_length=5)
    if incomplete_tasks:
        examples = ", ".join([t.name + " (" + t.status + ")" for t in incomplete_tasks])
        frappe.throw("This Project cannot be marked Completed while delivery Tasks are still open, for example: " + examples + ". Please complete all delivery Tasks before closing the Project.")

    incomplete_milestones = frappe.get_all("Task", filters={"project": doc.name, "is_milestone": 1, "status": ["!=", "Completed"]}, fields=["name", "subject", "status"], limit_page_length=5)
    if incomplete_milestones:
        examples = ", ".join([t.name + " (" + t.status + ")" for t in incomplete_milestones])
        frappe.throw("This Project cannot be marked Completed while Milestone Tasks remain incomplete: " + examples + ".")

def close_labor_preapprovals_on_completion(doc, method):
    if doc.status == "Completed" and doc.has_value_changed("status"):
        from bsgroup.bs_group.doctype.labor_preapproval.labor_preapproval import (
            close_open_preapprovals_for_project,
        )

        close_open_preapprovals_for_project(doc.name)


def validate_mandatory_fields(doc, method):
    missing = [label for label, value in {
        "Project Description": doc.custom_project_description,
        "Expected Start Date": doc.expected_start_date,
        "Expected End Date": doc.expected_end_date,
        "Project Type": doc.project_type,
        "Customer": doc.customer,
        "Project Manager": doc.custom_project_manager
    }.items() if not value]

    if missing:
        frappe.throw("The following mandatory fields must be completed before creating a new Project: " + ", ".join(missing))
