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
    const leaveType = frm.doc.leave_type;
    frm.toggle_display(['custom_emergency_contact_name', 'custom_emergency_contact_phone'], frm.doc.custom_time_off_category === 'Emergency Leave');
    if (frm.doc.leave_type === 'Sick Leave') {
        frm.toggle_reqd('custom_medical_certificate', (frm.doc.total_leave_days || 0) > 1);
        return;
    }
    frappe.db.get_singles_value("BS Group Settings", "select_leave_type").then((configured_leave_type) => {
        frappe.db.get_singles_value("BS Group Settings", "attachment_required_after_days").then((threshold_days) => {
            if (frm.doc.leave_type !== leaveType) return;
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
