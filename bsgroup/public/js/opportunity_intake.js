(() => {
    const isCctv = d => d.custom_business_type === 'Supply and Installation' && d.custom_installation_type === 'CCTV';
    async function update(frm, notify = false) {
        const d = frm.doc;
        for (const field of ['expected_closing', 'probability']) {
            frm.set_df_property(field, 'hidden', 1);
        }
        if (!frm.fields_dict.custom_business_type) return;
        const cctv = isCctv(d), small = cctv && d.custom_camera_count > 0 && d.custom_camera_count < 30;
        const blocked = d.custom_business_type === 'Supply' || small;
        frm.set_df_property('sales_stage', 'hidden', 1);
        frm.set_df_property('sales_stage', 'reqd', 0);
        frm.toggle_reqd('custom_business_type', frm.is_new() || !!d.custom_business_type);
        for (const field of ['custom_business_type', 'custom_service_type', 'custom_installation_type', 'custom_camera_count', 'custom_site_survey_needed']) {
            frm.set_df_property(field, 'read_only', !!d.custom_site_survey_request);
        }
        frm.toggle_display('custom_presales_required', !blocked && !cctv && !!d.custom_business_type);
        for (const field of ['custom_elv_site_survey_required', 'custom_technical_site_survey_required']) {
            frm.set_df_property(field, 'depends_on', `eval:doc.custom_presales_required && !(doc.custom_business_type === 'Supply and Installation' && doc.custom_installation_type === 'CCTV')`);
            frm.toggle_display(field, !blocked && !cctv && !!d.custom_presales_required);
        }
        if (!d.custom_site_survey_request) {
            if (blocked) await frm.set_value({custom_presales_required: 0, custom_elv_site_survey_required: 0, custom_technical_site_survey_required: 0});
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
        refresh(frm) { return update(frm); },
        async custom_business_type(frm) {
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
        custom_presales_required(frm) { return update(frm); }
    });
})();
