frappe.ui.form.on("Lead", {
    refresh: function(frm) {
        setTimeout(() => {
            $('a[data-label="Customer"]').hide();
            $('a[data-label="Quotation"]').hide();
            $('a[data-label="Prospect"]').hide();
        }, 500);

        frm.page.remove_inner_button("Opportunity", "Create");

        frm.page.add_inner_button("Opportunity", function () {
            frappe.call({
                method: "erpnext.crm.doctype.lead.lead.make_opportunity",
                args: { source_name: frm.docname },
                freeze: true,
                callback: function(r) {
                    if (!r.exc && r.message) {
                        r.message.sales_stage = "Proposal";
                        r.message.custom_organization_name = frm.doc.company_name;
                        frappe.model.sync(r.message);
                        frappe.set_route("Form", r.message.doctype, r.message.name);
                    }
                }
            });
        }, "Create");
    }
});