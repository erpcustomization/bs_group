"""A rejected position stays subject to review until a later approval."""
import frappe


def requires_fresh_approval(sheet, before_revision=None):
    """Read immutable decisions, including the current revision when revising.

    Authority checks exclude the current revision so its approval must still
    pass the exact-manager, revision and amount checks. Pending/Not Required
    revisions cannot wash away an earlier rejection.
    """
    cutoff = before_revision if before_revision is not None else (sheet.custom_dcs_revision_no or 0) + 1
    decisions = frappe.get_all("DCS Revision", filters={
        "dcs": sheet.name, "revision_no": ["<", cutoff],
        "approval_state": ["in", ["Rejected", "Approved"]],
    }, fields=["approval_state"], order_by="revision_no desc", limit_page_length=1)
    return bool(decisions and decisions[0].approval_state == "Rejected")
