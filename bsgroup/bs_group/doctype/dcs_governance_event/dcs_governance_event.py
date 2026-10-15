# Copyright (c) 2026, Tridots Tech and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

from bsgroup.dcs.governance_event_guard import before_insert as _guard_before_insert


class DCSGovernanceEvent(Document):
	"""Append-only governed audit trail.

	The trust boundary lives in ``bsgroup.dcs.governance_event_guard`` and is
	wired both through ``hooks.doc_events`` and here, so removing either
	registration alone cannot open the DocType to direct inserts.
	"""

	def before_insert(self):
		_guard_before_insert(self)

	def validate(self):
		# DCS Governance Event - Immutability Guard (D2a).
		# The canonical governed audit trail is append-only. A recorded event is never edited.
		if not self.is_new():
			frappe.throw(
				"DCS Governance Event "
				+ str(self.name)
				+ " is immutable. A recorded governance event is append-only evidence and can never be edited. If an event was recorded in error, record a corrective governed action instead."
			)

	def on_trash(self):
		# DCS Governance Event - Deletion Guard (D2a).
		# Governed audit evidence is never removed.
		frappe.throw(
			"DCS Governance Event "
			+ str(self.name)
			+ " cannot be deleted. The governed audit trail is immutable, append-only evidence. If an event was recorded in error, record a corrective governed action instead."
		)
