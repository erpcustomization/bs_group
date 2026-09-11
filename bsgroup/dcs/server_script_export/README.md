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
