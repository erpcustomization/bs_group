// Intake coordinators hand over one Lead to one eligible salesperson.
frappe.ui.form.on('Lead', {
    refresh(frm) {
        const hideAssignment = ['erp-om.bitssecureit.com', 'erp-om.k.frappe.cloud']
            .includes(window.location.hostname);
        if (hideAssignment) frm.remove_custom_button(__('Assign salesperson'));
        // Realtime doc_update can arrive before the transfer response. Its delayed
        // reload must not reopen a record after the sender loses permission.
        if (!frm._bsi_handover_reload_guard) {
            frm._bsi_handover_reload_guard = true;
            const reload = frm.reload_doc.bind(frm);
            frm.reload_doc = (...args) => {
                if (frm._bsi_handover_pending || frm._bsi_handed_over === frm.doc.name) return Promise.resolve();
                return reload(...args);
            };
            frm.debounced_reload_doc = () => {
                clearTimeout(frm._bsi_handover_refresh_timer);
                frm._bsi_handover_refresh_timer = setTimeout(() => frm.reload_doc(), 1000);
            };
        }
        frm._bsi_sales_transfer = null;
        if (frm.is_new() || !frappe.user.has_role('BS Lead Intake Manager') || !frm.perm?.some(p => p.write)) return;
        const transfer = async (to_user) => {
            if (frm.is_dirty()) {
                frappe.msgprint(__('Save your changes before assigning this Lead.'));
                return false;
            }
            if (frm._bsi_handover_pending) return false;
            const name = frm.doc.name;
            frm._bsi_handover_pending = true;
            clearTimeout(frm._bsi_handover_refresh_timer);
            try {
                const r = await frappe.call({method:'bsgroup.lead_assignment.transfer',
                    args:{name,to_user,expected_modified:frm.doc.modified,expected_owner:frm.doc.lead_owner || ""},
                    freeze:true,freeze_message:__('Assigning Lead…')});
                if (r.exc || !r.message) return false;
                if (!r.message.can_read) frm._bsi_handed_over = name;
                frm._bsi_handover_pending = false;
                clearTimeout(frm._bsi_handover_refresh_timer);
                if (r.message.can_read) await frm.reload_doc();
                else await frappe.set_route('List','Lead');
                frappe.show_alert({message:__('Lead assigned successfully'),indicator:'green'});
                return true;
            } finally {
                frm._bsi_handover_pending = false;
            }
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
        if (!hideAssignment) frm.add_custom_button(__('Assign salesperson'), open);
        if (frm.assign_to) frm.assign_to.add = open;
    }
});
