(() => {
    if (window.bsPresalesDcsHandoff) return;
    window.bsPresalesDcsHandoff = true;
    frappe.ui.form.on('Presales Request', {
        async refresh(frm) {
            if (frm.is_new() || frm.doc.status !== 'Rework') return;
            const name = frm.doc.name;
            const result = await frappe.call({method:'bsgroup.presales_dcs_handoff.linked_dcs',args:{name}});
            if (frm.doc.name !== name || !result.message) return;
            frm.set_intro(__('Sales requested quotation rework. Open the linked costing sheet and use Revise BOQ; saving the revision updates the same quotation.'),'orange');
            frm.add_custom_button(__('Revise Linked Costing Sheet'),()=>frappe.set_route('Form','Deal Cost Sheet',result.message));
        },
        async on_submit(frm) {
            const name = frm.doc.name;
            const result = await frappe.call({method:'bsgroup.presales_dcs_handoff.linked_dcs',args:{name}});
            if (result.message && window.cur_frm === frm && frm.doc.name === name) {
                frappe.set_route('Form', 'Deal Cost Sheet', result.message);
            }
        }
    });
})();
