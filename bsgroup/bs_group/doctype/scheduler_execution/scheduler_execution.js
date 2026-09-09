// Copyright (c) 2026, Tridots Tech and contributors
// For license information, please see license.txt

frappe.ui.form.on('Scheduler Execution', {
	refresh: function (frm) {
		if (frm.is_new()) return;
		var is_zz = String(frm.doc.activity_details || '').indexOf('ZZTEST') === 0;
		if (!is_zz) return;

		// FIX 10 / FIX 9: on ZZTEST POC records the verification path and the separate
		// Close action are not part of the workflow. Update Work is the single engineer action.
		['Start Work', 'Mark Blocked', 'Submit for Verification', 'Correct Work', 'Verify', 'Reject for Correction', 'Close Execution']
			.forEach(function (lbl) { frm.remove_custom_button(lbl); });
		['Supervisor'].forEach(function (g) { try { frm.remove_custom_button('Verify', g); frm.remove_custom_button('Reject for Correction', g); frm.remove_custom_button('Close Execution', g); } catch (e) { } });

		var ref = frm.doc.category === 'Project' ? ('Project Task ' + (frm.doc.task || '-'))
			: frm.doc.category === 'HD Ticket' ? ('Helpdesk Ticket ' + (frm.doc.ticket || '-'))
				: ('Internal Task ' + (frm.doc.internal_task || '-'));
		var cond = frm.doc.timesheet_condition ? (' | Timesheet: ' + frm.doc.timesheet_condition) : '';
		frm.set_intro('ZZTEST POC. Single closure point: ' + ref + cond, frm.doc.operational_status === 'Closed' ? 'blue' : 'orange');

		if (frm.doc.docstatus === 0 && frm.doc.operational_status !== 'Cancelled') {
			frm.add_custom_button('Update Work', function () {
				const d = new frappe.ui.Dialog({
					title: 'Update Work - ' + ref,
					size: 'large',
					fields: [
						{ fieldtype: 'Datetime', fieldname: 'actual_start', label: 'Actual Start', reqd: 1, default: frm.doc.actual_start },
						{ fieldtype: 'Datetime', fieldname: 'actual_end', label: 'Actual End', reqd: 1, default: frm.doc.actual_end },
						{ fieldtype: 'Column Break' },
						{ fieldtype: 'Select', fieldname: 'work_outcome', label: 'Result Achieved',
							options: ['', 'Fully Completed', 'Partially Completed', 'Blocked', 'No Work Possible', 'Cancelled by Operations'].join('\n'),
							default: frm.doc.work_outcome },
						{ fieldtype: 'Percent', fieldname: 'completion_percentage', label: 'Completion Percentage', default: frm.doc.completion_percentage },
						{ fieldtype: 'Section Break' },
						{ fieldtype: 'Small Text', fieldname: 'work_completed', label: 'Actual Work Performed', reqd: 1, default: frm.doc.work_completed },
						{ fieldtype: 'Small Text', fieldname: 'work_pending', label: 'Pending Work', default: frm.doc.work_pending },
						{ fieldtype: 'Section Break', label: 'Blocker' },
						{ fieldtype: 'Select', fieldname: 'blocker_category', label: 'Blocker Category',
							options: ['', 'Awaiting Customer', 'Awaiting Material', 'Awaiting Approval', 'Access Issue', 'Equipment Fault', 'Other'].join('\n'),
							default: frm.doc.blocker_category },
						{ fieldtype: 'Small Text', fieldname: 'blocker_details', label: 'Blocker Details', default: frm.doc.blocker_details },
						{ fieldtype: 'Section Break', label: 'Evidence and Labour' },
						{ fieldtype: 'Attach', fieldname: 'completion_evidence', label: 'Evidence', default: frm.doc.completion_evidence },
						{ fieldtype: 'Int', fieldname: 'additional_labour_used', label: 'Additional Labour Used', default: frm.doc.additional_labour_used },
						{ fieldtype: 'Column Break' },
						{ fieldtype: 'Check', fieldname: 'task_completed', label: 'Task completed', default: 0,
							description: 'Tick only when the defined activity on the linked Task, Ticket or Internal Task is genuinely finished.' },
						{ fieldtype: 'Small Text', fieldname: 'completion_note', label: 'Completion Note', default: frm.doc.completion_note }
					],
					primary_action_label: 'Submit Update',
					primary_action: function (values) {
						values.execution = frm.doc.name;
						frappe.call({
							method: 'zz_poc_scheduler_execution_update_work',
							args: values, freeze: true,
							freeze_message: 'Recording work, daily timesheet and operational update...',
							callback: function (r) {
								d.hide();
								const m = r.message || {};
								frappe.msgprint({
									title: 'Work Updated', indicator: 'green', message:
										'Closure point: <b>' + (m.reference_type || '-') + ' ' + (m.operational_reference || '-') + '</b><br>'
										+ 'Daily Timesheet: <b>' + (m.timesheet || '-') + '</b> (detail rows today: ' + (m.daily_timesheet_rows || 0) + ', total ' + (m.daily_total_hours || 0) + 'h)<br>'
										+ 'This update: <b>' + (m.actual_hours || 0) + ' h</b><br>'
										+ 'Execution status: <b>' + (m.operational_status || '-') + '</b><br>'
										+ 'Scheduler row status: <b>' + (m.scheduler_row_status || '-') + '</b><br>'
										+ 'Task / Ticket closed: <b>' + (m.downstream_closed ? 'Yes' : 'No') + '</b>'
								});
								frm.reload_doc();
							}
						});
					}
				});
				d.show();
			}, 'ZZTEST POC');
		}

		var is_ops = frappe.user.has_role('Operations Manager') || frappe.user.has_role('Projects Manager') || frappe.user.has_role('System Manager');
		if (!is_ops) return;

		var op_task = frm.doc.category === 'Office' ? frm.doc.internal_task : frm.doc.task;
		if (op_task) {
			frm.add_custom_button('Reopen / Return Task', function () {
				const dr = new frappe.ui.Dialog({
					title: 'Reopen or Return Task ' + op_task,
					fields: [{ fieldtype: 'Small Text', fieldname: 'zz_poc_reason', label: 'Reason (mandatory)', reqd: 1 },
						{ fieldtype: 'Data', fieldname: 'new_status', label: 'New Task Status', default: 'Implementation In Progress' },
						{ fieldtype: 'Percent', fieldname: 'progress', label: 'Restore Progress To (optional)' }],
					primary_action_label: 'Reopen',
					primary_action: function (v) {
						dr.hide(); frappe.call({
							method: 'zz_poc_task_reopen',
							args: { task: op_task, zz_poc_reason: v.zz_poc_reason, new_status: v.new_status, progress: v.progress },
							freeze: true, freeze_message: 'Reopening and reassigning...', callback: function (r) {
								const m = r.message || {}; frappe.msgprint({
									title: 'Task Reopened', indicator: 'orange', message:
										'Status: <b>' + m.previous_status + '</b> to <b>' + m.new_status + '</b><br>Progress: <b>' + m.previous_progress + '% to ' + m.restored_progress + '%</b><br>Reassigned to: <b>' + (m.reassigned_to || []).join(', ') + '</b>'
								});
								frm.reload_doc();
							}
						});
					}
				});
				dr.show();
			}, 'ZZTEST POC');
		}

		if (frm.doc.operational_status !== 'Cancelled') {
			frm.add_custom_button('Cancel / Reassign Assignment', function () {
				const dx = new frappe.ui.Dialog({
					title: 'Cancel or Reassign Assignment',
					fields: [{ fieldtype: 'Small Text', fieldname: 'zz_poc_reason', label: 'Reason (mandatory)', reqd: 1 },
						{ fieldtype: 'Link', fieldname: 'new_resource', label: 'Reassign To (leave blank to cancel only)', options: 'User' }],
					primary_action_label: 'Apply',
					primary_action: function (v) {
						dx.hide(); frappe.call({
							method: 'zz_poc_reassign_assignment',
							args: { scheduler_row: frm.doc.scheduler_row, zz_poc_reason: v.zz_poc_reason, new_resource: v.new_resource },
							freeze: true, freeze_message: 'Cancelling / reassigning...', callback: function (r) {
								const m = r.message || {}; frappe.msgprint({
									title: 'Assignment Updated', indicator: 'orange', message:
										'Old assignment <b>' + m.old_row + '</b> set to <b>Cancelled/Reassigned</b><br>Previous resource: <b>' + m.old_resource + '</b><br>New assignment: <b>' + (m.new_scheduler || 'none') + '</b> for <b>' + (m.new_resource || '-') + '</b>'
								});
								frm.reload_doc();
							}
						});
					}
				});
				dx.show();
			}, 'ZZTEST POC');
		}
	}
});

