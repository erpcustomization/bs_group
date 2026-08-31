frappe.ui.form.on("Item", {
    refresh(frm){
        frm.toggle_display("item_code", true)
    },
    item_group: function(frm){
        if (frm.doc.item_group === "Professional Services" || frm.doc.item_group === "Services"){
            frm.set_value('is_stock_item', 0)
        }
    }
})