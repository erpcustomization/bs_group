frappe.ui.form.on("Purchase Invoice", {
    refresh(frm) {
        if (!frm.doc.custom_bsp_managed || frm.is_new()) return;

        frappe.route_options = {bsp_invoice: frm.doc.name};
        frappe.set_route("bs-procurement");
    }
});
