(() => {
    const base = 'bsgroup.quotation_numbering.';
    async function show() {
        const data = (await frappe.call({method:base+'status',freeze:true})).message;
        if (!data?.authorised) return;
        const esc = frappe.utils.escape_html;
        const state = data.state || {};
        const dialog = new frappe.ui.Dialog({title:__('Quotation numbering'),fields:[{fieldtype:'HTML',fieldname:'summary'}]});
        dialog.fields_dict.summary.$wrapper.html(`<p><strong>${data.enabled ? 'New quotations use IDs without SAL-.' : 'Remove SAL- from new and existing quotation IDs.'}</strong></p>
            <p>Existing quotations remaining: <strong>${data.remaining}</strong></p>
            <p>Migration: ${esc(state.status || 'Not started')} · ${state.completed || 0} / ${state.total || data.remaining}</p>
            ${state.error ? '<p class="text-danger">'+esc(state.error)+'</p>' : ''}
            ${data.examples.map(r=>'<p>'+esc(r.old)+' → '+esc(r.new)+'</p>').join('')}
            <p>Linked records, attachments and history are retained. Previously issued PDF contents remain unchanged.</p>
            ${data.conflicts.length ? '<p class="text-danger">Conflicting IDs: '+data.conflicts.map(esc).join(', ')+'</p>' : ''}`);
        if (!data.conflicts.length && !['Running','Queued'].includes(state.status) && (data.remaining || !data.enabled)) {
            dialog.set_primary_action(__('Apply to New and Existing Quotations'),async()=>{
                await frappe.call({method:base+'start',type:'POST',freeze:true});
                dialog.hide(); await show();
            });
        }
        dialog.set_secondary_action_label(__('Refresh Status'));
        dialog.set_secondary_action(()=>{dialog.hide();show();});
        dialog.show();
    }
    for (const dt of ['Quotation','Document Naming Settings']) frappe.ui.form.on(dt,{
        refresh(frm) {
            if (frappe.session.user==='Administrator' || frappe.user.has_role('System Manager'))
                frm.add_custom_button(__('Quotation Numbering'),show,__('Administration'));
        }
    });
})();
