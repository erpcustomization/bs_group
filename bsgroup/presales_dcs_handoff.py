"""Bidirectional, identity-checked Presales handoff to an existing DCS."""
import frappe
from bsgroup.dcs.presales_lineage import _same_deal


def link_back(request, sheet):
    if request.docstatus != 1 or sheet.docstatus == 2 or sheet.custom_record_authority == 'Superseded':
        frappe.throw('Only a submitted Presales Request and active DCS can be linked.')
    if sheet.presales_request != request.name or not _same_deal(sheet, request):
        frappe.throw('The DCS and Presales Request must belong to the same deal.')
    current = frappe.db.get_value('Presales Request', request.name, 'custom_deal_cost_sheet', for_update=True)
    if current and current != sheet.name:
        frappe.throw('Presales already links to another DCS. Review the existing link first.')
    request.custom_deal_cost_sheet = sheet.name
    # Creation copied the earlier draft state; submission has now persisted
    # Costing in Progress. Refresh the canonical projection after that change.
    from bsgroup.bs_group.doctype.deal_cost_sheet.deal_cost_sheet import dcs_presales_sync
    dcs_presales_sync(request.name, source='interactive')
    if current == sheet.name:
        return
    request.db_set('custom_deal_cost_sheet', sheet.name)
    request.add_comment('Info', 'Linked existing Deal Cost Sheet: ' + sheet.name)


@frappe.whitelist()
def linked_dcs(name):
    request = frappe.get_doc('Presales Request', name)
    request.check_permission('read')
    if request.docstatus != 1 or not request.custom_deal_cost_sheet:
        return None
    sheet = frappe.get_doc('Deal Cost Sheet', request.custom_deal_cost_sheet)
    sheet.check_permission('read')
    if sheet.docstatus == 2 or sheet.presales_request != name or not _same_deal(sheet, request):
        return None
    return sheet.name


@frappe.whitelist(methods=['POST'])
def backfill(names):
    if frappe.session.user != 'Administrator':
        frappe.throw('Administrator required', frappe.PermissionError)
    names = frappe.parse_json(names)
    if not isinstance(names, list) or len(names) != 6 or len(set(names)) != 6:
        frappe.throw('Provide the six reviewed Presales Request names.')
    result = []
    for name in names:
        request = frappe.get_doc('Presales Request', name, for_update=True)
        rows = frappe.get_all('Deal Cost Sheet', filters={'presales_request':name,'docstatus':['<',2]}, fields=['name','custom_record_authority','creation'])
        rows = [r for r in rows if r.custom_record_authority != 'Superseded']
        if len(rows) != 1 or str(rows[0].creation)[:10] != '2026-11-02':
            frappe.throw('Expected exactly one active DCS created on 2 November for ' + name)
        sheet = frappe.get_doc('Deal Cost Sheet', rows[0].name, for_update=True)
        link_back(request, sheet)
        result.append({'presales_request':name,'dcs':sheet.name})
    return result


@frappe.whitelist(methods=['POST'])
def repair_statuses():
    if frappe.session.user != 'Administrator':
        frappe.throw('Administrator required', frappe.PermissionError)
    from bsgroup.bs_group.doctype.deal_cost_sheet.deal_cost_sheet import dcs_presales_sync
    drafts = []
    if not frappe.db.exists('Workflow', {'document_type':'Deal Cost Sheet','is_active':1}):
        for row in frappe.get_all('Deal Cost Sheet', filters={'docstatus':0}, fields=['name','workflow_state']):
            if not row.workflow_state:
                frappe.db.set_value('Deal Cost Sheet', row.name, 'workflow_state', 'Draft')
                drafts.append(row.name)
    requests = frappe.db.sql("""select distinct p.name from `tabPresales Request` p
        join `tabDeal Cost Sheet` d on d.presales_request=p.name
        where d.docstatus<2 and coalesce(d.custom_presales_status,'')<>coalesce(p.status,'')""",as_dict=True)
    for row in requests:
        dcs_presales_sync(row.name, source='interactive')
    return {'draft_defaults':drafts, 'presales_statuses_synced':[r.name for r in requests]}