// Single source of truth for Select options: always derived from Scheduler Execution metadata.
// Do not hardcode option lists in dialogs - the server validates against DocType metadata.
function se_supervisor_select_options(fieldname) {
	var meta = frappe.get_meta('Scheduler Execution') || {};
	var df = (meta.fields || []).find(function (f) { return f.fieldname === fieldname; });
	if (!df || !df.options) {
		frappe.throw(__('Select options for {0} could not be read from Scheduler Execution metadata.', [fieldname]));
	}
	return '\n' + df.options;
}

frappe.ui.form.on("Scheduler Execution", {
	refresh: function (frm) {
		if (frm.is_new()) {
			return;
		}

		if (frm.doc.docstatus !== 0) {
			return;
		}

		var is_supervisor = frappe.user.has_role("Operations Manager") || frappe.user.has_role("System Manager");
		if (!is_supervisor) {
			return;
		}

		if (frm.doc.resource && frm.doc.resource === frappe.session.user) {
			return;
		}

		var group = "Supervisor";

		if (frm.doc.operational_status === "Awaiting Verification" && frm.doc.verification_status === "Pending Verification") {

			frm.add_custom_button("Verify", function () {
				var dv = new frappe.ui.Dialog({
					title: "Verify Execution",
					fields: [
						{
							fieldname: "productive_category",
							label: "Productive Category",
							fieldtype: "Select",
							options: se_supervisor_select_options("productive_category"),
							reqd: 1
						},
						{
							fieldname: "billable",
							label: "Billable",
							fieldtype: "Check",
							default: 0
						},
						{
							fieldname: "supervisor_comment",
							label: "Supervisor Comment (optional)",
							fieldtype: "Small Text"
						}
					],
					primary_action_label: "Verify",
					primary_action: function (values) {
						dv.hide();
						frappe.call({
							method: "scheduler_execution_verify",
							args: {
								name: frm.doc.name,
								productive_category: values.productive_category,
								billable: values.billable ? 1 : 0,
								supervisor_comment: values.supervisor_comment || ""
							},
							freeze: true,
							freeze_message: "Verifying execution...",
							callback: function (r) {
								if (r.message && r.message.success) {
									frappe.show_alert({ message: r.message.message, indicator: "green" });
									frm.reload_doc();
								}
							}
						});
					}
				});
				dv.show();
			}, group);

			frm.add_custom_button("Reject for Correction", function () {
				var dr = new frappe.ui.Dialog({
					title: "Reject for Correction",
					fields: [
						{
							fieldname: "supervisor_comment",
							label: "Reason / Correction Required",
							fieldtype: "Small Text",
							reqd: 1
						}
					],
					primary_action_label: "Reject",
					primary_action: function (values) {
						dr.hide();
						frappe.call({
							method: "scheduler_execution_reject_for_correction",
							args: {
								name: frm.doc.name,
								supervisor_comment: values.supervisor_comment
							},
							freeze: true,
							freeze_message: "Rejecting for correction...",
							callback: function (r) {
								if (r.message && r.message.success) {
									frappe.show_alert({ message: r.message.message, indicator: "orange" });
									frm.reload_doc();
								}
							}
						});
					}
				});
				dr.show();
			}, group);
		}

		if (frm.doc.operational_status === "Completed" && frm.doc.verification_status === "Verified") {
			frm.add_custom_button("Close Execution", function () {
				frappe.confirm("Close and submit this Scheduler Execution? Once submitted it cannot be edited.", function () {
					frappe.call({
						method: "scheduler_execution_close",
						args: { name: frm.doc.name },
						freeze: true,
						freeze_message: "Closing execution...",
						callback: function (r) {
							if (r.message && r.message.success) {
								frappe.show_alert({ message: r.message.message, indicator: "green" });
								frm.reload_doc();
							}
						}
					});
				});
			}, group);
		}
	}
});

