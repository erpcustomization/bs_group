from pathlib import Path
import frappe
import bsgroup
bsgroup.__path__.insert(0, str(Path(__file__).resolve().parents[1] / "bsgroup"))
frappe.init(site="rel1-test.local", sites_path="/home/bitssecureit/rel1-bench/sites")
frappe.connect()
frappe.set_user("Administrator")
try:
    from bsgroup import scoped_sales_access as access
    from unittest.mock import patch
    # Real database and native permission engine; all configuration is rolled back.
    # The local bench has no queue worker; do not enqueue contact-sync jobs
    # for configuration that this test immediately rolls back.
    with patch.object(frappe, 'enqueue'):
        access.configure_dubai()
    frappe.clear_cache()
    import bsgroup.hooks as hooks
    real_hooks = frappe.get_hooks
    def test_hooks(name=None, *args, **kwargs):
        value = real_hooks(name, *args, **kwargs)
        if name in ("has_permission", "permission_query_conditions"):
            value = dict(value)
            for dt in ("Lead", "Opportunity", "Presales Request", "Deal Cost Sheet", "Quotation", "Site Survey Request"):
                value[dt] = [getattr(hooks, name)[dt]]
        return value
    with patch.object(frappe, 'get_hooks', side_effect=test_hooks):
        for user in ['gopinath@bitssecureit.com','priya@bitssecureit.com','paul@bitssecureit.com','sanisha@bitssecureit.com']:
            frappe.set_user(user)
            mode = access.scope()
            assert mode
            assert 'System Manager' not in frappe.get_roles() and 'Sales Manager' not in frappe.get_roles()
            assert not frappe.has_permission('Site Survey Request', 'read')
            assert not frappe.has_permission('Sales Order', 'read')
            assert not frappe.has_permission('User', 'write', doc=frappe.get_doc('User','Administrator'))
            customers = frappe.get_list('Customer', fields=['name'], limit_page_length=10000)
            assert customers, (user, 'no selectable customers')
            for customer in customers:
                doc = frappe.get_doc('Customer', customer.name)
                assert doc.has_permission('read', user=user), (user, customer.name, 'selectable customer denied')
                assert not doc.has_permission('write', user=user), (user, 'customer edit granted')
            print(user, 'selectable customers readable', len(customers), flush=True)
            for dt in ('Lead','Opportunity','Presales Request','Deal Cost Sheet','Quotation'):
                permitted = dt in access.SCREENS[mode]
                assert bool(frappe.has_permission(dt, 'read')) == permitted, (user,dt)
                if not permitted:
                    continue
                rows = frappe.get_list(dt, fields=['name'], limit_page_length=1000)
                for row in rows:
                    assert access.permission(frappe.get_doc(dt,row.name), user)
                if rows:
                    assert frappe.get_doc(dt,rows[0].name).has_permission(user=user), (user,dt,'own record denied')
                other = frappe.db.sql(f'SELECT name FROM `tab{dt}` WHERE NOT ({access.condition(dt,user)}) LIMIT 1', as_dict=True)
                if other:
                    assert not frappe.has_permission(dt,'read',doc=frappe.get_doc(dt,other[0].name),user=user), (user,dt,'foreign readable')
                print(user, dt, 'visible',len(rows), 'foreign denied',bool(other),flush=True)
            boot = frappe._dict(module_sidebars={'BS Group':{'items':[{'link_type':'DocType','link_to':dt} for dt in ['Lead','Opportunity','Presales Request','Site Survey Request','Deal Cost Sheet','Quotation']]}})
            access.boot_session(boot)
            assert len(boot.module_sidebars['BS Group']['items']) == len(access.SCREENS[mode])
        frappe.set_user('Administrator')
        assert access.scope() is None
    print('PASS scoped roles, list filtering, foreign direct-read denial, survey-tab denial and sidebar counts; rollback',flush=True)
finally:
    frappe.db.rollback()
    frappe.clear_cache()
    frappe.destroy()
