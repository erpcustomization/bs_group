"""New Opportunity enquiry requirement, including deferred Lead conversion."""
from pathlib import Path
import frappe
import bsgroup
from unittest.mock import patch

bsgroup.__path__.insert(0, str(Path(__file__).resolve().parents[1] / 'bsgroup'))
from bsgroup.opportunity_intake import validate

class Opportunity(frappe._dict):
    def is_new(self):
        return self.get('new', True)

def reject(message):
    raise ValueError(message)

checks = 0
with patch('bsgroup.opportunity_intake._', lambda text: text), patch('frappe.throw', reject):
    for origin in ('Customer', 'Lead'):
        for enquiry in (None, '', ' \n\t'):
            doc = Opportunity(opportunity_from=origin, custom_enquiry=enquiry,
                flags=frappe._dict(deferred_lead_intake=True))
            try:
                validate(doc)
            except ValueError as exc:
                assert 'Enquiry' in str(exc)
            else:
                raise AssertionError('Blank enquiry accepted')
            checks += 1
    doc = Opportunity(opportunity_from='Lead', custom_enquiry='Customer needs CCTV installation',
        flags=frappe._dict(deferred_lead_intake=True))
    validate(doc)
    assert doc.custom_presales_required == 0
    checks += 1
    validate(Opportunity(new=False, custom_enquiry=None))
    checks += 1
print(f'PASS {checks} enquiry checks')
