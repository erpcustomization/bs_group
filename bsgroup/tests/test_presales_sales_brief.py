"""Date serialisation must not prevent Presales saving its own work."""
from datetime import date
from unittest import TestCase
from unittest.mock import Mock, patch

from bsgroup.presales_sales_brief import protect_sales_fields


class TestSalesBriefProtection(TestCase):
    def check(self, old, new, denied=False):
        doc = Mock()
        doc.is_new.return_value = False
        doc.get.side_effect = new.get
        doc.get_doc_before_save.return_value = Mock(get=old.get)
        with patch('bsgroup.presales_sales_brief.frappe.get_roles', return_value=['BS Scoped Presales']), \
             patch('bsgroup.presales_sales_brief.frappe.throw') as throw:
            protect_sales_fields(doc)
            self.assertEqual(throw.called, denied)

    def test_same_dates_with_presales_work_changes(self):
        self.check({'request_date':date(2026,11,5),'expected_close_date':date(2026,12,1)},
                   {'request_date':'2026-11-05','expected_close_date':'2026-12-01',
                    'solution_summary':'Updated solution','scope_details':'Updated scope',
                    'custom_completion_time':'2 days'})

    def test_empty_dates_are_equivalent(self):
        self.check({'request_date':None,'expected_close_date':None},
                   {'request_date':'','expected_close_date':''})

    def test_real_date_changes_are_denied(self):
        for field in ('request_date','expected_close_date'):
            for old,new in ((date(2026,11,5),'2026-11-06'),(date(2026,11,5),''),(None,'2026-11-05')):
                with self.subTest(field=field,old=old,new=new):
                    self.check({field:old},{field:new},denied=True)

    def test_sales_details_remain_protected(self):
        for field,old,new in (('subject','Original','Changed'),('estimated_value',100,200),
                              ('custom_service_details','Original','Changed'),
                              ('opportunity','OPP-1','OPP-2'),('customer','A','B')):
            with self.subTest(field=field):
                self.check({field:old},{field:new},denied=True)
