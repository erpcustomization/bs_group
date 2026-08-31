// Copyright (c) 2026, Tridots Tech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Cheque Request", {
    onload: function(frm) {
        if (!frm.doc.request_date) {
            frm.set_value("request_date", frappe.datetime.get_today());
        }
        if (!frm.doc.requested_by) {
            frappe.db.get_value("User", frappe.session.user, "full_name")
                .then(r => {
                    if (r.message) {
                        frm.set_value("requested_by", r.message.full_name);
                    }
                });
    }
    },
	refresh(frm) {
        const show_cheque_fields = [
            "Pre-Approved",
            "Prepared",
            "Pending Signature",
            "Signed",
            "Issued"
        ];

        if (show_cheque_fields.includes(frm.doc.status)) {
            frm.set_df_property("cheque_number", "hidden", 0);
            frm.set_df_property("cheque_date", "hidden", 0);
        } else {
            frm.set_df_property("cheque_number", "hidden", 1);
            frm.set_df_property("cheque_date", "hidden", 1);
        }
        // BEFORE PREPARED
        if (frm.doc.status !== "Prepared" && frm.doc.status !== "Pending Signature") {
            frm.set_df_property("signed_by", "read_only", 1);
        }
        // BEFORE SIGNED
        if (frm.doc.status !== "Signed") {
            frm.set_df_property("issued_by", "read_only", 1);
        }
        // // AFTER ISSUED → FULL LOCK
        // if (frm.doc.status === "Issued") {
        //     frm.set_read_only();
        // }
	},
});
