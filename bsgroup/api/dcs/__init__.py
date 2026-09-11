"""Governed Deal Cost Sheet services (A-14).

Dotted method paths used by ``deal_cost_sheet.js``:

    bsgroup.api.dcs.negotiation.dcs_apply_revision      bsgroup.api.dcs.negotiation.dcs_screen3
    bsgroup.api.dcs.approval.dcs_approval_decision      bsgroup.api.dcs.approval.dcs_screen4
    bsgroup.api.dcs.award.dcs_record_award              bsgroup.api.dcs.award.dcs_award_reversal
    bsgroup.api.dcs.award.dcs_po_reconcile
    bsgroup.api.dcs.handover.dcs_set_delivery_owner     bsgroup.api.dcs.handover.dcs_handover_action
    bsgroup.api.dcs.handover.dcs_delivery_release       bsgroup.api.dcs.handover.dcs_screen5

The production Server Scripts of the same bare names stay enabled until the
release is verified in staging (Decision 1); see section 4 of the
implementation package for their retirement.
"""

ENDPOINTS = {
	"dcs_apply_revision": "bsgroup.api.dcs.negotiation.dcs_apply_revision",
	"dcs_screen3": "bsgroup.api.dcs.negotiation.dcs_screen3",
	"dcs_approval_decision": "bsgroup.api.dcs.approval.dcs_approval_decision",
	"dcs_screen4": "bsgroup.api.dcs.approval.dcs_screen4",
	"dcs_record_award": "bsgroup.api.dcs.award.dcs_record_award",
	"dcs_award_reversal": "bsgroup.api.dcs.award.dcs_award_reversal",
	"dcs_po_reconcile": "bsgroup.api.dcs.award.dcs_po_reconcile",
	"dcs_set_delivery_owner": "bsgroup.api.dcs.handover.dcs_set_delivery_owner",
	"dcs_handover_action": "bsgroup.api.dcs.handover.dcs_handover_action",
	"dcs_delivery_release": "bsgroup.api.dcs.handover.dcs_delivery_release",
	"dcs_screen5": "bsgroup.api.dcs.handover.dcs_screen5",
}