// Single source of truth for Select options: always derived from Scheduler Execution metadata.
// Do not hardcode option lists in dialogs - the server validates against DocType metadata.
function se_select_options(fieldname) {
	var meta = frappe.get_meta('Scheduler Execution') || {};
	var df = (meta.fields || []).find(function (f) { return f.fieldname === fieldname; });
	if (!df || !df.options) {
		frappe.throw(__('Select options for {0} could not be read from Scheduler Execution metadata.', [fieldname]));
	}
	return '\n' + df.options;
}

frappe.ui.form.on('Scheduler Execution', {
	refresh: function (frm) {
		// NOTE: the framework already clears custom buttons in refresh_header() before
		// refresh handlers run. Do NOT call frm.clear_custom_buttons() here - doing so would
		// wipe buttons added by other Client Scripts on this DocType depending on load order.
		if (frm.is_new()) {
			return;
		}

		// The native Submit button can never succeed on a Scheduler Execution: submission
		// only happens inside the approved Close action, after supervisor verification.
		// Leaving it visible only produces a guaranteed validation error, so remove it.
		if (frm.doc.docstatus === 0 && !frm.is_dirty()) {
			frm.page.clear_primary_action();
		}

		if (frm.doc.docstatus === 1) {
			frm.set_intro(__('This Scheduler Execution is closed and read-only.'), 'blue');
			return;
		}

		if (frm.doc.docstatus === 2) {
			return;
		}

		if (frm.doc.operational_status === 'Closed') {
			frm.set_intro(__('This Scheduler Execution is closed and read-only.'), 'blue');
			return;
		}

		if (frm.doc.operational_status === 'Awaiting Verification' && frm.doc.verification_status === 'Pending Verification') {
			frm.set_intro(__('Awaiting supervisor verification.'), 'orange');
			return;
		}

		if (!frm.doc.resource) {
			return;
		}

		var is_assigned = (frappe.session.user === frm.doc.resource);
		var is_manager = frappe.user.has_role('System Manager');

		if (!is_assigned && !is_manager) {
			return;
		}

		if (frm.doc.operational_status === 'Scheduled' && frm.doc.verification_status === 'Pending Verification') {
			frm.add_custom_button(__('Start Work'), function () {
				frappe.confirm(
					__('Start work on this Scheduler Execution?'),
					function () {
						frappe.call({
							method: 'scheduler_execution_start_work',
							args: { name: frm.doc.name },
							freeze: true,
							freeze_message: __('Starting work...'),
							callback: function (r) {
								if (r.message && r.message.success) {
									frappe.show_alert({ message: r.message.message, indicator: 'green' });
									frm.reload_doc();
								}
							}
						});
					}
				);
			});
		}

		if (frm.doc.operational_status === 'In Progress') {
			frm.add_custom_button(__('Mark Blocked'), function () {
				show_mark_blocked_dialog(frm);
			});

			frm.add_custom_button(__('Submit for Verification'), function () {
				show_submit_for_verification_dialog(frm);
			});
		}

		if (frm.doc.operational_status === 'Blocked') {
			frm.add_custom_button(__('Resume Work'), function () {
				frappe.confirm(
					__('Resume work on this Scheduler Execution?'),
					function () {
						frappe.call({
							method: 'scheduler_execution_resume_work',
							args: { name: frm.doc.name },
							freeze: true,
							freeze_message: __('Resuming work...'),
							callback: function (r) {
								if (r.message && r.message.success) {
									frappe.show_alert({ message: r.message.message, indicator: 'green' });
									frm.reload_doc();
								}
							}
						});
					}
				);
			});
		}

		if (frm.doc.operational_status === 'Awaiting Verification' && frm.doc.verification_status === 'Rejected for Correction' && frm.doc.supervisor_comment) {
			frm.add_custom_button(__('Correct Work'), function () {
				var safe_comment = frappe.utils.escape_html(frm.doc.supervisor_comment);
				var message = __('This work was rejected for correction.') + '<br><br><b>' + __('Supervisor Comment:') + '</b><br>' + safe_comment + '<br><br>' + __('Reopen this execution for correction?');
				frappe.confirm(
					message,
					function () {
						frappe.call({
							method: 'scheduler_execution_correct_work',
							args: { name: frm.doc.name },
							freeze: true,
							freeze_message: __('Reopening for correction...'),
							callback: function (r) {
								if (r.message && r.message.success) {
									frappe.show_alert({ message: r.message.message, indicator: 'green' });
									frm.reload_doc();
								}
							}
						});
					}
				);
			});
		}
	}
});

