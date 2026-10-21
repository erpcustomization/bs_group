"""Deploy sales handover assets only to rel1-test.local."""
import json,runpy
from pathlib import Path
import frappe
from frappe.utils import now_datetime
root=Path('/home/bitssecureit/rel1-bench/apps/bsgroup')
page=root/'bsgroup/bs_group/page/bs_procurement/bs_procurement.json'
data=json.loads(page.read_text());roles={r['role'] for r in data['roles']}
for role in ['Commercial Controller','Managing Director']:
 if role not in roles:data['roles'].append({'role':role})
page.write_text(json.dumps(data,indent=2)+'\n')
frappe.init(site='rel1-test.local',sites_path='/home/bitssecureit/rel1-bench/sites');frappe.connect();frappe.set_user('Administrator')
try:
 frappe.clear_cache(doctype='Quotation');frappe.clear_cache(doctype='Material Request')
 frappe.db.set_value('DocType','Quotation','modified',now_datetime(),update_modified=False)
 frappe.db.commit();frappe.clear_cache()
finally:frappe.destroy()
runpy.run_path(str(root/'tests/bs_procurement/deploy_standard.py'),run_name='__main__')
