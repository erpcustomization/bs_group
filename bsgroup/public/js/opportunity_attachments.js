(() => {
    if (window.bsOpportunityAttachments) return;
    window.bsOpportunityAttachments = true;
    async function render(frm) {
        const root = frm.wrapper[0] || frm.wrapper;
        let box = root.querySelector('.bs-opportunity-attachments');
        if (!box) {
            box = document.createElement('section');
            box.className = 'bs-opportunity-attachments';
            box.style.cssText = 'padding:12px 16px;margin:10px 0;border:1px solid #dbe5f1;border-radius:10px;background:#f7faff';
            const host = root.querySelector('.tab-pane');
            if (!host) return;
            host.append(box);
        }
        box.replaceChildren();
        $('<strong>').text(__('Supporting attachments')).appendTo(box);
        $('<p class="text-muted small">').text(__('Files attached to the Opportunity are available to its linked Presales Request.')).appendTo(box);
        if (frm.is_new()) {
            $('<p>').text(__('Save this record first to add attachments.')).appendTo(box);
            return;
        }
        if (frm.doctype === 'Opportunity' && frm.perm?.some(p=>p.write)) {
            $('<button type="button" class="btn btn-primary btn-sm">').text(__('Add attachments')).appendTo(box).on('click',()=>{
                new frappe.ui.FileUploader({doctype:frm.doctype,docname:frm.doc.name,
                    allow_multiple:true,make_attachments_public:false,allow_toggle_private:false,
                    on_success:()=>render(frm)});
            });
        }
        const list = $('<div style="display:flex;gap:10px;flex-wrap:wrap;margin-top:8px">').appendTo(box);
        try {
            const r = await frappe.call({method:'bsgroup.opportunity_attachments.files',args:{doctype:frm.doctype,name:frm.doc.name},quiet:true});
            if (!list[0].isConnected) return;
            for (const file of r.message || []) {
                const query = new URLSearchParams({doctype:frm.doctype,name:frm.doc.name,file:file.name});
                $('<a>').text(file.file_name).attr('href','/api/method/bsgroup.opportunity_attachments.download?'+query).appendTo(list);
            }
            if (!r.message?.length) list.text(__('No supporting attachments yet.'));
        } catch(e) { list.text(__('Attachments could not be loaded. Please refresh the form.')); }
    }
    for (const dt of ['Opportunity','Presales Request']) frappe.ui.form.on(dt,{refresh:render});
})();
