from pathlib import Path
from unittest.mock import patch
import frappe
import bsgroup
bsgroup.__path__.insert(0,str(Path(__file__).resolve().parents[1]/'bsgroup'))
from bsgroup.dcs import creation


def refuse(message, exc):
    raise exc(message)


class Sheet:
    def __init__(self):
        self.name='TEST-DCS'
        self.flags=frappe._dict(ignore_permissions=True,workflow_dcs=True)
    def update(self, values):
        self.__dict__.update(values)
    def insert(self, **kwargs):
        creation.guard_creation(self)
        assert kwargs['ignore_permissions']
        return self


with patch.object(creation,'_',side_effect=lambda s:s),patch.object(frappe,'throw',side_effect=refuse):
    sheet=Sheet()
    try:
        sheet.insert(ignore_permissions=True)
        raise AssertionError('Manual creation accepted')
    except frappe.PermissionError:
        pass
    assert creation.insert_from_workflow(sheet) is sheet
    try:
        creation.guard_creation(sheet)
        raise AssertionError('Workflow authority leaked')
    except frappe.PermissionError:
        pass
    from bsgroup.opportunity_intake import create_cost_sheet
    opp=frappe._dict(name='TEST-OPP',opportunity_from='Customer',party_name='TEST-CUSTOMER',title='Test',company='Test',currency='AED')
    with patch.object(frappe,'get_all',return_value=[]),patch.object(frappe,'new_doc',return_value=Sheet()):
        result=create_cost_sheet(opp)
        assert result=={'name':'TEST-DCS','created':True}
        result=create_cost_sheet(opp,ignore_permissions=True)
        assert result['created']
    from unittest.mock import Mock
    from bsgroup.bs_group.doctype.presales_request.presales_request import PresalesRequest
    presales=frappe._dict(name='TEST-PR',opportunity='TEST-OPP',party_type='Customer',party='TEST-CUSTOMER',organisation_name='Test',subject='Test',company='Test',requested_by='sales',site_visit=None)
    with patch.object(frappe,'db',Mock(),create=True),patch.object(frappe,'get_all',return_value=[]),patch.object(frappe,'get_doc',return_value=opp),patch.object(frappe,'new_doc',return_value=Sheet()):
        frappe.db.exists.return_value=False
        PresalesRequest.on_submit(presales)
    class Broken(Sheet):
        def insert(self,**kwargs):
            creation.guard_creation(self)
            raise RuntimeError('failure')
    try:
        creation.insert_from_workflow(Broken())
    except RuntimeError:
        pass
    assert creation._allowed_sheet.get() is None
print('PASS manual/forged-flags blocked; Opportunity and survey workflow creation allowed; authority resets on success/failure')