function show_mark_blocked_dialog(frm) {
	var dialog = new frappe.ui.Dialog({
		title: __('Mark Blocked'),
		fields: [
			{
				fieldname: 'blocker_category',
				label: __('Blocker Category'),
				fieldtype: 'Select',
				options: se_select_options('blocker_category'),
				reqd: 1
			},
			{
				fieldname: 'blocker_details',
				label: __('Blocker Details'),
				fieldtype: 'Small Text',
				reqd: 1
			},
			{
				fieldname: 'blocker_owner',
				label: __('Blocker Owner'),
				fieldtype: 'Link',
				options: 'User'
			},
			{
				fieldname: 'follow_up_required',
				label: __('Follow-up Required'),
				fieldtype: 'Check',
				default: 0
			},
			{
				fieldname: 'follow_up_date',
				label: __('Follow-up Date'),
				fieldtype: 'Date',
				mandatory_depends_on: 'eval:doc.follow_up_required'
			}
		],
		primary_action_label: __('Mark Blocked'),
		primary_action: function (values) {
			dialog.get_primary_btn().prop('disabled', true);
			frappe.call({
				method: 'scheduler_execution_mark_blocked',
				args: {
					name: frm.doc.name,
					blocker_category: values.blocker_category,
					blocker_details: values.blocker_details,
					blocker_owner: values.blocker_owner,
					follow_up_required: values.follow_up_required,
					follow_up_date: values.follow_up_date
				},
				freeze: true,
				freeze_message: __('Marking blocked...'),
				callback: function (r) {
					if (r.message && r.message.success) {
						dialog.hide();
						frappe.show_alert({ message: r.message.message, indicator: 'green' });
						frm.reload_doc();
					} else {
						dialog.get_primary_btn().prop('disabled', false);
					}
				},
				error: function () {
					dialog.get_primary_btn().prop('disabled', false);
				}
			});
		}
	});
	dialog.show();
}

