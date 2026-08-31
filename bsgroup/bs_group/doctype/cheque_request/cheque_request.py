# Copyright (c) 2026, Tridots Tech and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class ChequeRequest(Document):

    def validate(self):
        # workflow_state is always set before validate runs.
        # Sync status from it so all handle_* checks work correctly.
        if self.workflow_state:
            self.status = self.workflow_state

        self.handle_pre_approval()
        self.handle_preparation()
        self.handle_signing()
        self.handle_issue()
        self.check_duplicate_cheque()

    # PRE-APPROVAL LOGIC
    def handle_pre_approval(self):
        if self.status == "Pre-Approved":
            if not self.pre_approved_by:
                self.pre_approved_by = frappe.session.user
                self.pre_approved_on = now_datetime()
            self.pre_approval_status = "Approved"

        elif self.status == "Pending Pre-Approval":
            self.pre_approval_status = "Pending"

    # PREPARATION LOGIC
    def handle_preparation(self):
        if self.status == "Prepared":

            if not self.cheque_number:
                frappe.throw("Cheque Number is mandatory before marking as Prepared")

            if not self.cheque_date:
                frappe.throw("Cheque Date is mandatory")

            if not self.bank_account:
                frappe.throw("Bank Account is mandatory")

            if not self.prepared_by:
                self.prepared_by = frappe.session.user
                self.prepared_on = now_datetime()

    # SIGNING LOGIC
    def handle_signing(self):
        if self.status == "Pending Signature":
            self.signing_status = "Pending"

        elif self.status == "Signed":
            if not self.signed_by:
                self.signed_by = frappe.session.user
                self.signed_on = now_datetime()
            self.signing_status = "Signed"

    # ISSUE LOGIC
    def handle_issue(self):
        if self.status == "Issued":
            if not self.issued_by:
                self.issued_by = frappe.session.user
                self.issued_on = now_datetime()
            self.issue_status = "Issued"

    # DUPLICATE CHECK
    def check_duplicate_cheque(self):
        if self.cheque_number and self.bank_account:
            existing = frappe.db.exists(
                "Cheque Request",
                {
                    "cheque_number": self.cheque_number,
                    "bank_account": self.bank_account,
                    "name": ["!=", self.name]
                }
            )
            if existing:
                frappe.throw("Cheque Number already used for this Bank Account!")