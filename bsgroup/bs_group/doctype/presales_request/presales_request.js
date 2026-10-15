// Copyright (c) 2026, Tridots Tech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Presales Request", {
    onload(frm) {
        if (!frm.doc.requested_by) {
            frm.set_value("requested_by", frappe.session.user);
        }
    },
    opportunity(frm) {
        // A-6: the party comes from the Opportunity as recorded there. `customer`
        // is derived on the server from the party and is never set here.
        if (!frm.doc.opportunity) return;
        frappe.db.get_value("Opportunity", frm.doc.opportunity,
            ["opportunity_from", "party_name", "custom_organization_name"]
        ).then(r => {
            if (!r.message) return;
            let opp = r.message;
            if ((opp.opportunity_from === "Customer" || opp.opportunity_from === "Lead") && opp.party_name) {
                frm.set_value("party_type", opp.opportunity_from);
                frm.set_value("party", opp.party_name);
                frm.set_value("organisation_name", opp.custom_organization_name || "");
                frm.set_value("is_new_customer", opp.opportunity_from === "Lead" ? 1 : 0);
            }
        });
    },
    party_type(frm) {
        if (frm.doc.party && frm.doc.party_type) {
            // party is a Dynamic Link: a change of type invalidates the value.
            frm.set_value("party", "");
        }
    },
    party(frm) {
        if (!frm.doc.party || !frm.doc.party_type) return;
        let field = frm.doc.party_type === "Customer" ? "customer_name" : "company_name";
        frappe.db.get_value(frm.doc.party_type, frm.doc.party, field).then(r => {
            if (r.message) frm.set_value("organisation_name", r.message[field] || frm.doc.party);
        });
    },
    refresh(frm){
        set_completion_date(frm);
        set_status_indicator(frm);
        reduce_subject_height(frm);
        set_status_value(frm);
        frm.toggle_reqd("site_visit", frm.doc.site_visit_required == 1);
        if(frm.doc.docstatus == 1){
            frm.add_custom_button("Deal Cost Sheet", () => {
                frappe.new_doc("Deal Cost Sheet", {
                    opportunity: frm.doc.opportunity,
                    presales_request : frm.doc.name,
                    party_type: frm.doc.party_type,
                    party: frm.doc.party,
                    organisation_name: frm.doc.organisation_name,
                    deal_owner: frm.doc.requested_by,
                    company: frm.doc.company,
                    subject: frm.doc.subject
                })
            },__("Create"))
        }
    },
    status(frm){
        set_completion_date(frm)
    },
    site_visit_required(frm){
        frm.toggle_reqd("site_visit", frm.doc.site_visit_required == 1);
    }
});

function set_completion_date(frm) {
    if (frm.doc.status === "Completed") {
        frm.set_df_property("completion_date", "read_only", 0);
        frm.set_df_property("completion_date", "reqd", 1);
    } else {
        frm.set_df_property("completion_date", "read_only", 1);
        frm.set_df_property("completion_date", "reqd", 0);
    }
}

function reduce_subject_height(frm){
    setTimeout(() => {
        frm.fields_dict.subject.$wrapper
            .find('textarea')
            .css({
                "height": "30px",
                "min-height": "27px"
            });
    }, 300);
}

function set_status_indicator(frm){
    let color = {
        "Draft": "gray",
        "Open": "blue",
        "Assigned": "cyan",
        "In Progress": "orange",
        "Awaiting Sales Input": "yellow",
        "Awaiting Customer Input": "purple",
        "Costing in Progress": "pink",
        "Ready for Quotation": "green",
        "Submitted to Sales": "blue",
        "Completed": "darkgreen",
        "On Hold": "darkgrey",
        "Won": "lime",
        "Lost": "red",
        "Cancelled": "darkred"
    }[frm.doc.status] || "black";
    frm.page.set_indicator(frm.doc.status, color);
}

function set_status_value(frm) {
    if (frm.doc.docstatus == 1 && frm.doc.status != "Submitted to Sales" && frm.doc.status != "Open") {
        frm.set_value("status", "Open");
        frm.save("Update");
    }
}