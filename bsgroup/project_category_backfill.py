"""One-time, category-only classification of the existing UAE/Oman portfolio."""
import json
import re

import frappe

from bsgroup.project_modules import MODULES, classify

PATCH = "bs_project_category_completion_2026_11_16_v1"
REVIEW_FIELD = "custom_bs_category_review_note"


def proposed_categories(row):
    """Preserve saved choices except the two explicitly authorized corrections."""
    title = str(row.get("project_name") or "").replace("_", " ")
    if row.get("name") == "PROJ-2367" and "Amana AMC - ECS/NCS" in title:
        return ["elv"], ""
    if row.get("name") == "PROJ-0157" and "Embassy of the Republic of Indonesia - IT Infrastructure AMC" in title:
        return ["infra"], ""
    result = classify(row)
    if any(row.get(field) in (1, "1", True) for _, field in MODULES.values()):
        return None, None
    categories = result["categories"]
    if not categories:
        # These are scope hints, not changes to the AMC/Project partition.
        text = str(row.get("project_type") or "") + " " + title
        if re.search(r"\b(?:ecs|ncs|sapien|fire alarm|bms|pabx)\b", text, re.I):
            categories = ["elv"]
        elif re.search(r"\b(?:it|data cent(?:er|re)|rack|cabling|fortigate|aruba)\b", text, re.I):
            categories = ["infra"]
        elif re.search(r"\bsupply\b", text, re.I) and not result["is_amc"] and not re.search(r"install|implementation|migration", text, re.I):
            categories = ["supply"]
    if categories:
        return categories, "Needs category review: assigned from the existing title/type; confirm the contract scope."
    return ["infra"], "Needs category review: scope is unclear; Infra is provisional until the owner confirms the category."


def execute():
    """No workflow saves, statuses, tasks, permission writes or historical edits."""
    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

    if frappe.local.site not in {"erp-bitssecureit.u.frappe.cloud", "erp-om.k.frappe.cloud",
                                 "erp.bitssecureit.com", "erp-om.bitssecureit.com"}:
        return
    if frappe.db.exists("Patch Log", {"patch": PATCH}):
        return
    meta = frappe.get_meta("Project")
    if not all(meta.has_field(field) for _, field in MODULES.values()):
        return
    if not meta.has_field(REVIEW_FIELD):
        create_custom_fields({"Project": [dict(
            fieldname=REVIEW_FIELD, label="Category Review Note", fieldtype="Small Text",
            insert_after="custom_bs_3cx_projects", allow_on_submit=1,
            description="Provisional classification only. Confirm the project scope, update Project Modules and clear this note when verified.",
        )]}, update=False)
    fields = ["name", "project_name", "project_type", REVIEW_FIELD] + [field for _, field in MODULES.values()]
    for row in frappe.get_all("Project", fields=fields, limit_page_length=0):
        categories, note = proposed_categories(row)
        if categories is None:
            continue
        values = {field: int(key in categories) for key, (_, field) in MODULES.items()}
        values[REVIEW_FIELD] = note
        changes = [[field, row.get(field), value] for field, value in values.items()
                   if (row.get(field) or ("" if field == REVIEW_FIELD else 0)) != value]
        if not changes:
            continue
        frappe.db.set_value("Project", row.name, values, update_modified=False)
        # Append a category-only audit entry; never rewrite prior versions/comments.
        frappe.get_doc(dict(doctype="Version", ref_doctype="Project", docname=row.name,
                            data=json.dumps({"changed": changes}))).insert(ignore_permissions=True)
        frappe.clear_document_cache("Project", row.name)
    frappe.get_doc(dict(doctype="Patch Log", patch=PATCH)).insert(ignore_permissions=True)

