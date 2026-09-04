import frappe


def execute():
	"""Backfill `custom_pipeline_stage` from the existing core `status` for
	Quotations created before the pipeline stage field existed - they were
	all left at the field's default "Draft", which made every pipeline
	report/dashboard show the entire sales history as Draft regardless of
	actual outcome.

	Only touches rows still sitting at the "Draft" default, so it never
	overwrites a stage a user has since set deliberately.
	"""
	status_to_stage = {
		"Draft": "Draft",
		"Open": "Sent",
		"Ordered": "Won",
		"Lost": "Lost",
		"Cancelled": "Cancelled",
		"Expired": "Expired",
	}

	for status, stage in status_to_stage.items():
		if stage == "Draft":
			continue
		frappe.db.sql(
			"""
			UPDATE `tabQuotation`
			SET custom_pipeline_stage = %(stage)s
			WHERE status = %(status)s AND custom_pipeline_stage = 'Draft'
			""",
			{"status": status, "stage": stage},
		)
