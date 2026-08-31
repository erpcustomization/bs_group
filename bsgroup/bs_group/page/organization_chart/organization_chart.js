frappe.pages['organization-chart'].on_page_load = function(wrapper) {
	var page = frappe.ui.make_app_page({
		parent: wrapper,
		title: 'Live Organization Chart',
		single_column: true
	});

	$(frappe.templates["organization_chart"]).appendTo(page.main);
}