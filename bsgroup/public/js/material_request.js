frappe.ui.form.on("Material Request", {
    refresh(frm) {
        if (!frm.doc.custom_bsp_managed || frm.is_new()) return;
        frm.set_intro(__("This is the standard record for your BS Purchase Requisition. No separate Material Request is required."), "blue");
        frm.add_custom_button(__("Process Purchase Requisition"), () => {
            frappe.route_options = {bsp_request: frm.doc.name};
            frappe.set_route("bs-procurement");
        });
    },
    custom_project: function(frm) {
        if (frm.doc.custom_project) {
            frappe.db.get_value(
                "Deal Cost Sheet",
                { project: frm.doc.custom_project },
                "name"
            ).then(r => {
                if (r.message && r.message.name) {
                    frm.set_value("custom_deal_cost_sheet", r.message.name);
                } else {
                    frm.set_value("custom_deal_cost_sheet", "");
                    frappe.msgprint("No Deal Cost Sheet found for this Project.");
                }
            });
        } else {
            frm.set_value("custom_deal_cost_sheet", "");
        }
    }
});
