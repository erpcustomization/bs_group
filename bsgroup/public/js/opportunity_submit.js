(() => {
    const value = (frm,name) => frm.fields_dict[name]?.get_value?.() ?? frm.doc[name];
    const filled = v => Array.isArray(v) ? v.length > 0 : v !== null && v !== undefined && String(v).trim() !== '';
    function ready(frm) {
        if (!filled(value(frm,'party_name')) || !filled(value(frm,'custom_subject')) || !(Number(value(frm,'opportunity_amount')) > 0)) return false;
        const kind = value(frm,'custom_business_type');
        if (!kind) return false;
        for (const field of Object.values(frm.fields_dict)) {
            if (field.df.reqd && !['Section Break','Column Break','Tab Break','HTML','Button'].includes(field.df.fieldtype)
                && !filled(value(frm,field.df.fieldname))) return false;
        }
        if (kind === 'Service' && (!value(frm,'custom_service_type') || !value(frm,'custom_service_survey'))) return false;
        if (kind === 'Service' && value(frm,'custom_service_survey') === 'No Site Survey Required' && !filled(value(frm,'custom_service_details'))) return false;
        if (kind === 'Supply and Installation') {
            if (!value(frm,'custom_installation_type')) return false;
            if (value(frm,'custom_installation_type') === 'CCTV') {
                const count=Number(value(frm,'custom_camera_count'));
                if (!Number.isInteger(count) || count <= 0 || (count >= 30 && !value(frm,'custom_site_survey_needed'))) return false;
            }
        }
        const survey = frm.doc.custom_presales_required && (frm.doc.custom_elv_site_survey_required || frm.doc.custom_technical_site_survey_required);
        if (survey && (Number(frm.doc.custom_survey_step) !== 3 || !['custom_survey_instructions','custom_survey_location','custom_survey_contact_name','custom_survey_contact_phone'].every(name=>filled(value(frm,name))))) return false;
        return true;
    }
    function render(frm) {
        const root = frm.wrapper[0] || frm.wrapper;
        const status = root.querySelector('.bsi-opportunity-status');
        if (!status) return;
        let row = root.querySelector('.bsi-submit-opportunity-row');
        if (!row) {
            row = document.createElement('div');
            row.className = 'bsi-submit-opportunity-row';
            row.style.cssText = 'display:flex;justify-content:flex-end;margin:0 0 6px';
            const button = document.createElement('button');
            button.type = 'button';
            button.className = 'btn btn-primary';
            button.textContent = __('Submit Opportunity');
            button.addEventListener('click',async()=>{
                if (frm._submitting_opportunity || !frm.is_new()) return;
                if (!ready(frm)) { frappe.msgprint(__('Complete the required details and confirm the survey steps first.')); return; }
                frm._submitting_opportunity = true;
                button.disabled = true;
                try {
                    await frm.save();
                    if (frm.is_new() || frm.is_dirty()) return;
                    frappe.show_alert({message:__('Opportunity created.'),indicator:'green'});
                    if (frm.doc.custom_business_type === 'Supply' && frm._supply_open_dcs) {
                        await frappe.new_doc('Deal Cost Sheet', {
                            opportunity:frm.doc.name,party_type:frm.doc.opportunity_from,party:frm.doc.party_name,
                            organisation_name:frm.doc.custom_organization_name,subject:frm.doc.custom_subject || frm.doc.title
                        });
                    }
                } finally { frm._submitting_opportunity=false;button.disabled=false;render(frm); }
            });
            row.append(button);
            status.before(row);
        }
        row.hidden = !frm.is_new() || !ready(frm);
        // Hidden must override the inline flex display as well.
        row.style.display = row.hidden ? 'none' : 'flex';
        if (frm.is_new()) frm.page.clear_primary_action();
    }
    frappe.ui.form.on('Opportunity',{
        refresh(frm) {
            render(frm);
            $(frm.wrapper).off('input.bsi_submit change.bsi_submit').on('input.bsi_submit change.bsi_submit','input,textarea,select',()=>{
                clearTimeout(frm._submit_render_timer);
                frm._submit_render_timer=setTimeout(()=>render(frm),100);
            });
        },
        bsi_update_submit:render,
        custom_survey_step:render,
        validate(frm) {
            if (frm.is_new() && !frm._submitting_opportunity) {
                frappe.throw(__('Complete the details, then click Submit Opportunity above Status.'));
            }
        }
    });
})();
