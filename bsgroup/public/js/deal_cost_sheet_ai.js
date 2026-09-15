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
// All figures come from the server (bsgroup.ai.quotation_generator); this file
// only checks readiness, collects optional guidance, routes to the draft, and
// reports approval / missing-cost / tax warnings.

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
			if (p.block_reason && !p.can_override) {
				frappe.msgprint({
					title: __("Blocked by commercial approval"),
					message: bsg_ai_esc(p.block_reason),
					indicator: "red",
				});
				return;
			}
			const missing = p.missing_costs || [];
			if (missing.length && !p.can_override) {
				const rows = missing.map(m => "<li>" + bsg_ai_esc(m.ref) + " — " + bsg_ai_esc(m.issue) + "</li>").join("");
				frappe.msgprint({
					title: __("Missing costs — fix before quoting"),
					message: "<ul>" + rows + "</ul>",
					indicator: "orange",
				});
				return;
			}
			bsg_ai_quote_dialog(frm, p);
		},
	});
}

function bsg_ai_quote_dialog(frm, preview) {
	const warnings = [];
	if (preview.block_reason) warnings.push(__("Override: ") + preview.block_reason);
	(preview.missing_costs || []).forEach(m => warnings.push(m.ref + " — " + m.issue));
	if (preview.tax_warning) warnings.push(preview.tax_warning);

	const canOverrideMissing = preview.can_override && (preview.missing_costs || []).length;

	const d = new frappe.ui.Dialog({
		title: __("AI Quotation Draft"),
		fields: [
			warnings.length
				? {
						fieldtype: "HTML",
						options:
							'<div style="background:#fff4e5;border:1px solid #ffd8a8;padding:8px 10px;border-radius:6px;margin-bottom:8px;font-size:12px">' +
							"<b>" + __("Please review:") + "</b><ul style=\"margin:4px 0 0 16px\">" +
							warnings.map(w => "<li>" + bsg_ai_esc(w) + "</li>").join("") +
							"</ul></div>",
				  }
				: { fieldtype: "HTML", options: "" },
			{ fieldtype: "Small Text", fieldname: "instructions", label: __("Extra guidance for the narrative (optional, no prices)") },
			{ fieldtype: "Check", fieldname: "overwrite_narrative", label: __("Overwrite existing subject / scope / notes"), default: 0 },
			canOverrideMissing
				? { fieldtype: "Check", fieldname: "ignore_missing_costs", label: __("Proceed despite missing costs (override)"), default: 0 }
				: { fieldtype: "HTML", options: "" },
		],
		primary_action_label: __("Generate Draft"),
		primary_action(values) {
			d.hide();
			frappe.call({
				method: "bsgroup.ai.quotation_generator.generate_quotation_from_dcs",
				args: {
					source_name: frm.doc.name,
					instructions: values.instructions || "",
					overwrite_narrative: values.overwrite_narrative ? 1 : 0,
					ignore_missing_costs: values.ignore_missing_costs ? 1 : 0,
				},
				freeze: true,
				freeze_message: __("Generating draft quotation..."),
				callback(r) {
					const res = r.message || {};
					if (!res.ok) {
						frappe.msgprint({
							title: __("Not created"),
							message: bsg_ai_esc(res.message || __("Could not generate the quotation.")),
							indicator: "red",
						});
						return;
					}
					const notes = [];
					if (res.ai_error) notes.push(__("AI note: ") + res.ai_error);
					(res.needs_input || []).forEach(n => notes.push(n));
					if (notes.length) {
						frappe.msgprint({
							title: __("Draft created — items to review"),
							message: "<ul>" + notes.map(n => "<li>" + bsg_ai_esc(n) + "</li>").join("") + "</ul>",
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
