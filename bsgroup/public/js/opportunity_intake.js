(() => {
    function supplyValue(frm) {
        const amount = frm.fields_dict.opportunity_amount;
        const wrapper = amount?.$wrapper?.[0];
        const anchor = frm.fields_dict.custom_business_type?.$wrapper?.[0];
        if (!wrapper || !anchor) return;
        if (!frm._supply_amount_home) {
            frm._supply_amount_home = document.createComment('Opportunity amount original position');
            wrapper.before(frm._supply_amount_home);
        }
        let button = wrapper.querySelector('.bsi-supply-ok');
        if (!button) {
            button = document.createElement('button');
            button.type = 'button';
            button.className = 'btn btn-primary btn-sm bsi-supply-ok';
            button.textContent = __('OK');
            button.title = __('Save Opportunity and open Deal Cost Sheet');
            button.style.marginTop = '8px';
            wrapper.append(button);
            button.addEventListener('click', async () => {
                if (frm._supply_handoff || frm.doc.custom_business_type !== 'Supply') return;
                if (!(Number(frm.doc.opportunity_amount) > 0)) {
                    frappe.msgprint(__('Enter an Opportunity Value greater than zero.'));
                    amount.set_focus();
                    return;
                }
                if (frm.is_new()) {
                    frm._supply_open_dcs = true;
                    frappe.show_alert({message:__('Value confirmed. Click Submit Opportunity to create the Opportunity and open the Deal Cost Sheet.'),indicator:'green'});
                    frm.trigger('bsi_update_submit');
                    return;
                }
                frm._supply_handoff = true;
                button.disabled = true;
                try {
                    if (frm.is_new() || frm.is_dirty()) await frm.save();
                    if (frm.is_new() || frm.is_dirty() || frm.doc.custom_business_type !== 'Supply') return;
                    await frappe.new_doc('Deal Cost Sheet', {
                        opportunity: frm.doc.name,
                        party_type: frm.doc.opportunity_from,
                        party: frm.doc.party_name,
                        organisation_name: frm.doc.custom_organization_name,
                        subject: frm.doc.custom_subject || frm.doc.title
                    });
                } finally {
                    frm._supply_handoff = false;
                    button.disabled = false;
                }
            });
        }
        const supply = frm.doc.custom_business_type === 'Supply';
        button.hidden = !supply || !frm.perm?.some(p => frm.is_new() ? p.create : p.write);
        frm.set_df_property('opportunity_amount', 'label', supply ? __('Opportunity Value') : __('Opportunity Amount'));
        if (supply) {
            frm.toggle_reqd('opportunity_amount', true);
            if (anchor.nextElementSibling !== wrapper) anchor.after(wrapper);
        } else if (wrapper.previousSibling !== frm._supply_amount_home) {
            frm._supply_amount_home.after(wrapper);
        }
    }
    function positionStatus(frm) {
        const field = frm.fields_dict.status;
        const wrapper = field?.$wrapper?.[0];
        if (!wrapper) return;
        const root = frm.wrapper[0] || frm.wrapper;
        const host = wrapper.closest('.tab-pane') || root.querySelector('.tab-pane');
        if (!host) return;
        let bar = host.querySelector('.bsi-opportunity-status');
        if (!bar) {
            bar = document.createElement('div');
            bar.className = 'bsi-opportunity-status';
            host.prepend(bar);
            const style = document.createElement('style');
            style.textContent = `
                .bsi-opportunity-status{display:flex;justify-content:flex-end;padding:4px 0 8px}
                .bsi-opportunity-status .frappe-control{display:flex;align-items:center;gap:10px;margin:0!important}
                .bsi-opportunity-status .form-group{display:flex;align-items:center;gap:10px;margin:0!important}
                .bsi-opportunity-status .control-label{margin:0!important;font-weight:600!important;color:#172b4d!important}
                .bsi-opportunity-status .control-input-wrapper{width:180px}
                .bsi-opportunity-status .help-box,.bsi-opportunity-status .fieldname{display:none}
                .bsi-opportunity-form .bsi-opportunity-status select.form-control{background:var(--status-bg)!important;color:var(--status-text)!important;border-color:var(--status-border)!important;border-radius:8px!important;min-height:34px;font-weight:600}
                .bsi-opportunity-status option{background:white;color:#172b4d}
            `;
            bar.append(style);
        }
        if (wrapper.parentElement !== bar) bar.append(wrapper);
        const palette = frm.doc.status === 'Open' ? ['#ddd6fe','#5b21b6','#a78bfa']
            : frm.doc.status === 'Lost' ? ['#c92a2a','#ffffff','#c92a2a']
            : ['Converted','Closed'].includes(frm.doc.status) ? ['#087f5b','#ffffff','#087f5b']
            : ['#1d5fc4','#ffffff','#1d5fc4'];
        ['--status-bg','--status-text','--status-border'].forEach((key,i)=>bar.style.setProperty(key,palette[i]));
    }
    const isCctv = d => d.custom_business_type === 'Supply and Installation' && d.custom_installation_type === 'CCTV';
    async function update(frm, notify = false) {
        const d = frm.doc;
        for (const field of ['expected_closing', 'probability', 'opportunity_owner']) {
            frm.set_df_property(field, 'hidden', 1);
        }
        frm.set_df_property('opportunity_from', 'hidden', d.opportunity_from === 'Customer');
        if (!frm.fields_dict.custom_business_type) return;
        supplyValue(frm);
        const cctv = isCctv(d), small = cctv && d.custom_camera_count > 0 && d.custom_camera_count < 30;
        const blocked = d.custom_business_type === 'Supply' || small;
        frm.set_df_property('sales_stage', 'hidden', 1);
        frm.set_df_property('sales_stage', 'reqd', 0);
        frm.toggle_reqd('custom_business_type', frm.is_new() || !!d.custom_business_type);
        for (const field of ['custom_business_type', 'custom_service_type', 'custom_service_survey', 'custom_service_details', 'custom_installation_type', 'custom_camera_count', 'custom_site_survey_needed']) {
            frm.set_df_property(field, 'read_only', !!d.custom_site_survey_request);
        }
        const service = d.custom_business_type === 'Service';
        frm.toggle_display('custom_presales_required', !blocked && !cctv && !service && !!d.custom_business_type);
        const presales = frm.fields_dict.custom_presales_required?.$wrapper?.[0];
        const anchor = frm.fields_dict.custom_site_survey_needed?.$wrapper?.[0];
        if (presales && anchor && anchor.nextElementSibling !== presales) anchor.after(presales);
        for (const field of ['custom_elv_site_survey_required', 'custom_technical_site_survey_required']) {
            frm.set_df_property(field, 'depends_on', `eval:doc.custom_presales_required && doc.custom_business_type !== 'Service' && !(doc.custom_business_type === 'Supply and Installation' && doc.custom_installation_type === 'CCTV')`);
            frm.toggle_display(field, !blocked && !cctv && !service && !!d.custom_presales_required);
        }
        if (!d.custom_site_survey_request) {
            if (service) {
                const elv = d.custom_service_survey === 'Site Survey by ELV' ? 1 : 0;
                const technical = d.custom_service_survey === 'Site Survey by Technical Team' ? 1 : 0;
                await frm.set_value({custom_presales_required: elv || technical, custom_elv_site_survey_required: elv, custom_technical_site_survey_required: technical});
            }
            else if (blocked) await frm.set_value({custom_presales_required: 0, custom_elv_site_survey_required: 0, custom_technical_site_survey_required: 0});
            else if (cctv && d.custom_camera_count >= 30) {
                const needed = d.custom_site_survey_needed === 'Yes' ? 1 : 0;
                await frm.set_value({custom_presales_required: needed, custom_elv_site_survey_required: needed, custom_technical_site_survey_required: 0});
            }
        }
        if (notify && small && frm._camera_notice !== d.custom_camera_count) {
            frm._camera_notice = d.custom_camera_count;
            frappe.msgprint({title: __('Proceed to Deal Cost Sheet'), indicator: 'blue',
                message: __('No site survey or presales required for fewer than 30 cameras. Save the Opportunity, then proceed to create the Deal Cost Sheet.')});
        }
        if (!small) frm._camera_notice = null;
    }
    frappe.ui.form.on('Opportunity', {
        onload(frm) {
            if (frm.is_new()) frm.set_value('opportunity_owner', frappe.session.user);
        },
        refresh(frm) { positionStatus(frm); return update(frm); },
        status(frm) { positionStatus(frm); },
        opportunity_from(frm) {
            frm.set_df_property('opportunity_from', 'hidden', frm.doc.opportunity_from === 'Customer');
        },
        async custom_business_type(frm) {
            if (!frm.doc.custom_site_survey_request) await frm.set_value({custom_service_survey: '', custom_service_details: ''});
            if (!frm.doc.custom_site_survey_request) await frm.set_value({custom_service_type: '', custom_installation_type: '', custom_camera_count: 0, custom_site_survey_needed: '', custom_presales_required: 0, custom_elv_site_survey_required: 0, custom_technical_site_survey_required: 0});
            await update(frm);
            frm.trigger('refresh');
        },
        async custom_installation_type(frm) {
            if (!frm.doc.custom_site_survey_request) await frm.set_value({custom_camera_count: 0, custom_site_survey_needed: '', custom_presales_required: 0, custom_elv_site_survey_required: 0, custom_technical_site_survey_required: 0});
            await update(frm);
        },
        async custom_camera_count(frm) {
            if (!frm.doc.custom_site_survey_request && frm.doc.custom_site_survey_needed) await frm.set_value('custom_site_survey_needed', '');
            return update(frm, true);
        },
        custom_site_survey_needed(frm) { return update(frm); },
        async custom_service_type(frm) {
            if (!frm.doc.custom_site_survey_request) await frm.set_value('custom_service_survey', '');
            return update(frm);
        },
        custom_service_survey(frm) { return update(frm); },
        custom_presales_required(frm) { return update(frm); }
    });
})();
