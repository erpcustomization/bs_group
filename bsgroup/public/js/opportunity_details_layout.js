(() => {
    function arrange(frm) {
        const root = frm.wrapper[0] || frm.wrapper;
        const details = root.querySelector('#opportunity-__details');
        const additional = root.querySelector('#opportunity-contact_info');
        const business = frm.fields_dict.custom_business_type?.$wrapper?.[0];
        const amount = frm.fields_dict.opportunity_amount?.$wrapper?.[0];
        if (!details || !additional || !business || !amount) return;
        // Keep the one native amount control in Details for every intake route.
        // Supply still positions it immediately below its category selector.
        if (frm._supply_amount_home && !details.contains(frm._supply_amount_home.parentElement?.closest('.form-column'))) {
            business.parentElement.append(frm._supply_amount_home);
        } else if (frm._supply_amount_home && frm._supply_amount_home.parentElement !== business.parentElement) {
            business.parentElement.append(frm._supply_amount_home);
        }
        if (frm.doc.custom_business_type !== 'Supply' && frm._supply_amount_home) frm._supply_amount_home.after(amount);
        let host = additional.querySelector('.bsi-additional-sections');
        if (!host) {
            host = document.createElement('div');
            host.className = 'bsi-additional-sections';
            additional.prepend(host);
        }
        const sections = new Set();
        for (const name of ['custom_next_action','custom_next_action_date','custom_margin','custom_sales_updates','currency','utm_source','company']) {
            const wrapper = frm.fields_dict[name]?.$wrapper?.[0];
            const section = wrapper?.closest('.form-section');
            if (section && details.contains(section) && !section.contains(business) && !section.contains(amount)) sections.add(section);
        }
        for (const section of sections) host.append(section);
    }
    frappe.ui.form.on('Opportunity', {
        refresh: arrange,
        custom_business_type: arrange
    });
})();
