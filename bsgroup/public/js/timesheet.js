frappe.ui.form.on("Timesheet", {
    refresh(frm) {
        frm.remove_custom_button("Start Timer");
        frm.remove_custom_button("Resume Timer");
        if (!frm.doc.user) {
            frm.set_value("user", frappe.session.user);
        }
        if (!frm.doc.custom_date) {
            frm.set_value("custom_date", frappe.datetime.get_today());
        }
        set_reference_type_filter(frm);
    }
});

frappe.ui.form.on("Timesheet Detail", {
    form_render(frm, cdt, cdn) {
        set_reference_type_filter(frm);
    },

    custom_from_times(frm, cdt, cdn) {
        calc_hours(frm, cdt, cdn);
    },

    custom_to_times(frm, cdt, cdn) {
        calc_hours(frm, cdt, cdn);
    },

    custom_reference(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        if (row.custom_reference_type === "Project") {
            row.project = row.custom_reference;
        } else {
            row.project = null;
        }
        frm.refresh_field("time_logs");
    }
});

function calc_hours(frm, cdt, cdn) {
    let row  = locals[cdt][cdn];
    let from = row.custom_from_times;
    let to   = row.custom_to_times;

    if (!from || !to) return;

    let from_secs = time_to_seconds(from);
    let to_secs   = time_to_seconds(to);
    let diff      = to_secs - from_secs;

    if (diff <= 0) {
        frappe.show_alert({ message: __("To Time must be after From Time"), indicator: "orange" });
        return;
    }

    frappe.model.set_value(cdt, cdn, "hours", flt(diff / 3600, 2));
}

function time_to_seconds(time_str) {
    let parts = (time_str || "").split(":");
    return (parseInt(parts[0]) || 0) * 3600
         + (parseInt(parts[1]) || 0) * 60
         + (parseInt(parts[2]) || 0);
}

function set_reference_type_filter(frm) {
    frm.fields_dict.time_logs.grid.get_field("custom_reference_type").get_query = function () {
        return {
            filters: {
                name: ["in", ["Project", "HD Ticket", "Presales Request"]]
            }
        };
    };
}
