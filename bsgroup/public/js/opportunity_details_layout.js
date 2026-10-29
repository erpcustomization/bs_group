(() => {
    async function leadDetails(frm) {
        const root = frm.wrapper[0] || frm.wrapper;
        const details = root.querySelector('#opportunity-__details');
        if (!details) return;
        let box = details.querySelector('.bsi-source-lead');
        const lead = frm.doc.opportunity_from === 'Lead' && frm.doc.party_name;
        root.classList.toggle('bsi-has-source-lead', !!lead);
        if (!root.querySelector('.bsi-source-lead-style')) {
            const style = document.createElement('style');
            style.className = 'bsi-source-lead-style';
            style.textContent = '#opportunity-__details .form-links{display:none!important}';
            root.append(style);
        }
        frm.set_df_property('party_name', 'read_only', lead ? 1 : 0);
        if (!lead) { box?.remove(); return; }
        if (!box) {
            box = document.createElement('section');
            box.className = 'bsi-source-lead';
            box.style.cssText = 'background:#eef3fb;border:1px solid #dfe7f2;border-radius:10px;padding:14px;margin:10px 0;color:#172b4d';
            details.append(box);
        }
        const dashboard = details.querySelector('.form-dashboard');
        if (dashboard && box.nextElementSibling !== dashboard) dashboard.before(box);
        if (box.dataset.lead === lead) return;
        box.dataset.lead = lead;
        box.textContent = __('Loading Lead details…');
        try {
            const result = await frappe.db.get_value('Lead', lead,
                ['title','lead_name','company_name','email_id','mobile_no','phone','custom_requirement']);
            if (frm.doc.party_name !== lead || !box.isConnected) return;
            const data = result.message || {};
            box.replaceChildren();
            const heading = document.createElement('h5');
            heading.textContent = __('Lead details / request');
            box.append(heading);
            for (const [label, value] of [['Lead ID',lead],['Title',data.title],['Organization',data.company_name],
                ['Contact',data.lead_name],['Email',data.email_id],['Phone',data.mobile_no || data.phone],['Request',data.custom_requirement]]) {
                if (!value) continue;
                const row = document.createElement('div');
                row.style.cssText = 'white-space:pre-wrap;overflow-wrap:anywhere;margin-top:5px';
                const caption = document.createElement('strong');
                caption.textContent = __(label) + ': ';
                row.append(caption, document.createTextNode(String(value)));
                box.append(row);
            }
        } catch (error) {
            box.textContent = __('Lead details could not be loaded. Check access to the linked Lead.');
            delete box.dataset.lead;
        }
    }
    function arrange(frm) {
        const root = frm.wrapper[0] || frm.wrapper;
        const details = root.querySelector('#opportunity-__details');
        const additional = root.querySelector('#opportunity-contact_info');
        const business = frm.fields_dict.custom_business_type?.$wrapper?.[0];
        const amount = frm.fields_dict.opportunity_amount?.$wrapper?.[0];
        if (!details || !additional || !business || !amount) return;
        const enquiry = frm.fields_dict.custom_enquiry?.$wrapper?.[0];
        if (enquiry) {
            let box = details.querySelector('.bsi-opportunity-enquiry');
            if (!box) {
                box = document.createElement('div');
                box.className = 'bsi-opportunity-enquiry';
                box.style.cssText = 'background:#fff;border:1px solid #dfe7f2;border-radius:10px;padding:12px 14px;margin:0 0 10px;width:100%;box-shadow:0 2px 7px rgba(18,51,95,.045)';
                details.append(box);
            }
            if (enquiry.parentElement !== box) box.append(enquiry);
            enquiry.style.marginBottom = '0';
            const input = enquiry.querySelector('textarea');
            if (input) {
                input.style.cssText = 'min-height:110px;width:100%;resize:vertical';
                input.placeholder = __('Enter the customer enquiry or request here…');
            }
        }
        // Keep the one native amount control in Details for every intake route.
        // Supply still positions it immediately below its category selector.
        if (frm._supply_amount_home && !details.contains(frm._supply_amount_home.parentElement?.closest('.form-column'))) {
            business.parentElement.append(frm._supply_amount_home);
        } else if (frm._supply_amount_home && frm._supply_amount_home.parentElement !== business.parentElement) {
            business.parentElement.append(frm._supply_amount_home);
        }
        if (frm.doc.custom_business_type !== 'Supply' && frm._supply_amount_home) frm._supply_amount_home.after(amount);
        const presales = frm.fields_dict.custom_presales_support?.$wrapper?.[0];
        if (presales && amount.nextElementSibling !== presales) amount.after(presales);
        let host = additional.querySelector('.bsi-additional-sections');
        if (!host) {
            host = document.createElement('div');
            host.className = 'bsi-additional-sections';
            additional.prepend(host);
        }
        const sections = new Set();
        for (const name of ['custom_next_action','custom_next_action_date','custom_margin','custom_sales_updates','custom_stage_history','currency','utm_source','company']) {
            const wrapper = frm.fields_dict[name]?.$wrapper?.[0];
            const section = wrapper?.closest('.form-section');
            if (section && details.contains(section) && !section.contains(business) && !section.contains(amount)) sections.add(section);
        }
        for (const section of sections) host.append(section);
        const surveyResults = additional.querySelector('.bsi-survey-results');
        if (surveyResults) additional.prepend(surveyResults);
    }
    frappe.ui.form.on('Opportunity', {
        refresh(frm) { arrange(frm); return leadDetails(frm); },
        custom_business_type: arrange
    });
})();
