(() => {
    frappe.bsi_create_supply_cost_sheet = async function(frm) {
        const response = await frappe.call({method:'bsgroup.opportunity_intake.create_supply_cost_sheet',
            args:{opportunity:frm.doc.name}, freeze:true, freeze_message:__('Creating Deal Cost Sheet…')});
        const result = response.message;
        if (!result?.name) return;
        await frm.reload_doc();
        frappe.show_alert({message: result.created
            ? __('Deal Cost Sheet {0} created.', [result.name])
            : __('Deal Cost Sheet {0} already exists.', [result.name]), indicator:'green'}, 8);
    };
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
            button.title = __('Save Opportunity and create Deal Cost Sheet');
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
                    frappe.show_alert({message:__('Value confirmed. Click Submit Opportunity to create the Opportunity and its Deal Cost Sheet.'),indicator:'green'});
                    frm.trigger('bsi_update_submit');
                    return;
                }
                frm._supply_handoff = true;
                button.disabled = true;
                try {
                    if (frm.is_new() || frm.is_dirty()) await frm.save();
                    if (frm.is_new() || frm.is_dirty() || frm.doc.custom_business_type !== 'Supply') return;
                    await frappe.bsi_create_supply_cost_sheet(frm);
                } finally {
                    frm._supply_handoff = false;
                    button.disabled = false;
                }
            });
        }
        const converted = frm.doc.opportunity_from === 'Lead';
        frm.toggle_reqd('opportunity_amount', !converted);
        frm.toggle_display('opportunity_amount', !converted || !frm.is_new());
        const supply = frm.doc.custom_business_type === 'Supply';
        button.hidden = !supply || !frm.perm?.some(p => frm.is_new() ? p.create : p.write);
        frm.set_df_property('opportunity_amount', 'label', supply ? __('Opportunity Value') : __('Opportunity Amount'));
        if (supply) {
            frm.toggle_reqd('opportunity_amount', !converted);
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
    async function update(frm, notify = false) {
        const d = frm.doc;
        for (const field of ['expected_closing', 'probability', 'opportunity_owner']) {
            frm.set_df_property(field, 'hidden', 1);
        }
        frm.set_df_property('opportunity_from', 'hidden', 1);
        if (!frm.fields_dict.custom_business_type) return;
        supplyValue(frm);
        const amount = frm.fields_dict.opportunity_amount?.$wrapper?.[0];
        const presales = frm.fields_dict.custom_presales_support?.$wrapper?.[0];
        if (amount && presales && amount.nextElementSibling !== presales) amount.after(presales);
        const routed = ['Service', 'Supply and Installation'].includes(d.custom_business_type);
        frm.set_df_property('sales_stage', 'hidden', 1);
        frm.set_df_property('sales_stage', 'reqd', 0);
        frm.toggle_reqd('custom_business_type', frm.is_new() || !!d.custom_business_type);
        for (const field of ['custom_business_type', 'custom_service_type', 'custom_service_survey', 'custom_installation_type', 'custom_camera_count', 'custom_presales_support']) {
            frm.set_df_property(field, 'read_only', !!d.custom_site_survey_request);
        }
        for (const field of ['custom_service_details', 'custom_site_survey_needed', 'custom_presales_required', 'custom_elv_site_survey_required', 'custom_technical_site_survey_required']) {
            frm.set_df_property(field, 'depends_on', '');
            frm.set_df_property(field, 'mandatory_depends_on', '');
            frm.toggle_reqd(field, false);
            frm.toggle_display(field, false);
        }
        for (const field of ['custom_service_survey', 'custom_presales_support']) {
            // Keep the dependency active: clearing it leaves Frappe's initial
            // hidden_due_to_dependency flag stuck on a blank new Opportunity.
            frm.set_df_property(field, 'depends_on', "eval:['Service','Supply and Installation'].includes(doc.custom_business_type)");
            frm.set_df_property(field, 'mandatory_depends_on', '');
            frm.toggle_display(field, routed);
            frm.toggle_reqd(field, routed);
        }
        frm.layout.refresh_dependency();
        if (!d.custom_site_survey_request) {
            await frm.set_value({
                custom_presales_required: routed && d.custom_presales_support === 'Yes' ? 1 : 0,
                custom_elv_site_survey_required: routed && d.custom_service_survey === 'Site Survey by ELV' ? 1 : 0,
                custom_technical_site_survey_required: routed && d.custom_service_survey === 'Site Survey by Technical Team' ? 1 : 0
            });
        }
    }
    frappe.ui.form.on('Opportunity', {
        onload(frm) {
            if (frm.is_new()) frm.set_value('opportunity_owner', frappe.session.user);
        },
        refresh(frm) { positionStatus(frm); return update(frm); },
        status(frm) { positionStatus(frm); },
        opportunity_from(frm) {
            frm.set_df_property('opportunity_from', 'hidden', 1);
        },
        async custom_business_type(frm) {
            if (!frm.doc.custom_site_survey_request) await frm.set_value({custom_service_survey: '', custom_service_details: ''});
            if (!frm.doc.custom_site_survey_request) await frm.set_value({custom_service_type: '', custom_installation_type: '', custom_camera_count: 0, custom_site_survey_needed: '', custom_presales_support: '', custom_presales_required: 0, custom_elv_site_survey_required: 0, custom_technical_site_survey_required: 0});
            await update(frm);
            frm.trigger('refresh');
        },
        async custom_installation_type(frm) {
            if (!frm.doc.custom_site_survey_request) await frm.set_value('custom_camera_count', 0);
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
        custom_presales_support(frm) { return update(frm); }
    });
})();
