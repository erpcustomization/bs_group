frappe.ui.form.on("Task", {
   onload(frm){
        if(!frm.doc.custom_created_by){
            frm.set_value("custom_created_by", frappe.session.user)
        }
   },
   refresh(frm){
        create_timesheet(frm)
   }
})

function create_timesheet(frm) {
    frm.add_custom_button("Timesheet", () => {
        let project   = frm.doc.project;
        let task_name = frm.doc.name;

        frappe.route_hooks.after_load = function (new_frm) {
            new_frm.doc.time_logs = [];
            let row = frappe.model.add_child(new_frm.doc, "Timesheet Detail", "time_logs");
            row.custom_reference_type = "Project";
            row.custom_reference      = project;
            row.project               = project;
            row.task                  = task_name;
            new_frm.refresh_field("time_logs");
        };

        frappe.new_doc("Timesheet");
    });
}