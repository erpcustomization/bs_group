frappe.ui.form.on("Opportunity", {
    refresh(frm){
        hide_create_button(frm);
        reduce_subject_height(frm);
        set_opportunity_status(frm);
        // A-6 / D1-D2: hand over the real party (Lead or Customer). `customer` is
        // never assigned from the organisation text - the server derives it from
        // the party when, and only when, the party is a Customer record.
        var party_defaults = {
            opportunity: frm.doc.name,
            party_type: frm.doc.opportunity_from,
            party: frm.doc.party_name,
            organisation_name: frm.doc.custom_organization_name,
            subject: frm.doc.custom_subject || frm.doc.title,
        };
        frm.remove_custom_button('Presales Request', __('Create'));
        frm.remove_custom_button('Deal Cost Sheet', __('Create'));
        if(frm.doc.custom_presales_required == 1){
            frm.add_custom_button("Presales Request", ()=>{
                if (frm.doc.custom_site_survey_request) {
                    frappe.db.get_value('Site Survey Request', frm.doc.custom_site_survey_request, 'presales_request').then(r => {
                        if (r.message && r.message.presales_request) frappe.set_route('Form', 'Presales Request', r.message.presales_request);
                    });
                    return;
                }
                if (frm.is_new() || frm.is_dirty()) {
                    frappe.msgprint(__('Save the Opportunity first. Selected survey options will create the linked requests automatically.'));
                    return;
                }
                frappe.new_doc("Presales Request", Object.assign({}, party_defaults, {
                    subject: frm.doc.custom_subject,
                    expected_close_date: frm.doc.expected_closing,
                }))
            },__("Create"))
        }
        else{
            frm.add_custom_button("Deal Cost Sheet", ()=>{
                if (frm.is_new() || frm.is_dirty()) {
                    frappe.msgprint(__('Save the Opportunity before creating the Deal Cost Sheet.'));
                    return;
                }
                frappe.new_doc("Deal Cost Sheet", Object.assign({}, party_defaults))
            },__("Create"))
        }
    },
    sales_stage: function(frm){
        set_opportunity_status(frm);
    },
    onload: function(frm) {
        if (frm.is_new()) set_lead_name(frm);
    },
    party_name: function(frm){
        set_lead_name(frm);
    }
})

function set_lead_name(frm) {
    if (!frm.doc.party_name) return;

    if (frm.doc.opportunity_from === "Lead") {
        frappe.db.get_value("Lead", frm.doc.party_name, ["lead_name", "company_name"])
            .then(r => {
                if (r.message) {
                    frm.set_value("custom_contact_person_name", r.message.lead_name);
                    frm.set_value("custom_organization_name", r.message.company_name || "");
                }
            });

    } else if (frm.doc.opportunity_from === "Customer") {
        frappe.db.get_value("Customer", frm.doc.party_name, ["customer_name", "customer_primary_contact"])
            .then(r => {
                if (r.message) {
                    frm.set_value("customer_name", r.message.customer_name);
                    frm.set_value("custom_organization_name", r.message.customer_name || "");

                    if (r.message.customer_primary_contact) {
                        frappe.db.get_doc("Contact", r.message.customer_primary_contact)
                            .then(contact => {
                                let full_name = [
                                    contact.first_name,
                                    contact.middle_name,
                                    contact.last_name
                                ].filter(Boolean).join(" ");

                                frm.set_value("custom_contact_person_name", full_name);
                            });
                    } else {
                        frm.set_value("custom_contact_person_name", "");
                    }
                }
            });
    }
}

function hide_create_button(frm) {
    setTimeout(() => {
        $('a[data-label="Supplier%20Quotation"]').hide();
        $('a[data-label="Request%20For%20Quotation"]').hide();
        $('a[data-label="Customer"]').hide();
    }, 500);
}

function set_opportunity_status(frm) {
    if (!frm.doc.sales_stage) return;

    if (frm.doc.sales_stage === "Lost" && frm.doc.status !== "Lost") {
        frm.set_value("status", "Lost");
    } 
    else if (frm.doc.sales_stage === "Won" && frm.doc.status !== "Closed") {
        frm.set_value("status", "Closed");
    }
}

