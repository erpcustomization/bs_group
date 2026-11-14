frappe.ui.form.on('BS Project Schedule Settings', {
    refresh(frm) {
        if(frappe.session.user==='mohan@bitssecureit.com') frm.add_custom_button(__('Send Private Test to Mohan'), async () => {
            const {message:r}=await frappe.call({method:'bsgroup.project_schedule.test_delivery',type:'POST',freeze:true});
            frappe.msgprint(__('First attempt: {0}. Repeated attempt: {1}. Check Power Automate run history for actual delivery.',[r.first,r.repeated]));
        });
        frm.add_custom_button(__('Test Duplicate Protection'), async () => {
            const {message:r}=await frappe.call({method:'bsgroup.project_schedule.selftest',type:'POST',freeze:true});
            if(r?.success) frappe.msgprint(__('Passed: two runs reused one scheduler and left one task row. Test changes were rolled back. No Teams messages sent.')+'<br>'+frappe.utils.escape_html(r.project));
        });
        frm.add_custom_button(__('Preview Tomorrow'), async () => {
            const {message: rows} = await frappe.call({method:'bsgroup.project_schedule.preview',freeze:true});
            const e = value => frappe.utils.escape_html(String(value || ''));
            const html = '<p>Read-only preview. No schedules or Teams messages are created.</p><div class="table-responsive"><table class="table table-bordered"><thead><tr><th>Employee</th><th>Shift</th><th>Tasks</th><th>Result</th></tr></thead><tbody>' + (rows || []).map(row=>
                `<tr><td>${e(row.employee_name)}<br>${e(row.user)}</td><td>${e(row.shift)}</td><td>${row.rows.length}</td><td>${e(row.reason || (row.rows.length ? 'Eligible' : 'No active assigned tasks with a start date'))}</td></tr>`
            ).join('') + '</tbody></table></div>';
            const dialog = new frappe.ui.Dialog({title:__('Tomorrow’s Project Schedule'),size:'extra-large',fields:[{fieldname:'preview',fieldtype:'HTML'}]});
            dialog.fields_dict.preview.$wrapper.html(html);dialog.show();
        });
    }
});
