// Copyright (c) 2026, Tridots Tech and contributors
// For license information, please see license.txt

// Auto-sum Payment Allocations into the cheque total Amount
function calc_cheque_total(frm) {
    var rows = frm.doc.payment_details || [];
    if (rows.length > 0) {
        var total = 0;
        rows.forEach(function(r){ total += flt(r.amount); });
        frm.set_value('amount', total);
        frm.set_df_property('amount', 'read_only', 1);
        frm.set_df_property('amount', 'description', 'Auto-calculated from Payment Allocations table.');
    } else {
        frm.set_df_property('amount', 'read_only', 0);
        frm.set_df_property('amount', 'description', '');
    }
    frm.refresh_field('amount');
}

frappe.ui.form.on('Cheque Payment Detail', {
    amount: function(frm) { calc_cheque_total(frm); },
    payment_details_remove: function(frm) { calc_cheque_total(frm); }
});

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
    payment_details_add: function(frm) { calc_cheque_total(frm); },
    payment_details_remove: function(frm) { calc_cheque_total(frm); },
    validate: function(frm) { calc_cheque_total(frm); },
	refresh(frm) {
        calc_cheque_total(frm);
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
