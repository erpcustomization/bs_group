frappe.ui.form.on('Quotation', {
    refresh: function(frm) {
        reduce_subject_height(frm)
        set_lead_name(frm)
        frm.set_df_property('customer_name', 'hidden', 1);
        setTimeout(function() {
            frm.remove_custom_button('Set as Lost');
        }, 500);
        if (frm.doc.__islocal) {
            apply_company_tax(frm);
        }
    },
    company: function(frm) {
        apply_company_tax(frm);
    },
    party_name: function(frm){
        set_lead_name(frm)
        frm.set_df_property('customer_name', 'hidden', 1);
    },
    custom_apply_exclude_to_all_items: function(frm) {
        exclude_all_items(frm);
    },
    custom_pipeline_stage: function(frm) {
        prompt_lost_reason_if_needed(frm);
    },
    onload: function(frm) {
        if (!frm.doc.custom_designation) {
            frappe.db.get_value("Employee",
                { user_id: frappe.session.user },
                [ "designation", "cell_number"]
            ).then(r => {
                if (r && r.message && r.message.designation) {
                    frm.set_value("custom_designation", r.message.designation);
                    frm.set_value("custom_phone__no", r.message.cell_number)
                }
            });
        }
    }
});

frappe.ui.form.on('Quotation Item', {
    item_code: function(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        if (!row.item_code) return;
        frappe.db.get_value("Item", row.item_code, ["item_name", "brand"]).then(r => {
            if (r && r.message) {
                frappe.model.set_value(cdt, cdn, "item_name", r.message.item_name);
                if (!row.brand) {
                    frappe.model.set_value(cdt, cdn, "brand", r.message.brand);
                }
            }
            set_customer_item(frm, cdt, cdn);
        });
    },
    item_name: function(frm, cdt, cdn) {
        set_customer_item(frm, cdt, cdn);
    },
    brand: function(frm, cdt, cdn) {
        set_customer_item(frm, cdt, cdn);
    },
    custom_exclude_item_name_and_brand: function(frm, cdt, cdn) {
        set_customer_item(frm, cdt, cdn);
    }
});

function set_lead_name(frm) {
    if (!frm.doc.party_name) return;

    if (frm.doc.quotation_to === "Lead") {
        frappe.db.get_value("Lead", frm.doc.party_name, ["lead_name", "company_name"])
            .then(r => {
                if (r.message) {
                    frm.set_value("custom_contact_person_name", r.message.lead_name);
                    frm.set_value("custom_organization_name", r.message.company_name || "");
                }
            });

    } else if (frm.doc.quotation_to === "Customer") {
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

function set_customer_item(frm, cdt, cdn) {
    let row = locals[cdt][cdn];
    let value;
    if (row.custom_exclude_item_name_and_brand) {
        value = (row.item_name || "").trim();
    } else {
        const parts = [row.brand, row.item_code, row.item_name].filter(p => p);
        value = parts.join(" - ");
    }
    frappe.model.set_value(cdt, cdn, "custom_customer_item_name", value);
    setTimeout(() => {
        frappe.model.set_value(cdt, cdn, "description", value);
    }, 800);
}

function exclude_all_items(frm) {
    const value = frm.doc.custom_apply_exclude_to_all_items ? 1 : 0;
    (frm.doc.items || []).forEach(row => {
        frappe.model.set_value(row.doctype, row.name, "custom_exclude_item_name_and_brand", value);
        set_customer_item(frm, row.doctype, row.name);
    });
    frm.refresh_field("items");
}

function apply_company_tax(frm) {
    if (!frm.doc.company) return;

    frappe.db.get_list("Sales Taxes and Charges Template", {
        filters: [["company", "=", frm.doc.company], ["name", "like", "%UAE VAT 5%%"]],
        fields: ["name"],
        limit: 1
    }).then(list => {
        if (list && list.length) {
            frm.set_value("taxes_and_charges", list[0].name);
        }
    });
}

function prompt_lost_reason_if_needed(frm) {
    const stagesNeedingReason = ["Lost", "Cancelled"];
    if (!stagesNeedingReason.includes(frm.doc.custom_pipeline_stage)) return;
    if (frm.doc.custom_lost_reason) return;

    frappe.prompt(
        [
            {
                fieldname: "custom_lost_reason",
                fieldtype: "Small Text",
                label: "Reason",
                reqd: 1,
            },
        ],
        (values) => {
            frm.set_value("custom_lost_reason", values.custom_lost_reason);
        },
        `Reason for marking as ${frm.doc.custom_pipeline_stage}`,
        "Save"
    );
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