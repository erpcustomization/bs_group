frappe.ui.form.on("Material Request", {
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