frappe.ui.form.on("Employee", {
	refresh(frm) {
		// hrms hides this field unconditionally in its own refresh handler;
		// defer so this runs after it and restores visibility.
		setTimeout(() => frm.set_df_property("holiday_list", "hidden", 0), 0);

		if (!frm.is_new() && frm.doc.user_id) {
			frm.add_custom_button(__("Send Login Details"), () => {
				frappe.confirm(
					__("Send login/reset-password instructions to {0}?", [frm.doc.user_id]),
					() => {
						frappe.call({
							method: "bsgroup.utils.employee.send_login_details",
							args: { employee: frm.doc.name },
							freeze: true,
							freeze_message: __("Sending email..."),
							callback: (r) => {
								if (r.message) {
									frappe.msgprint(__("Email sent to {0}", [r.message]));
								}
							},
						});
					}
				);
			});
		}
	},
});
