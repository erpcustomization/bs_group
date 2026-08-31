// Copyright (c) 2026, Tridots Tech and contributors
// For license information, please see license.txt

frappe.query_reports["Tech Task Scheduler Report"] = {
    filters: [
        {
            fieldname: "date_filter",
            label: __("Date Filter"),
            fieldtype: "Select",
            options: [
                "All",
                "Today",
                "Tomorrow",
                "This Week",
                "This Month",
                "Custom"
            ],
            default: "All"
        },
        {
            fieldname: "from_date",
            label: __("From Date"),
            fieldtype: "Date",
            depends_on: 'eval:doc.date_filter=="Custom"'
        },
        {
            fieldname: "to_date",
            label: __("To Date"),
            fieldtype: "Date",
            depends_on: 'eval:doc.date_filter=="Custom"'
        },
        {
            fieldname: "category",
            label: __("Category"),
            fieldtype: "Select",
            options: ["", "Project", "HD Ticket"]
        },
        {
            fieldname: "category_name",
            label: __("Project / Ticket"),
            fieldtype: "Data"
        },
        {
            fieldname: "task",
            label: __("Task"),
            fieldtype: "Link",
            options: "Task"
        },
        {
            fieldname: "assigned_to",
            label: __("Assigned To"),
            fieldtype: "Link",
            options: "User"
        },
        {
            fieldname: "status",
            label: __("Status"),
            fieldtype: "Select",
            options: ["", "Draft", "Open", "Completed", "Cancelled"]
        }
    ]
};
