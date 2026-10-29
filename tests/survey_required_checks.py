import sys
from pathlib import Path
import frappe, bsgroup
bsgroup.__path__.insert(0,str(Path(__file__).resolve().parents[1]/'bsgroup'))
from bsgroup.opportunity_intake import validate_survey_steps
frappe.throw=lambda message: (_ for _ in ()).throw(ValueError(message))
import bsgroup.opportunity_intake as module
module._=lambda text:text
class Doc(frappe._dict):
    meta=frappe._dict(get_label=lambda field:field)
fields=['custom_survey_instructions','custom_survey_location','custom_survey_contact_phone','custom_survey_contact_name','custom_enquiry']
base=dict(custom_presales_required=1,custom_elv_site_survey_required=1,custom_business_type='Service',custom_survey_step=0,**{f:'filled' for f in fields})
for field in fields:
    doc=Doc(base);doc[field]='   '
    try: validate_survey_steps(doc)
    except ValueError as e: assert field in str(e)
    else: raise AssertionError(field)
doc=Doc(base);validate_survey_steps(doc);assert doc.custom_survey_step==3
validate_survey_steps(Doc(custom_presales_required=0,custom_survey_step=0))
print('PASS five required fields, complete survey dispatch, and no-survey exemption')
