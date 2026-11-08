frappe.ui.form.on('Project', {
    refresh(frm) {
        const choices=[['custom_bs_supply_projects','BS Supply Projects'],['custom_bs_elv_projects','BS ELV Projects'],['custom_bs_infra_projects','BS Infra Projects'],['custom_bs_3cx_projects','BS 3CX Projects']];
        if(!choices.every(([field])=>frm.fields_dict[field])) {
            if(frappe.user.has_role('System Manager')) frm.add_custom_button(__('Set Up Project Modules'),async()=>{
                await frappe.call({method:'bsgroup.project_modules.setup',type:'POST',freeze:true});
                frappe.msgprint(__('The four project modules are ready. Reload the page to load the new menus and project selections.'));
            });
            return;
        }
        frm.add_custom_button(__('Project Modules'),()=>{
            const dialog=new frappe.ui.Dialog({title:__('Project Modules'),fields:choices.map(([field,label])=>({fieldtype:'Check',fieldname:field,label,default:frm.doc[field]||0,read_only:!frm.perm.some(p=>p.write)})),
                primary_action_label:__('Apply Selections'),primary_action:async values=>{
                    await frm.set_value(values);dialog.hide();
                    frappe.show_alert({message:__('Save the project to apply these module selections.'),indicator:'blue'});
                }});
            dialog.show();
            if(!frm.perm.some(p=>p.write))dialog.get_primary_btn().hide();
        },__('Project Requests'));
    }
});