function reduce_subject_height(frm){
    setTimeout(() => {
        frm.fields_dict.custom_subject.$wrapper
            .find('textarea')
            .css({
                "height": "30px",
                "min-height": "27px"
            });
    }, 300);
}

// Existing and converted records retain their original party and workflow.
frappe.ui.form.on('Opportunity', {
    onload(frm) {
        if (!frm.is_new()) return;
        frm.set_df_property('opportunity_amount', 'reqd', frm.doc.opportunity_from !== 'Lead');
        const convertedLead = frm.doc.opportunity_from === 'Lead' && !!frm.doc.party_name;
        if (!convertedLead) {
            if (frm.doc.opportunity_from !== 'Customer') {
                frm.set_value({opportunity_from: 'Customer', party_name: ''});
            }
            frm.set_df_property('party_name', 'only_select', 1);
        }
        frm.set_df_property('opportunity_from', 'read_only', 1);
    },
    refresh(frm) {
        const root = frm.page.wrapper[0] || frm.page.wrapper;
        root.classList.add('bsi-opportunity-form');
        if (root.querySelector('.bsi-opportunity-style')) return;
        const style = document.createElement('style');
        style.className = 'bsi-opportunity-style';
        style.textContent = `
            .bsi-opportunity-form{--text-color:#172b4d;--text-muted:#60718b;--border-color:#dfe7f2;color:#172b4d}
            .bsi-opportunity-form .form-layout{background:#f5f7fb!important}
            .bsi-opportunity-form .form-section{background:#fff;border-color:#dfe7f2!important;border-radius:10px;box-shadow:0 2px 7px rgba(18,51,95,.045)}
            .bsi-opportunity-form .section-head{color:#12335f!important;background:#eef3fb;border-radius:8px;padding:8px 12px;font-weight:600}
            .bsi-opportunity-form .form-tabs .nav-link.active{background:#eef3fb!important;color:#12335f!important;border-bottom:2px solid #1d5fc4!important;border-radius:7px 7px 0 0}
            .bsi-opportunity-form .control-label{color:#4c6486!important;font-size:11px;font-weight:500}
            .bsi-opportunity-form :is(input.form-control,textarea.form-control,select.form-control){background:#f8fafd!important;border:1px solid #dfe7f2!important;border-radius:6px!important;color:#172b4d}
            .bsi-opportunity-form :is(input.form-control,textarea.form-control,select.form-control):focus{background:#fff!important;border-color:#1d5fc4!important;box-shadow:0 0 0 2px rgba(29,95,196,.12)!important}
            .bsi-opportunity-form .btn-primary{background:#1d5fc4!important;border-color:#1d5fc4!important;color:white!important}
        `;
        root.append(style);
    }
});

frappe.ui.form.on('Opportunity', {
    custom_presales_required(frm) {
        if (!frm.doc.custom_presales_required && !frm.doc.custom_site_survey_request) {
            frm.set_value({custom_elv_site_survey_required: 0, custom_technical_site_survey_required: 0});
        }
    },
    refresh(frm) {
        frm.remove_custom_button(__('Site Survey Request'), __('Projects'));
        const selected = frm.doc.custom_presales_required &&
            (frm.doc.custom_elv_site_survey_required || frm.doc.custom_technical_site_survey_required);
        if (selected) {
            frm.add_custom_button(__('Site Survey Request'), async () => {
                if (frm.is_new() || frm.is_dirty()) await frm.save();
                if (frm.doc.custom_site_survey_request) {
                    frappe.set_route('Form', 'Site Survey Request', frm.doc.custom_site_survey_request);
                }
            }, __('Projects'));
        }
        for (const field of ['custom_presales_required', 'custom_elv_site_survey_required', 'custom_technical_site_survey_required']) {
            if (frm.fields_dict[field]) frm.set_df_property(field, 'read_only', !!frm.doc.custom_site_survey_request);
        }
    },
    custom_elv_site_survey_required(frm) { frm.trigger('refresh'); },
    custom_technical_site_survey_required(frm) { frm.trigger('refresh'); }
});
