frappe.ui.form.on('Delivery Request', {
    refresh(frm) {
        const completed=frm.doc.status==='Completed';
        frm.set_df_property('notes','read_only',completed);
        frm.set_df_property('proof','read_only',completed);
        if(!frm.is_new() && !completed && frm.perm?.some(p=>p.write)) {
            frm.add_custom_button(__('Complete Delivery'),()=>{
                frappe.confirm(__('Confirm delivery is complete. Your notes and private attachment will be retained as proof.'),async()=>{
                    if(frm.is_dirty()) await frm.save();
                    const {message}=await frappe.call({method:'bsgroup.supply_delivery.complete',args:{name:frm.doc.name},freeze:true,freeze_message:__('Completing delivery…')});
                    if(message?.status==='Completed') {await frm.reload_doc();frappe.show_alert({message:__('Delivery and project updated.'),indicator:'green'});}
                });
            });
        }
    }
});
