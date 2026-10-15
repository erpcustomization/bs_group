# Production Server Script export (read-only reference)

Byte-exact copies of the production Server Scripts that the DCS core release
ports into app code. Exported on 11 Sep 2026 from
`erp-bitssecureit.u.frappe.cloud` through the Frappe Cloud SQL Playground in
Read Only mode (`select script from tabServer Script where name = ...`).
Lengths were verified against `length(script)` on production and the files
were syntax-checked with `ast.parse`. Checksums are in `EXPORT_CHECKSUMS.txt`.

These files are **not imported or executed** by the app. They exist so the
port in `bsgroup/api/dcs/` can be diffed against the exact production
behaviour, and so the retirement ledger (Section 4 of the implementation
package) has a fixed reference for each script.

| File | Production Server Script | Port |
|------|--------------------------|------|
| dcs_apply_revision.py | dcs_apply_revision (API) | bsgroup.api.dcs.negotiation.dcs_apply_revision |
| dcs_screen3.py | dcs_screen3 (API) | bsgroup.api.dcs.negotiation.dcs_screen3 |
| dcs_approval_decision.py | dcs_approval_decision (API) | bsgroup.api.dcs.approval.dcs_approval_decision |
| dcs_screen4.py | dcs_screen4 (API) | bsgroup.api.dcs.approval.dcs_screen4 |
| dcs_record_award.py | dcs_record_award (API) | bsgroup.api.dcs.award.dcs_record_award |
| dcs_award_reversal.py | dcs_award_reversal (API) | bsgroup.api.dcs.award.dcs_award_reversal |
| dcs_po_reconcile.py | dcs_po_reconcile (API) | bsgroup.api.dcs.award.dcs_po_reconcile |
| dcs_set_delivery_owner.py | dcs_set_delivery_owner (API) | bsgroup.api.dcs.handover.dcs_set_delivery_owner |
| dcs_handover_action.py | dcs_handover_action (API) | bsgroup.api.dcs.handover.dcs_handover_action |
| dcs_delivery_release.py | dcs_delivery_release (API) | bsgroup.api.dcs.handover.dcs_delivery_release |
| dcs_screen5.py | dcs_screen5 (API) | bsgroup.api.dcs.handover.dcs_screen5 |
| DCS_Revision_Immutability_Guard.py / DCS_Revision_Deletion_Guard.py | DocType Event guards | bsgroup/bs_group/doctype/dcs_revision/dcs_revision.py |
| DCS_Handover_Condition_*_Guard.py | DocType Event guards | bsgroup/bs_group/doctype/dcs_handover_condition/dcs_handover_condition.py (already ported in ead9e4c) |
| HD_Partner_Email_Threading_Communication_Before_Insert.py | DocType Event | compared with bsgroup.utils.communication.hd_partner_email_threading (W-2, decision pending staging) |

## Production Server Script inventory and disposition register (read 12 Sep 2026 00:5x UAE, Frappe Cloud read-only SQL Playground)

* `server_scripts_251.psv` - all 251 production Server Scripts (177 disabled / 74 enabled):
  `name|script_type|reference_doctype|doctype_event|api_method|event_frequency|disabled|len(script)|creation|modified|modified_by`.
* `script_disposition_register.csv` - every script assigned one of the four release states:
  1. Replacement in rel-1 (36) - verified in staging per the S-Ret reference, then retired one at a time;
  2. Documented exception (57) - 7 kept enabled by decision (dcs_narrative_guard etc.), 39 enabled but outside
     the DCS register, 11 disabled by the 8-10 Sep migration with app replacements outside this release;
  3. Obsolete, disabled, on the deletion manifest (154);
  4. Blocked pending owner decision (4): DCS Presales Effort Metrics x2 (M-8), SI Bypass Project Customer Validation,
     Block Duplicate Quotation.
* `deletion_manifest.csv` - the 154 obsolete scripts. Deletion only after 30 stable production days following the
  release, and only after exporting each body (Server Script > Export JSON) to the release evidence folder; several are
  large one-off migrations (zoho_bill_migrate 65 KB, zoho_payment_migrate 28 KB) whose code has no other copy.
