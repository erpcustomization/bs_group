import importlib.util
import sys
import types
import unittest
from email.message import EmailMessage
from email.parser import Parser
from email.policy import SMTP
from pathlib import Path
from unittest.mock import Mock, patch


class Doc(dict):
    __getattr__ = dict.get
    __setattr__ = dict.__setitem__
    def set(self, key, value):
        self[key] = value


class HREmailTests(unittest.TestCase):
    def setUp(self):
        self.f = types.ModuleType("frappe")
        self.f.conf = {"host_name": "https://erp-om.bitssecureit.com"}
        self.f.local = Doc(site="erp-om.k.frappe.cloud")
        self.f.db = Mock()
        self.f.only_for = Mock()
        self.f.throw = lambda msg: (_ for _ in ()).throw(ValueError(msg))
        self.settings = Doc(custom_bs_hr_email_enabled=1, custom_bs_hr_email_account="HR Notifications")
        self.account = Doc(name="HR Notifications", email_id="hr-notifications-om@bitssecureit.com",
                           enable_outgoing=1, default_outgoing=0, enable_incoming=0)
        self.f.get_cached_doc = Mock(side_effect=lambda dt, *args: self.settings if dt == "HR Settings" else self.account)
        self.f.get_doc = Mock(return_value=self.account)
        self.f.get_cached_value = Mock(side_effect=lambda dt, name, field: {
            "Employee": "HR", "Leave Application": "HR", "HR Settings": "HR",
            "Salary Slip": "Payroll", "Quotation": "Selling", "HD Ticket": "Helpdesk",
            "Material Request": "Stock"}.get(name, "Core"))
        self.patch = patch.dict(sys.modules, {"frappe": self.f})
        self.patch.start()
        spec = importlib.util.spec_from_file_location("hr_email_test", Path(__file__).resolve().parents[1] / "hr_email.py")
        self.m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.m)

    def tearDown(self):
        self.patch.stop()

    def queue(self, dt="Employee"):
        msg = EmailMessage(policy=SMTP)
        msg["From"] = "ERP <erp.om@bitssecureit.com>"
        msg["To"] = "recipient@example.test"
        msg["Cc"] = "cc@example.test"
        msg["Reply-To"] = "existing-reply@example.test"
        msg["Message-ID"] = "<test-original@example.test>"
        msg["Subject"] = "Synthetic HR message"
        msg.set_content("Test body with Unicode: café")
        msg.add_alternative("<p>Test café</p>", subtype="html")
        msg.add_attachment(b"binary\x00\xff", maintype="application", subtype="octet-stream", filename="test.bin")
        return Doc(reference_doctype=dt, reference_name="test", email_account="Erp Om",
                   sender="erp.om@bitssecureit.com", message=msg.as_string(),
                   recipients=["recipient@example.test", "cc@example.test"])

    def test_hr_sender_changes_without_changing_body_attachments_recipients_or_reply_handling(self):
        q = self.queue()
        old = Parser(policy=SMTP).parsestr(q.message)
        recipients = list(q.recipients)
        self.m.route_queue(q)
        new = Parser(policy=SMTP).parsestr(q.message)
        self.assertEqual(q.email_account, "HR Notifications")
        self.assertIn(self.m.OMAN_EMAIL, q.sender)
        self.assertEqual(new["From"].addresses[0].addr_spec, self.m.OMAN_EMAIL)
        for key in ("To", "Cc", "Reply-To", "Subject", "Message-ID"):
            self.assertEqual(new[key], old[key])
        self.assertEqual([p.get_payload(decode=True) for p in new.walk()],
                         [p.get_payload(decode=True) for p in old.walk()])
        self.assertEqual(q.recipients, recipients)

    def test_non_hr_messages_remain_exactly_unchanged_even_from_hr_call_context(self):
        with patch.object(self.m, "hr_origin", return_value=True) as origin:
            for dt in ("Quotation", "Material Request", "HD Ticket", "User"):
                q = self.queue(dt)
                before = dict(q)
                self.m.route_queue(q)
                self.assertEqual(q, before)
            origin.assert_not_called()

    def test_uae_never_reads_settings_or_changes_messages(self):
        self.f.conf["host_name"] = "https://erp.bitssecureit.com"
        self.f.local.site = "erp-bitssecureit.u.frappe.cloud"
        q = self.queue()
        before = dict(q)
        self.m.route_queue(q)
        self.assertEqual(q, before)
        self.f.get_cached_doc.assert_not_called()

    def test_disabled_pilot_does_not_change_hr_messages(self):
        self.settings.custom_bs_hr_email_enabled = 0
        q = self.queue()
        before = dict(q)
        self.m.route_queue(q)
        self.assertEqual(q, before)

    def test_invalid_hr_transport_blocks_fallback_to_helpdesk(self):
        for field, value in (("enable_outgoing", 0), ("default_outgoing", 1),
                             ("enable_incoming", 1), ("email_id", "helpdesk@bitssecureit.com")):
            with self.subTest(field=field), patch.dict(self.account, {field: value}):
                with self.assertRaises(ValueError):
                    self.m.route_queue(self.queue())

    def test_salary_and_custom_hr_documents(self):
        for dt in ("Salary Slip", "HR Warning", "HR Service Request", "Leave Application"):
            q = self.queue(dt)
            self.m.route_queue(q)
            self.assertEqual(q.email_account, "HR Notifications")

    def test_hr_communication_reference_and_recorded_sender(self):
        self.f.db.get_value.return_value = ("Employee", "test")
        q = self.queue(None)
        q.communication = "communication-test"
        self.m.route_queue(q)
        self.assertEqual(q.email_account, "HR Notifications")
        self.f.db.set_value.assert_called_once()

    def test_reference_free_hrms_call_routes_but_generic_call_does_not(self):
        q = self.queue(None)
        before = dict(q)
        self.m.route_queue(q)
        self.assertEqual(q, before)
        namespace = {"__name__": "hrms.hr.doctype.leave_application.leave_application", "route": self.m.route_queue}
        exec("def send(q):\n    route(q)", namespace)
        namespace["send"](q)
        self.assertEqual(q.email_account, "HR Notifications")

    def test_enabling_and_disabling_restores_native_hr_reminder_senders(self):
        old = Doc(custom_bs_hr_email_enabled=0)
        doc = Doc(self.settings, sender="Old HR", sender_email="old@example.test",
                  hiring_sender="Old Hiring", hiring_sender_email="hiring@example.test")
        doc.get_doc_before_save = lambda: old
        self.m.validate_settings(doc)
        self.assertEqual(doc.sender_email, self.m.OMAN_EMAIL)
        old = Doc(doc)
        doc.custom_bs_hr_email_enabled = 0
        self.m.validate_settings(doc)
        self.assertEqual(doc.sender, "Old HR")
        self.assertEqual(doc.hiring_sender_email, "hiring@example.test")

    def test_cyclic_reference_does_not_recurse_forever(self):
        self.f.db.get_value.return_value = ("Communication", "loop")
        self.assertFalse(self.m.hr_document("Communication", "loop"))


if __name__ == "__main__":
    unittest.main()
