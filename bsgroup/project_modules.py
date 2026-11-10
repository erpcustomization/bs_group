"""Project module navigation. Membership is additive; native records and permissions remain authoritative."""
import json
import frappe
from frappe import _

MODULES = {
    "supply": ("BS Supply Projects", "custom_bs_supply_projects"),
    "elv": ("BS ELV Projects", "custom_bs_elv_projects"),
    "infra": ("BS Infra Projects", "custom_bs_infra_projects"),
    "3cx": ("BS 3CX Projects", "custom_bs_3cx_projects"),
}
SECTIONS = (
    ("dashboard", "Dashboard", "layout-dashboard"),
    ("projects", "Projects", "book-lock"),
    ("tasks", "Tasks", "book-open-text"),
    ("timesheets", "Timesheets", "timer-reset"),
    ("scheduler", "Tech Task Scheduler", "calendar"),
    ("expenses", "Expenses", "file-text"),
    ("advances", "Advance", "credit-card"),
    ("labor", "Labour Approval", "clipboard-list"),
)


def install():
    """Idempotent installation only. Never reclassify projects, change roles, or replace templates."""
    if not frappe.db.exists("DocType", "Sidebar") or not frappe.db.exists("Sidebar", "BS Group"):
        return {"installed": False, "reason": "The existing BS Group sidebar is not available on this site."}
    sidebar = frappe.get_doc("Sidebar", "BS Group")
    sections = [row.label for row in sidebar.items if row.type == "Section Break"]
    if "BS Project" not in sections:
        return {"installed": False, "reason": "The existing BS Project sidebar section is missing."}
    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
    after = "project_type"
    fields = []
    for title, field in MODULES.values():
        existing = frappe.get_meta("Project").get_field(field)
        if existing and existing.fieldtype != "Check":
            frappe.throw(_("Project field {0} already exists with an incompatible type.").format(field))
        if not existing:
            fields.append(dict(fieldname=field, label=title, fieldtype="Check", default="0", insert_after=after,
                               description="Select every module this project belongs to." if not fields else None))
        after = field
    if fields:
        create_custom_fields({"Project": fields}, update=False)
    if not frappe.db.exists("Page", "bs-project-modules"):
        frappe.reload_doc("bs_group", "page", "bs_project_modules", force=True)
    source = next(row for row in sidebar.items if row.type == "Section Break" and row.label == "BS Project")
    changed = False
    for key, (title, field) in MODULES.items():
        if title in sections:
            continue  # Preserve any existing/customized module navigation.
        group = {k: v for k, v in source.as_dict().items() if k not in
                 {"name", "doctype", "parent", "parenttype", "parentfield", "idx", "owner", "creation", "modified", "modified_by"}}
        group.update(label=title, keep_closed=1)
        sidebar.append("items", group)
        for section, label, icon in SECTIONS[:2]:
            options = {"bs_module": key, "bs_section": section}
            sidebar.append("items", dict(type="Link", label=label, link_type="Page", link_to="bs-project-modules",
                child=1, icon=icon, route_options=json.dumps(options),
                filters=json.dumps([["bs_module", "=", key], ["bs_section", "=", section]])))
        changed = True
    if changed:
        previous = frappe.flags.in_migrate
        try:
            frappe.flags.in_migrate = True
            sidebar.save()
        finally:
            frappe.flags.in_migrate = previous
    frappe.clear_cache(doctype="Project")
    frappe.clear_cache()
    return {"installed": True, "modules": [title for title, field in MODULES.values()]}


@frappe.whitelist(methods=["POST"])
def setup():
    frappe.only_for("System Manager")
    result = install()
    if not result["installed"]:
        frappe.throw(_(result["reason"]))
    return result


def visible_projects(key):
    if key not in MODULES:
        frappe.throw(_("Choose a valid project module."))
    if not frappe.has_permission("Project", "read"):
        frappe.throw(_("Project access is restricted by your existing permissions."), frappe.PermissionError)
    field = MODULES[key][1]
    if not frappe.get_meta("Project").has_field(field):
        frappe.throw(_("Project modules have not been installed yet."))
    return frappe.get_list("Project", filters={field: 1},
        fields=["name", "project_name", "status", "project_type", "percent_complete", "company", "modified"],
        order_by="creation desc", limit_page_length=0)


def records(section, projects):
    names = [row.name for row in projects]
    definitions = {
        "tasks": ("Task", {"project": ["in", names]}, ["subject", "status", "project"]),
        "timesheets": ("Timesheet", [["Timesheet Detail", "project", "in", names]], ["employee_name", "status"]),
        "scheduler": ("Tech Task Scheduler", [["Tech Task Scheduler List", "project", "in", names]], []),
        "expenses": ("Expense Claim", {"project": ["in", names]}, ["employee_name", "workflow_state", "project"]),
        "advances": ("Employee Advance", {"custom_project": ["in", names]}, ["employee_name", "workflow_state", "custom_project"]),
        "labor": ("Labor Preapproval", {"source": "Project", "reference": ["in", names]}, ["workflow_state", "reference", "task"]),
    }
    doctype, filters, extra = definitions[section]
    result = {"doctype": doctype, "rows": [], "available": bool(frappe.has_permission(doctype, "read"))}
    if not result["available"] or not names:
        return result
    meta = frappe.get_meta(doctype)
    fields = ["name", "modified", "docstatus"] + [field for field in extra if meta.has_field(field)]
    result["rows"] = frappe.get_list(doctype, filters=filters, fields=fields,
                                    distinct=True, order_by="creation desc", limit_page_length=100)
    return result


@frappe.whitelist()
def overview(module, section="dashboard"):
    if section not in {key for key, label, icon in SECTIONS}:
        frappe.throw(_("Choose a valid module section."))
    projects = visible_projects(module)
    result = dict(module=module, title=MODULES[module][0], field=MODULES[module][1], section=section,
                  projects=projects, can_create=bool(frappe.has_permission("Project", "create")))
    if section not in ("dashboard", "projects"):
        result.update(requires_project=True)
    return result
