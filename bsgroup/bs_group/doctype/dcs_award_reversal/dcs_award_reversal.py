# Copyright (c) 2026, Tridots Tech and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class DCSAwardReversal(Document):
	def before_insert(self):
		# DCS Award Reversal - Governed Field Guard
		# An award reversal record is approval evidence. It may only ever be written by the
		# award reversal service, which enforces Managing Director authority, a mandatory
		# reason and a mandatory acknowledgement. Nothing may create or alter one directly.
		allowed = 0
		if self.flags.dcs_api_write:
			allowed = 1

		if allowed == 0:
			frappe.throw(
				"A DCS Award Reversal record may only be created by the award reversal "
				"service. It enforces Managing Director authority, a mandatory reversal "
				"reason and a mandatory acknowledgement. Direct creation or modification "
				"of an award reversal record is not permitted, because it would be false "
				"approval evidence."
			)

	def validate(self):
		allowed = 0
		if self.flags.dcs_api_write:
			allowed = 1

		if allowed == 0:
			frappe.throw(
				"A DCS Award Reversal record may only be created by the award reversal "
				"service. It enforces Managing Director authority, a mandatory reversal "
				"reason and a mandatory acknowledgement. Direct creation or modification "
				"of an award reversal record is not permitted, because it would be false "
				"approval evidence."
			)

	def on_trash(self):
		# DCS Award Reversal - Deletion Guard
		# Award reversal records are permanent history and are never deleted.
		frappe.throw(
			"A DCS Award Reversal record is permanent approval history and cannot be "
			"deleted. The original award event, the reversal and any subsequent "
			"re-award must all remain visible."
		)
