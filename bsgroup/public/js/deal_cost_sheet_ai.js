// Copyright (c) 2026, Tridots Tech and contributors
// For license information, please see license.txt
//
// AI-assisted draft quotation button for the Deal Cost Sheet form.
//
// Loaded via hooks.doctype_js["Deal Cost Sheet"] as a SEPARATE file (not an
// edit to deal_cost_sheet.js) so this stays additive and does not conflict
// with the fix/dcs-core-release-1 rewrite of the controller. Frappe merges
// this refresh handler with the controller's own.
//
// All figures come from the server (bsgroup.ai.quotation_generator). This file
// checks readiness, and only offers an override when the user is allowed one -
// each override is an explicit, separate checkbox; there is no automatic
// bypass. It then routes to the draft and reports any warnings.

frappe.ui.form.on("Deal Cost Sheet", {
	refresh(frm) {
		if (frm.doc.docstatus === 1) {
			frm.add_custom_button(
				__("AI Quotation Draft"),
				() => bsg_ai_create_quotation(frm),
				__("Create")
			);
		}
	},
});

function bsg_ai_esc(v) {
	return frappe.utils.escape_html(v == null ? "" : String(v));
}

function bsg_ai_create_quotation(frm) {
	frappe.call({
		method: "bsgroup.ai.quotation_generator.preview_dcs_readiness",
		args: { source_name: frm.doc.name },
		freeze: true,
		freeze_message: __("Checking readiness..."),
		callback(r) {
			const p = r.message || {};

			// Status block (draft/cancelled DCS) is never overridable.
			if (p.status_block) {
				frappe.msgprint({ title: __("Cannot quote this deal cost sheet"), message: bsg_ai_esc(p.status_block), indicator: "red" });
				return;
			}

			const blocks = [];
			if (p.block_reason) blocks.push({ key: "approval", label: p.block_reason });
			(p.missing_costs || []).forEach(m => blocks.push({ key: "missing", label: m.ref + " — " + m.issue }));
			if (p.tax_block) blocks.push({ key: "tax", label: p.tax_block });

			if (blocks.length && !p.can_override) {
				const rows = blocks.map(b => "<li>" + bsg_ai_esc(b.label) + "</li>").join("");
				frappe.msgprint({
					title: __("Not ready to quote — resolve these first"),
					message: "<ul>" + rows + "</ul>",
					indicator: "orange",
				});
				return;
			}
			bsg_ai_quote_dialog(frm, p, blocks);
		},
	});
}

function bsg_ai_quote_dialog(frm, preview, blocks) {
	const hasApproval = !!preview.block_reason;
	const hasMissing = (preview.missing_costs || []).length > 0;
	const hasTax = !!preview.tax_block;
	const canOverride = !!preview.can_override;

	const fields = [];
	if (blocks.length) {
		const rows = blocks.map(b => "<li>" + bsg_ai_esc(b.label) + "</li>").join("");
		fields.push({
			fieldtype: "HTML",
			options:
				'<div style="background:#fff4e5;border:1px solid #ffd8a8;padding:8px 10px;border-radius:6px;margin-bottom:8px;font-size:12px">' +
				"<b>" + __("These normally block a quotation:") + "</b><ul style=\"margin:4px 0 0 16px\">" + rows + "</ul>" +
				(canOverride ? "<div style=\"margin-top:6px\">" + __("Tick the matching override below to proceed anyway (recorded on the quotation).") + "</div>" : "") +
				"</div>",
		});
	}
	fields.push({ fieldtype: "Small Text", fieldname: "instructions", label: __("Extra guidance for the narrative (optional, no prices)") });
	fields.push({ fieldtype: "Check", fieldname: "overwrite_narrative", label: __("Overwrite existing subject / scope / notes"), default: 0 });
	if (canOverride && hasApproval) {
		fields.push({ fieldtype: "Check", fieldname: "override_approval", label: __("Override commercial approval block"), default: 0 });
	}
	if (canOverride && hasMissing) {
		fields.push({ fieldtype: "Check", fieldname: "ignore_missing_costs", label: __("Proceed despite missing costs"), default: 0 });
	}
	if (canOverride && hasTax) {
		fields.push({ fieldtype: "Check", fieldname: "override_tax", label: __("Proceed without a resolved tax template"), default: 0 });
	}

	const d = new frappe.ui.Dialog({
		title: __("AI Quotation Draft"),
		fields: fields,
		primary_action_label: __("Generate Draft"),
		primary_action(values) {
			// Enforce that each present block has its override explicitly ticked.
			if (hasApproval && !values.override_approval) {
				frappe.msgprint({ title: __("Override required"), message: __("Tick 'Override commercial approval block' to proceed."), indicator: "orange" });
				return;
			}
			if (hasMissing && !values.ignore_missing_costs) {
				frappe.msgprint({ title: __("Override required"), message: __("Tick 'Proceed despite missing costs' to proceed."), indicator: "orange" });
				return;
			}
			if (hasTax && !values.override_tax) {
				frappe.msgprint({ title: __("Override required"), message: __("Tick 'Proceed without a resolved tax template' to proceed."), indicator: "orange" });
				return;
			}
			d.hide();
			frappe.call({
				method: "bsgroup.ai.quotation_generator.generate_quotation_from_dcs",
				args: {
					source_name: frm.doc.name,
					instructions: values.instructions || "",
					overwrite_narrative: values.overwrite_narrative ? 1 : 0,
					override_approval: values.override_approval ? 1 : 0,
					ignore_missing_costs: values.ignore_missing_costs ? 1 : 0,
					override_tax: values.override_tax ? 1 : 0,
				},
				freeze: true,
				freeze_message: __("Generating draft quotation..."),
				callback(r) {
					const res = r.message || {};
					if (!res.ok) {
						frappe.msgprint({ title: __("Not created"), message: bsg_ai_esc(res.message || __("Could not generate the quotation.")), indicator: "red" });
						return;
					}
					const notes = [];
					if (res.ai_error) notes.push(__("AI note: ") + res.ai_error);
					(res.warnings || []).forEach(w => notes.push(w));
					(res.needs_input || []).forEach(n => notes.push(n));
					if (notes.length) {
						const uniq = Array.from(new Set(notes));
						frappe.msgprint({
							title: __("Draft created — items to review"),
							message: "<ul>" + uniq.map(n => "<li>" + bsg_ai_esc(n) + "</li>").join("") + "</ul>",
							indicator: "orange",
						});
					} else {
						frappe.show_alert({ message: __("Draft quotation created"), indicator: "green" });
					}
					frappe.set_route("Form", "Quotation", res.quotation);
				},
			});
		},
	});
	d.show();
}
