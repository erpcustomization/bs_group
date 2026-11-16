"""Project module navigation. Membership is additive; native records and permissions remain authoritative."""
import json
import re
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
    ("amc", "AMC", "calendar"),
    ("tasks", "Tasks", "book-open-text"),
    ("timesheets", "Timesheets", "timer-reset"),
    ("scheduler", "Tech Task Scheduler", "calendar"),
    ("expenses", "Expenses", "file-text"),
    ("advances", "Advance", "credit-card"),
    ("labor", "Labour Approval", "clipboard-list"),
)


def route_options(row):
    try:
        value = json.loads(row.route_options or "{}")
        return value if isinstance(value, dict) else {}
    except (ValueError, TypeError):
        return {}


def install():
    """Idempotent installation only. Never reclassify projects, change roles, or replace templates."""
    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
    kickoff_field = "custom_expected_kick_off_meeting_date"
    existing = frappe.get_meta("Project").get_field(kickoff_field)
    if existing and existing.fieldtype != "Date":
        frappe.throw(_("Project kick-off meeting date already exists with an incompatible type."))
    if not existing:
        create_custom_fields({"Project": [dict(fieldname=kickoff_field, label="Expected Kick-off Meeting Date",
                           fieldtype="Date", reqd=0, insert_after="expected_end_date")]}, update=False)
    if not frappe.db.exists("DocType", "Sidebar") or not frappe.db.exists("Sidebar", "BS Group"):
        return {"installed": False, "reason": "The existing BS Group sidebar is not available on this site."}
    sidebar = frappe.get_doc("Sidebar", "BS Group")
    sections = [row.label for row in sidebar.items if row.type == "Section Break"]
    if not {"BS Project", "BS Project Support"}.intersection(sections):
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
    source = next(row for row in sidebar.items if row.type == "Section Break" and row.label in {"BS Project", "BS Project Support"})
    changed = False
    for key, (title, field) in MODULES.items():
        if title in sections:
            continue  # Preserve any existing/customized module navigation.
        group = {k: v for k, v in source.as_dict().items() if k not in
                 {"name", "doctype", "parent", "parenttype", "parentfield", "idx", "owner", "creation", "modified", "modified_by"}}
        group.update(label=title, keep_closed=1)
        sidebar.append("items", group)
        for section, label, icon in SECTIONS[:3]:
            options = {"bs_module": key, "bs_section": section}
            sidebar.append("items", dict(type="Link", label=label, link_type="Page", link_to="bs-project-modules",
                child=1, icon=icon, route_options=json.dumps(options),
                filters=json.dumps([["bs_module", "=", key], ["bs_section", "=", section]])))
        changed = True
    # Existing category sections also need AMC, immediately after Projects.
    group = None
    for row in list(sidebar.items):
        if row.type == "Section Break":
            group = next((key for key, (title, _) in MODULES.items() if row.label == title), None)
        if not group or row.type != "Link" or row.link_to != "bs-project-modules":
            continue
        try:
            options = json.loads(row.route_options or "{}")
        except (TypeError, ValueError):
            continue
        if options.get("bs_section") != "projects":
            continue
        if any(r.link_to == "bs-project-modules" and route_options(r).get("bs_section") == "amc"
               and route_options(r).get("bs_module") == group for r in sidebar.items if r.type == "Link"):
            continue
        values = {k: v for k, v in row.as_dict().items() if k not in
                  {"name", "doctype", "parent", "parenttype", "parentfield", "idx", "owner", "creation", "modified", "modified_by"}}
        options.update(bs_module=group, bs_section="amc")
        values.update(label="AMC", icon="calendar", route_options=json.dumps(options),
                      filters=json.dumps([["bs_module", "=", group], ["bs_section", "=", "amc"]]))
        added = sidebar.append("items", values)
        sidebar.items.remove(added)
        sidebar.items.insert(sidebar.items.index(row) + 1, added)
        changed = True
    if changed:
        for idx, row in enumerate(sidebar.items, 1):
            row.idx = idx
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
    from bsgroup.project_daily_work import enabled, TERMINAL
    if enabled() and section == "tasks":
        filters["status"] = ["not in", list(TERMINAL)]
    result = {"doctype": doctype, "rows": [], "available": bool(frappe.has_permission(doctype, "read"))}
    if not result["available"] or not names:
        return result
    meta = frappe.get_meta(doctype)
    fields = ["name", "modified", "docstatus"] + [field for field in extra if meta.has_field(field)]
    result["rows"] = frappe.get_list(doctype, filters=filters, fields=fields,
                                    distinct=True, order_by="creation desc", limit_page_length=100)
    return result