function show_submit_for_verification_dialog(frm) {
	var dialog = new frappe.ui.Dialog({
		title: __('Submit for Verification'),
		fields: [
			{
				fieldname: 'work_completed',
				label: __('Work Completed'),
				fieldtype: 'Small Text',
				reqd: 1
			},
			{
				fieldname: 'work_outcome',
				label: __('Work Outcome'),
				fieldtype: 'Select',
				options: se_select_options('work_outcome'),
				reqd: 1
			},
			{
				fieldname: 'work_pending',
				label: __('Work Pending'),
				fieldtype: 'Small Text',
				mandatory_depends_on: "eval:doc.work_outcome && !['Fully Completed','Cancelled by Operations'].includes(doc.work_outcome)"
			},
			{
				fieldname: 'completion_evidence',
				label: __('Completion Evidence'),
				fieldtype: 'Attach',
				reqd: 1
			},
			{
				fieldname: 'follow_up_required',
				label: __('Follow-up Required'),
				fieldtype: 'Check',
				default: 0
			},
			{
				fieldname: 'follow_up_date',
				label: __('Follow-up Date'),
				fieldtype: 'Date',
				mandatory_depends_on: 'eval:doc.follow_up_required'
			}
		],
		primary_action_label: __('Submit for Verification'),
		primary_action: function (values) {
			dialog.get_primary_btn().prop('disabled', true);
			frappe.call({
				method: 'scheduler_execution_submit_for_verification',
				args: {
					name: frm.doc.name,
					work_completed: values.work_completed,
					work_pending: values.work_pending,
					work_outcome: values.work_outcome,
					completion_evidence: values.completion_evidence,
					follow_up_required: values.follow_up_required,
					follow_up_date: values.follow_up_date
				},
				freeze: true,
				freeze_message: __('Submitting for verification...'),
				callback: function (r) {
					if (r.message && r.message.success) {
						dialog.hide();
						frappe.show_alert({ message: r.message.message, indicator: 'green' });
						frm.reload_doc();
					} else {
						dialog.get_primary_btn().prop('disabled', false);
					}
				},
				error: function () {
					dialog.get_primary_btn().prop('disabled', false);
				}
			});
		}
	});
	dialog.show();
}
