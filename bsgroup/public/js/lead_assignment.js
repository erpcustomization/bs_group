// Intake coordinators hand over one Lead to one eligible salesperson.
frappe.ui.form.on('Lead', {
    refresh(frm) {
        frm._bsi_sales_transfer = null;
        if (frm.is_new() || !frappe.user.has_role('BS Lead Intake Manager') || !frm.perm?.some(p => p.write)) return;
        const transfer = async (to_user) => {
            if (frm.is_dirty()) {
                frappe.msgprint(__('Save your changes before assigning this Lead.'));
                return false;
            }
            const r = await frappe.call({method:'bsgroup.lead_assignment.transfer',
                args:{name:frm.doc.name,to_user,expected_modified:frm.doc.modified},
                freeze:true,freeze_message:__('Assigning Lead…')});
            if (r.exc || !r.message) return false;
            frappe.show_alert({message:__('Lead assigned successfully'),indicator:'green'});
            if (r.message.can_read) await frm.reload_doc();
            else await frappe.set_route('List','Lead');
            return true;
        };
        frm._bsi_sales_transfer = transfer;
        const open = async () => {
            if (frm.is_dirty()) return frappe.msgprint(__('Save your changes before assigning this Lead.'));
            const r = await frappe.call({method:'bsgroup.lead_assignment.choices',args:{name:frm.doc.name}});
            const people = r.message || [];
            const d = new frappe.ui.Dialog({title:__('Assign salesperson'),fields:[
                {fieldname:'person',fieldtype:'Select',label:__('Salesperson'),reqd:1,
                    options:[{value:'',label:__('Select salesperson')},...people.map(p=>({value:p.value,label:p.label+' ('+p.value+')'}))]},
                {fieldtype:'HTML',options:'<p>'+__('The selected salesperson becomes the Lead Owner and receives the assignment.')+'</p>'}
            ],primary_action_label:__('Assign'),primary_action:async v=>{if(await transfer(v.person)) d.hide();}});
            d.show();
        };
        frm.add_custom_button(__('Assign salesperson'), open);
        if (frm.assign_to) frm.assign_to.add = open;
    }
});
