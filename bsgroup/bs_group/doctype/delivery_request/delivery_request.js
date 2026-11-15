frappe.ui.form.on('Delivery Request', {
    refresh(frm) {
        const completed=frm.doc.status==='Completed';
        const role=frappe.session.user===frm.doc.coordinator?'coordinator':frappe.session.user===frm.doc.delivery_person?'delivery':null;
        for(const participant of ['coordinator','delivery']) for(const field of ['notes','proof'])
            frm.set_df_property(participant+'_'+field,'read_only',completed || role!==participant || !!frm.doc[participant+'_completed_on']);
        frm.set_intro(__('Both the coordinator and delivery person must submit their own work and proof. The supply project closes only after both confirmations.'),'blue');
        if(!frm.is_new() && !completed && role && !frm.doc[role+'_completed_on'] && frm.perm?.some(p=>p.write)) {
            frm.add_custom_button(__('Submit My Work'),()=>{
                frappe.confirm(__('Submit your work and private proof? Your entry will be retained. Both participants must submit before the project closes.'),async()=>{
                    if(frm.is_dirty()) await frm.save();
                    const {message}=await frappe.call({method:'bsgroup.supply_delivery.complete',args:{name:frm.doc.name},freeze:true,freeze_message:__('Recording your work…')});
                    if(message?.status) {await frm.reload_doc();frappe.show_alert({message:message.status==='Completed'?__('Both confirmations received. Delivery and project completed.'):__('Your work is recorded. Waiting for the other participant.'),indicator:'green'});}
                });
            });
        }
    }
});
