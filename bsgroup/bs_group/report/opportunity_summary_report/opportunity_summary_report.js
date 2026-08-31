// Copyright (c) 2026, Tridots Tech and contributors
// For license information, please see license.txt

frappe.query_reports["Opportunity Summary Report"] = {
	filters: [
		{
            fieldname: "from_date",
            label: "From Date",
            fieldtype: "Date"
        },
        {
            fieldname: "to_date",
            label: "To Date",
            fieldtype: "Date"
        },
		{
			fieldname: "account",
			label: "Account",
			fieldtype: "Data"   
		},
		{
			fieldname: "scope",
			label: "Scope",
			fieldtype: "Link",
			options: "Opportunity Type"   
		},
		{
			fieldname: "status",
			label: "Status",
			fieldtype: "Link",
			options: "Sales Stage"
		}
	],
};
