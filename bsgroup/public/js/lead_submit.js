(() => {
    const rootOf = frm => frm.wrapper[0] || frm.wrapper;
    const value = (frm,name) => {
        const field = frm.fields_dict[name];
        return field?.df.hidden || field?.df.read_only ? frm.doc[name] : (field?.get_value?.() ?? frm.doc[name]);
    };
    const filled = v => Array.isArray(v) ? v.length > 0 : v != null && String(v).trim() !== '';
    function ready(frm) {
        if (!filled(value(frm,'company_name')) || !filled(value(frm,'first_name')) || !filled(value(frm,'custom_requirement'))) return false;
        return Object.values(frm.fields_dict).every(field =>
            !field.df.reqd || (field.get_status && field.get_status() !== 'Write') ||
            ['Section Break','Column Break','Tab Break','HTML','Button'].includes(field.df.fieldtype) || filled(value(frm,field.df.fieldname)));
    }
    function render(frm) {
        const root = rootOf(frm), status = root.querySelector('.bsi-lead-outcome');
        if (!status) return;
        let row = status.querySelector('.bsi-submit-lead-row');
        if (!row) {
            row = document.createElement('div');
            row.className = 'bsi-submit-lead-row';
            row.style.cssText = 'width:100%;display:flex;justify-content:flex-end;margin-bottom:8px';
            const button = document.createElement('button');
            button.type = 'button'; button.className = 'btn btn-primary';
            button.addEventListener('click', async () => {
                if (frm._submitting_lead || (frm.is_new() && !ready(frm))) return;
                frm._submitting_lead = true; button.disabled = true;
                const isNew = frm.is_new();
                const input = root.querySelector('.bsi-note-composer textarea');
                const note = (input?.value || '').trim();
                try {
                    // Flush native inputs before the one explicit save.
                    for (const name of ['first_name','last_name','company_name','title','email_id','mobile_no','phone','lead_owner','custom_requirement','custom_next_follow_up_date']) {
                        const field = frm.fields_dict[name];
                        if (field && (!field.get_status || field.get_status() === 'Write')) await frm.set_value(name,value(frm,name));
                    }
                    if (note) {
                        frm.add_child('notes', {note:frappe.utils.escape_html(note).replace(/\n/g,'<br>'),added_by:frappe.session.user,added_on:frappe.datetime.now_datetime()});
                        // The note is now in the unsaved document, even if validation fails.
                        input.value = '';
                        frm.refresh_field('notes');
                    }
                    if (isNew) await frm.set_value('status','Open');
                    await frm.save();
                    if (!frm.is_new() && !frm.is_dirty()) frappe.show_alert({message:__(isNew ? 'Lead submitted.' : 'Changes saved.'),indicator:'green'});
                } finally { frm._submitting_lead = false; button.disabled = false; render(frm); }
            });
            row.append(button); status.prepend(row);
        }
        status.style.flexWrap = 'wrap';
        const button = row.querySelector('button');
        button.textContent = __(frm.is_new() ? 'Submit Lead' : 'Save Changes');
        const note = (root.querySelector('.bsi-note-composer textarea')?.value || '').trim();
        const permitted = frm.perm?.some(p => frm.is_new() ? p.create : p.write);
        row.hidden = !permitted || (frm.is_new() ? !ready(frm) : !(frm.is_dirty() || note));
        row.style.display = row.hidden ? 'none' : 'flex';
        if (frm.is_new()) frm.page.clear_primary_action();
    }
    frappe.ui.form.on('Lead', {
        refresh(frm) {
            if (frm.is_new()) {
                for (const name of ['first_name','company_name','custom_requirement']) if (frm.fields_dict[name]) frm.toggle_reqd(name,true);
            }
            render(frm);
            $(rootOf(frm)).off('.bsi_lead_submit').on('input.bsi_lead_submit change.bsi_lead_submit','input,textarea,select',()=>{
                clearTimeout(frm._lead_submit_timer);
                frm._lead_submit_timer = setTimeout(()=>render(frm),120);
            }).on('dirty.bsi_lead_submit',()=>render(frm));
        },
        bsi_lead_submission_changed: render,
        validate(frm) {
            if (frm.is_new() && !frm._submitting_lead) frappe.throw(__('Complete the details, then click Submit Lead above Status.'));
        }
    });
})();
