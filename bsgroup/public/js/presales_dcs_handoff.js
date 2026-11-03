(() => {
    if (window.bsPresalesDcsHandoff) return;
    window.bsPresalesDcsHandoff = true;
    frappe.ui.form.on('Presales Request', {
        async on_submit(frm) {
            const name = frm.doc.name;
            const result = await frappe.call({method:'bsgroup.presales_dcs_handoff.linked_dcs',args:{name}});
            if (result.message && window.cur_frm === frm && frm.doc.name === name) {
                frappe.set_route('Form', 'Deal Cost Sheet', result.message);
            }
        }
    });
})();
