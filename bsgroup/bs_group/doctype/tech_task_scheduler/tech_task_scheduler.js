// Copyright (c) 2026, Tridots Tech and contributors
// For license information, please see license.txt

const CATEGORY_DOCTYPE_MAP = {
    "Presales": "Presales Request",
};

frappe.ui.form.on("Tech Task Scheduler List", {
    category(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        let target_doctype = CATEGORY_DOCTYPE_MAP[row.category] || row.category;
        frappe.model.set_value(cdt, cdn, "category_doctype", target_doctype);
        frappe.model.set_value(cdt, cdn, "category_name", "");
    },
    category_name(frm, cdt, cdn) {
        let row = locals[cdt][cdn];
        if (row.category === "HD Ticket" && row.category_name) {
            frappe.db.get_value("HD Ticket", row.category_name, "subject", function(r) {
                if (r && r.subject) {
                    frappe.model.set_value(cdt, cdn, "activity_details", r.subject);
                }
            });
        }
    },
});

frappe.ui.form.on("Tech Task Scheduler", {
    refresh(frm) {
        render_task_scheduler(frm);
        apply_category_name_filter(frm);

        frm.set_query("task", "tech_task_scheduler_list", function (doc, cdt, cdn) {
            let row = locals[cdt][cdn];
            return {
                filters: {
                    project: row.category_name
                }
            };
        });
    }
});

function render_task_scheduler(frm) {

    let html_content = `
    <div style="
      background:#F0FCFF;
      border-left:5px solid #00AFC1;
      padding:12px 14px;
      border-radius:6px;
      margin:10px 0;
    ">
      <div style="font-size:15px;font-weight:600;color:#0A1F44;">
        Tech Task Scheduler
      </div>

      <div style="font-size:12px;color:#6b7280;margin-top:3px;">
        Click “Add Row”, choose the date, then select the required category.
      </div>
    </div>
    `;

    if (frm.fields_dict.tech_task_scheduler) {
        frm.fields_dict.tech_task_scheduler.$wrapper.html(html_content);
    }
}

function apply_category_name_filter(frm) {

    frm.fields_dict.tech_task_scheduler_list.grid.get_field("category_name").get_query = function(doc, cdt, cdn) {
        let row = locals[cdt][cdn];
        if (row.category === "HD Ticket") {
            return {
                filters: {
                    status: "Open"
                }
            };
        }
        if (row.category === "Project") {
            return {
                filters: {
                    status: "Open"
                }
            };
        }
    };
}