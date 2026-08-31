frappe.ui.form.on("Opportunity", {
    refresh(frm){
        hide_create_button(frm);
        reduce_subject_height(frm);
        set_opportunity_status(frm);
        if(frm.doc.custom_presales_required == 1){
            frm.add_custom_button("Presales Request", ()=>{
                frappe.new_doc("Presales Request", {
                    opportunity: frm.doc.name,
                    customer: frm.doc.custom_organization_name,
                    subject: frm.doc.custom_subject,
                    expected_close_date: frm.doc.expected_closing,
                })
            },__("Create"))
        }
        else{
            frm.add_custom_button("Deal Cost Sheet", ()=>{
                frappe.new_doc("Deal Cost Sheet", {
                    opportunity: frm.doc.name,
                    customer: frm.doc.custom_organization_name,
                })
            },__("Create"))
        }
    },
    sales_stage: function(frm){
        set_opportunity_status(frm);
    },
    onload: function(frm) {
        set_lead_name(frm);
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