@frappe.whitelist()
def overview(module, section="dashboard", status="Not completed", search=""):
    if module not in MODULES:
        frappe.throw(_("Choose a valid project module."))
    if section not in {key for key, label, icon in SECTIONS}:
        frappe.throw(_("Choose a valid module section."))
    if status not in ("Not completed", "All", "Open", "On hold", "Completed", "Cancelled"):
        frappe.throw(_("Choose a valid project status."))
    query = str(search or "").strip().casefold()
    rows = [row for row in portfolio()
            if (status == "All" or (row.get("status") != "Completed" if status == "Not completed" else row.get("status") == status))
            and (not query or any(query in str(row.get(field) or "").casefold()
                                 for field in ("name", "project_name", "customer")))]
    matching = [row for row in rows if module in row["categories"]]
    projects = [row for row in matching if not row["is_amc"]]
    amcs = [row for row in matching if row["is_amc"]]
    result = dict(module=module, title=MODULES[module][0], field=MODULES[module][1], section=section,
                  projects=projects, amcs=amcs,
                  unclassified=[row for row in rows if not row["categories"]
                                and row["is_amc"] == (section == "amc")],
                  can_create=bool(frappe.has_permission("Project", "create")))
    if section not in ("dashboard", "projects", "amc"):
        result.update(requires_project=True)
    return result


def classify(row):
    """Read-only legacy grouping. Explicit selections always win; no document saves."""
    # Imported titles often use underscores as word separators.
    title = str(row.get("project_name") or "").replace("_", " ")
    kind = str(row.get("project_type") or "").replace("_", " ").strip()
    is_amc = kind in {"Remote AMC", "PPM AMC", "Adhoc AMC"} or (
        not re.search(r"non[\s_-]*amc", title, re.I) and
        bool(re.search(r"\bamc\b|\bmaintenance\b", title, re.I)))
    selected = [key for key, (_, field) in MODULES.items() if row.get(field) in (1, "1", True)]
    if selected:
        review = str(row.get("custom_bs_category_review_note") or "").strip()
        return dict(categories=selected, is_amc=bool(is_amc), classification=review or "Saved category", review_required=bool(review))
    text = kind + " " + title
    patterns = {
        "3cx": r"\b3cx\b",
        "elv": r"\belv\b|\bcctv\b|\baccess control\b|\bnurse call\b|\bintercom\b|\banpr\b",
        "infra": r"\binfra(?:structure)?\b|\bnetwork(?:ing)?\b|\bwi[ -]?fi\b|\bfirewall\b|\bserver\b|\bstructured cabling\b",
    }
    # Supply-only wording is decisive. "Supply & installation" alone is not.
    if re.search(r"\bsupply[ -]only\b", text, re.I):
        inferred = ["supply"]
    else:
        inferred = [key for key, pattern in patterns.items() if re.search(pattern, text, re.I)]
    return dict(categories=inferred, is_amc=bool(is_amc), review_required=True,
                classification="From title/type — confirm category" if inferred else "Needs classification")


def portfolio():
    if not frappe.has_permission("Project", "read"):
        frappe.throw(_("Project access is restricted by your existing permissions."), frappe.PermissionError)
    meta = frappe.get_meta("Project")
    fields = ["name", "project_name", "status", "project_type", "percent_complete", "company", "modified"]
    fields += [field for field in ["customer", "custom_project_manager", "expected_start_date", "expected_end_date", "custom_bs_category_review_note"]
               + [field for _, field in MODULES.values()] if meta.has_field(field)]
    rows = frappe.get_list("Project", fields=fields, order_by="creation desc", limit_page_length=0)
    return [dict(row, **classify(row)) for row in rows]
