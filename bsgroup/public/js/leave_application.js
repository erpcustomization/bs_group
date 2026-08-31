frappe.ui.form.on("Leave Application", {
    leave_type(frm) {
        toggle_medical_certificate(frm);
    },
    total_leave_days(frm) {
        toggle_medical_certificate(frm);
    },
    onload(frm) {
        toggle_medical_certificate(frm);
    },
    refresh(frm) {
        toggle_medical_certificate(frm);
    },
});

function toggle_medical_certificate(frm) {
    frappe.db.get_singles_value("BS Group Settings", "select_leave_type").then((configured_leave_type) => {
        frappe.db.get_singles_value("BS Group Settings", "attachment_required_after_days").then((threshold_days) => {
            let mandatory = (
                configured_leave_type &&
                threshold_days &&
                frm.doc.leave_type === configured_leave_type &&
                (frm.doc.total_leave_days || 0) > threshold_days
            );

            frm.toggle_reqd("custom_medical_certificate", mandatory);
        });
    });
}
