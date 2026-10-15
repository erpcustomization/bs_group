"""Step 8 / D12: keep Project Cost Baseline unavailable to users until its
financial calculations pass gate G-PCB in staging.

* DocPerms are reduced to System Manager in the DocType JSON (synced by the
  model sync before this patch runs); no workspace links to the DocType
  exist in the app.
* The cost-overrun policy is set to ``None`` so the PO / PI / Expense Claim /
  Labor Preapproval validate hooks never warn or block on a baseline figure
  that is not yet trusted. The previous value is logged so it can be
  restored when G-PCB passes.

Idempotent; touches nothing when the policy is already ``None``.
"""

import frappe

LOG_TITLE = "BSG-REL-1"


def execute():
	if not frappe.db.exists("DocType", "BS Group Settings"):
		return
	current = frappe.db.get_single_value("BS Group Settings", "cost_overrun_policy")
	if current == "None":
		return
	frappe.db.set_value("BS Group Settings", "BS Group Settings", "cost_overrun_policy", "None", update_modified=False)
	frappe.log_error(
		title=LOG_TITLE,
		message=f"PCB lockdown: cost_overrun_policy '{current}' -> 'None' (D12). "
		f"Project Cost Baseline rows on this site: {frappe.db.count('Project Cost Baseline')}. Restore after G-PCB.",
	)
