frappe.ui.form.on('Site Survey Request', {
    refresh(frm) {
        for (const field of ['custom_service_details', 'custom_survey_instructions', 'title',
            'organization', 'company', 'currency', 'opportunity_amount', 'presales_request',
            'sales_details', 'salesperson', 'salesperson_name', 'requested_by',
            'contact_person', 'contact_email', 'contact_phone']) {
            frm.set_df_property(field, 'hidden', 1);
        }
        const root = frm.page.wrapper[0] || frm.page.wrapper;
        root.classList.add('bsi-survey-form');
        if (!root.querySelector('.bsi-survey-style')) {
            const style = document.createElement('style');
            style.className = 'bsi-survey-style';
            style.textContent = '.bsi-survey-form .page-actions .primary-action,.bsi-survey-form .page-actions .menu-btn-group{display:none!important}.bsi-survey-submit-bar{display:flex;justify-content:flex-end;align-items:center;gap:12px;padding:10px 0}.bsi-survey-status{padding:8px 12px;border-radius:8px;font-weight:600;background:#e3edff;color:#174e9b}.bsi-survey-status.submitted{background:#dcfce7;color:#166534}';
            root.append(style);
        }
        frm.clear_custom_buttons();
        frm.page.clear_primary_action();
        frm.set_df_property('status', 'hidden', 1);
        const host = frm.layout.wrapper[0] || frm.layout.wrapper;
        let bar = host.querySelector('.bsi-survey-submit-bar');
        if (!bar) {
            bar = document.createElement('div');
            bar.className = 'bsi-survey-submit-bar';
            host.prepend(bar);
        }
        bar.replaceChildren();
        const done = frm.doc.status === 'Completed';
        const label = done ? __('Submitted') : __(frm.doc.status || 'Requested');
        frm.page.set_indicator(label, done ? 'green' : 'blue');
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'btn btn-primary';
        button.textContent = __('Submit Survey');
        button.hidden = done || frm.doc.status === 'Cancelled' || !frm.perm?.some(p => p.write);
        button.onclick = async () => {
            if (frm._submitting_survey) return;
            if (!frappe.utils.strip_html(frm.doc.results || '').trim()) {
                frappe.msgprint(__('Enter the site survey results before submitting.'));
                return;
            }
            const previous = frm.doc.status;
            frm._submitting_survey = true;
            button.disabled = true;
            try {
                await frm.set_value('status', 'Completed');
                await frm.save();
                if (frm.is_dirty()) await frm.set_value('status', previous);
                else frappe.show_alert({message:__('Survey submitted.'),indicator:'green'});
            } catch (error) {
                await frm.set_value('status', previous);
                throw error;
            } finally {
                frm._submitting_survey = false;
                button.disabled = false;
            }
        };
        const caption = document.createElement('strong');
        caption.textContent = __('Status');
        const status = document.createElement('span');
        status.className = 'bsi-survey-status' + (done ? ' submitted' : '');
        status.setAttribute('role', 'status');
        status.textContent = label;
        bar.append(button, caption, status);
    }
});
