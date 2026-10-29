from pathlib import Path
import frappe, bsgroup
bsgroup.__path__.insert(0,str(Path(__file__).resolve().parents[1]/'bsgroup'))
frappe.init(site='rel1-test.local',sites_path='/home/bitssecureit/rel1-bench/sites')
frappe.connect();frappe.set_user('Administrator')
from bsgroup.sales_qualification import setup,validate,FIELDS
print(setup())
doc=frappe.new_doc('Opportunity')
for name,_ in FIELDS: doc.set('custom_'+name,'No')
validate(doc)
doc.custom_budget_confirmed=''
try: validate(doc)
except frappe.ValidationError: print('PASS Yes/No qualification rejects missing answer')
else: raise AssertionError('Missing accepted')
meta=frappe.get_meta('Presales Request')
assert all(meta.get_field(n).hidden and meta.get_field(n).permlevel==9 and not meta.get_field(n).reqd for n,_ in FIELDS)
print('PASS presales fields hidden, restricted and optional')
frappe.db.commit();frappe.destroy()
