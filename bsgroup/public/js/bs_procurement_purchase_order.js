frappe.ui.form.on("Purchase Order", {
    refresh(frm) {
        if (!frm.doc.custom_bsp_managed || frm.is_new()) return;
        frm.set_intro(__("This Purchase Order is linked to a BS Purchase Requisition. Use Supplier comparison and approval to record quotations and send it to Mohan."), "blue");
        frm.add_custom_button(__("Supplier comparison and approval"), async () => {
            if (frm.is_dirty()) await frm.save();
            frappe.route_options = {
                bsp_request: frm.doc.custom_bsp_material_request,
                bsp_order: frm.doc.name
            };
            frappe.set_route("bs-procurement");
        });
        frm.add_custom_button(__("Purchase Requisition"), () => {
            frappe.route_options = {bsp_request: frm.doc.custom_bsp_material_request};
            frappe.set_route("bs-procurement");
        });
    }
});
