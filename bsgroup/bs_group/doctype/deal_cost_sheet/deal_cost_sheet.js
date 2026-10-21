// Copyright (c) 2026, Tridots Tech and contributors
// For license information, please see license.txt

frappe.ui.form.on("Deal Cost Sheet", {
	onload(frm) {
		// set_presales_filter(frm)
		// Cancelling a DCS should not cascade-cancel the Presales Request
		// (or any other linked submittable doc) it references.
		frm.ignore_doctypes_on_cancel_all = ["Presales Request"];
	},
	refresh(frm) {
		recalc_parent(frm);
		render_solution_matrix(frm);
		render_summary_with_currency(frm);
		reduce_subject_height(frm);
		render_site_visit_evidence(frm);

		if (frm.doc.docstatus == 1) {
			frm.add_custom_button("Create Quotation", () => {
				create_quotation(frm);
			}, __("More actions"));
		}

		if (frm.doc.version_no) {
			frm.set_intro(
				'<b>Version ' + frm.doc.version_no + '</b>' +
				(frm.doc.last_revised_by ? ' &nbsp;|&nbsp; Last revised by: <b>' + frm.doc.last_revised_by + '</b>' : '') +
				(frm.doc.last_revised_on ? ' on <b>' + frappe.datetime.str_to_user(frm.doc.last_revised_on) + '</b>' : ''),
				'blue'
			);
		}

		if (frm.doc.version_history) {
			try {
				var history = JSON.parse(frm.doc.version_history);
				if (history && history.length > 0) {
					var rows = history.map(function(v) {
						return '<tr>' +
							'<td style="padding:4px 8px;border:1px solid #e0e0e0;"><b>v' + v.version + '</b></td>' +
							'<td style="padding:4px 8px;border:1px solid #e0e0e0;">' + (v.revised_by || '-') + '</td>' +
							'<td style="padding:4px 8px;border:1px solid #e0e0e0;">' + (v.revised_on ? v.revised_on.substring(0,16) : '-') + '</td>' +
							'<td style="padding:4px 8px;border:1px solid #e0e0e0;text-align:right;">' + dcs_money(frm, v.total_cost || 0) + '</td>' +
							'<td style="padding:4px 8px;border:1px solid #e0e0e0;text-align:right;">' + dcs_money(frm, v.total_selling || 0) + '</td>' +
						'</tr>';
					}).join('');

					var html = '<div style="margin:10px 0;">' +
						'<b>Version History</b>' +
						'<table style="width:100%;border-collapse:collapse;margin-top:6px;font-size:12px;">' +
						'<thead><tr style="background:#f5f5f5;">' +
						'<th style="padding:4px 8px;border:1px solid #e0e0e0;text-align:left;">Ver</th>' +
						'<th style="padding:4px 8px;border:1px solid #e0e0e0;text-align:left;">Revised By</th>' +
						'<th style="padding:4px 8px;border:1px solid #e0e0e0;text-align:left;">Date</th>' +
						'<th style="padding:4px 8px;border:1px solid #e0e0e0;text-align:right;">Cost</th>' +
						'<th style="padding:4px 8px;border:1px solid #e0e0e0;text-align:right;">Selling</th>' +
						'</tr></thead><tbody>' + rows + '</tbody></table></div>';

					frm.set_df_property('version_history', 'description', html);
				}
			} catch(e) {}
		}
	},
	apply_exclude_to_all_items(frm){
		exclude_all_items(frm)
	},
	presales_request(frm){
		fetch_customer(frm)
	},
	site_visit(frm){
		render_site_visit_evidence(frm);
	},
	opportunity(frm){
		// set_presales_filter(frm);
        fetch_presales(frm);
	},
	company(frm) {
		render_summary_with_currency(frm);
	},
	get_data(frm){
		fetch_document_data(frm)
	},
	document_upload(frm) {
		if (!frm.doc.document_upload) {
			frm.clear_table("items");
			frm.refresh_field("items");
			recalc_parent(frm);
		}
	},
	load_responsibilities: function(frm) {
        load_responsibilities(frm);
    }
});

function reduce_subject_height(frm){
    setTimeout(() => {
        frm.fields_dict.subject.$wrapper
            .find('textarea')
            .css({
                "height": "30px",
                "min-height": "27px"
            });
    }, 300);
}

frappe.listview_settings["Deal Cost Sheet"] = {
	onload: function(listview) {
		listview.filter_area.add([
			["Deal Cost Sheet", "docstatus", "!=", "2"]
		]);
	}
};

frappe.ui.form.on("Deal Cost Item", {
	item_code(frm, cdt, cdn) {
		let row = locals[cdt][cdn];
		if (frm.doc.currency) {
			frappe.model.set_value(cdt, cdn, "currency", frm.doc.currency);
		}
		const categoryReady = set_item_category(frm, cdt, cdn).then(() => {
			recalc_item(frm, cdt, cdn);
		});
		if (row.item_code) {
			frappe.db.get_value("Item", row.item_code, ["item_name", "brand"]).then(r => {
				if (r && r.message) {
					frappe.model.set_value(cdt, cdn, "item_name", r.message.item_name);
					if (!row.brand) {
						frappe.model.set_value(cdt, cdn, "brand", r.message.brand);
					}
				}
				set_customer_item(frm, cdt, cdn);
			});
		}
        return categoryReady;
	},
	brand: function(frm, cdt, cdn) {
        set_customer_item(frm, cdt, cdn);
    },
    item_name: function(frm, cdt, cdn) {
        set_customer_item(frm, cdt, cdn);
    },
	exclude_item_name_and_brand: function(frm, cdt, cdn){
		set_customer_item(frm, cdt, cdn);
	},
	qty(frm, cdt, cdn) {
		recalc_item(frm, cdt, cdn);
	},
	cost_rate(frm, cdt, cdn) {
		recalc_item(frm, cdt, cdn);
	},
	selling_rate(frm, cdt, cdn) {
		recalc_item(frm, cdt, cdn);
	},
	items_remove(frm) {
		recalc_parent(frm);
	}
});

frappe.ui.form.on("Additional Charges Item", {
	selling_amount(frm) {
		recalc_parent(frm);
	},
	amount(frm, cdt, cdn) {
		recalc_parent(frm);
	},
	addtional_charges_remove(frm) {
		recalc_parent(frm);
	}
});

frappe.ui.form.on("Deal Cost Resource", {
	resource_type(frm, cdt, cdn) {
		recalc_parent(frm);
	},
	cost_rate(frm, cdt, cdn) {
		if (frm.doc.currency) {
			frappe.model.set_value(cdt, cdn, "currency", frm.doc.currency);
		}
		recalc_resource(frm, cdt, cdn);
	},
	no_of_persons(frm, cdt, cdn) {
		recalc_resource(frm, cdt, cdn);
	},
	no_of_days(frm, cdt, cdn) {
		recalc_resource(frm, cdt, cdn);
	},
	hours(frm, cdt, cdn) {
		recalc_resource(frm, cdt, cdn);
	},
	cost_rate(frm, cdt, cdn) {
		recalc_resource(frm, cdt, cdn);
	},
	resources_remove(frm) {
		recalc_parent(frm);
		render_summary_with_currency(frm);
	}
});

// ── Summary Tables ────────────────────────────────────────────────────────────

function render_summary_with_currency(frm) {
	if (frm.doc.company) {
		const selected_company = frm.doc.company;
        frappe.db.get_value("Company", selected_company, "default_currency").then(r => {
            if (frm.doc.company !== selected_company) return;
			const currency = (r.message && r.message.default_currency) || frm.doc.currency;
            if (!currency) return;
			frm.doc.currency = currency;
			propagate_currency(frm, currency);
			render_summary(frm, currency);
		});
	} else {
		render_summary(frm, frm.doc.currency || "AED");
	}
}

function propagate_currency(frm, currency) {
    const decimals = currency === "OMR" ? 3 : 2;
    if (frm.__dcs_currency_decimals !== decimals) {
        frm.__dcs_currency_decimals = decimals;
        Object.keys(frm.fields_dict).forEach(function(name) {
            const control = frm.fields_dict[name];
            if (control.df.fieldtype === "Currency") frm.set_df_property(name, "precision", decimals);
            if (control.grid) {
                (control.grid.docfields || []).filter(df => df.fieldtype === "Currency").forEach(function(df) {
                    control.grid.update_docfield_property(df.fieldname, "precision", decimals);
                });
            }
        });
    }
	(frm.doc.items || []).forEach(row => {
		frappe.model.set_value(row.doctype, row.name, "currency", currency);
	});
	(frm.doc.resources || []).forEach(row => {
		frappe.model.set_value(row.doctype, row.name, "currency", currency);
	});
	frm.refresh_field("items");
	frm.refresh_field("resources");
}

function render_summary(frm, currency) {
	currency = currency || "AED";
	const doc = frm.doc;
	const $wrapper = $(frm.fields_dict["commercial_summary_html"].wrapper);

	const fmt = (val) => format_currency(flt(val), currency, currency === "OMR" ? 3 : 2);
	const pct = (val) => flt(val, 2).toFixed(2) + "%";

	const can_see_selling=frappe.user.has_role(["Sales Manager","Sales User","Presales","Commercial Controller","Managing Director","System Manager"]);

	const prod_cost       = flt(doc.products_cost_total);
	const prod_sell       = flt(doc.products_selling_total);
	const prod_margin     = prod_sell - prod_cost;
	const prod_margin_pct = prod_sell ? (prod_margin / prod_sell) * 100 : 0;

	const svc_cost        = flt(doc.services_cost_total);
	const svc_sell        = flt(doc.services_selling_total);
	const svc_margin      = svc_sell - svc_cost;
	const svc_margin_pct  = svc_sell ? (svc_margin / svc_sell) * 100 : 0;

	let charges_total=0, charges_selling=0;
	(doc.addtional_charges || []).forEach(row => {
		charges_total += flt(row.amount);
        charges_selling += flt(row.selling_amount);
	});

	let resource_cost_total = 0;
	(doc.resources || []).forEach(row => {
		resource_cost_total += flt(row.cost_amount);
	});

	const total_cost_calc    = flt(doc.total_cost);
	const total_selling_calc = flt(doc.total_selling);
	const total_margin_calc  = flt(doc.margin_value);
        const total_margin_pct   = flt(doc.margin_percent);

	const th = (label, align = "right") =>
		`<th style="text-align:${align}; padding:8px 12px; background:#f0f4f8; font-weight:600; font-size:12px; color:#4a5568;">${label}</th>`;

	const td = (val, bold = false) =>
		`<td style="text-align:right; padding:7px 12px; ${bold ? "font-weight:700;" : ""}">${val}</td>`;

	const td_label = (val, bold = false) =>
		`<td style="padding:7px 12px; ${bold ? "font-weight:700;" : ""}">${val}</td>`;

	// ── Commercial Summary ──
	const commercial_html = `
		<div style="margin-bottom:24px;">
			<div style="font-size:14px; font-weight:700; color:#2d3748; margin-bottom:10px; padding-bottom:6px; border-bottom:2px solid #5b7fdb;">
				BOQ breakdown — saved rows
			</div>
            <div class="text-muted small" style="margin-bottom:8px">These figures describe the saved BOQ. The Overview shows the current negotiated and awarded positions.</div>
			<table style="width:100%; border-collapse:collapse; font-size:13px; border:1px solid #e2e8f0;">
				<thead>
					<tr>
						${th("Category", "left")}
						${th(`Cost (${currency})`)}
						${can_see_selling ? th(`Selling (${currency})`) : ""}
						${can_see_selling ? th(`Margin (${currency})`) : ""}
						${can_see_selling ? th("Margin %") : ""}
					</tr>
				</thead>
				<tbody>
					<tr style="border-bottom:1px solid #e2e8f0;">
						${td_label("Products")}
						${td(fmt(prod_cost))}
						${can_see_selling ? td(fmt(prod_sell)) : ""}
						${can_see_selling ? td(fmt(prod_margin)) : ""}
						${can_see_selling ? td(prod_sell > 0 ? pct(prod_margin_pct) : "Not priced") : ""}
					</tr>
					<tr style="border-bottom:1px solid #e2e8f0;">
						${td_label("Services")}
						${td(fmt(svc_cost))}
						${can_see_selling ? td(fmt(svc_sell)) : ""}
						${can_see_selling ? td(fmt(svc_margin)) : ""}
						${can_see_selling ? td(svc_sell > 0 ? pct(svc_margin_pct) : "Not priced") : ""}
					</tr>
					<tr style="border-bottom:1px solid #e2e8f0;">
						${td_label("Additional Charges")}
						${td(fmt(charges_total))}
						${can_see_selling ? td(fmt(charges_selling)) : ""}
						${can_see_selling ? td(fmt(charges_selling-charges_total)) : ""}
						${can_see_selling ? td(charges_selling > 0 ? pct(100*(charges_selling-charges_total)/charges_selling) : "Not priced") : ""}
					</tr>
					<tr style="border-bottom:1px solid #e2e8f0;">
						${td_label("Resources")}
						${td(fmt(resource_cost_total))}
						${can_see_selling ? td("-") : ""}
						${can_see_selling ? td("-") : ""}
						${can_see_selling ? td("-") : ""}
					</tr>
					<tr style="background:#f7f9fc; border-top:2px solid #cbd5e0;">
						${td_label("Total", true)}
						${td(fmt(total_cost_calc), true)}
						${can_see_selling ? td(fmt(total_selling_calc), true) : ""}
						${can_see_selling ? td(fmt(total_margin_calc), true) : ""}
						${can_see_selling ? td(total_selling_calc > 0 ? pct(total_margin_pct) : "Not priced", true) : ""}
					</tr>
				</tbody>
			</table>
		</div>
	`;

	// ── Resource Summary ──
	let resource_rows = "";
	(doc.resources || []).forEach(r => {
		resource_rows += `
			<tr style="border-bottom:1px solid #e2e8f0;">
				${td_label(r.resource_type || "")}
				${td(flt(r.no_of_persons))}
				${td(flt(r.no_of_days))}
				${td(fmt(r.cost_rate))}
				${td(fmt(r.cost_amount))}
			</tr>
		`;
	});

	if (!resource_rows) {
		resource_rows = `<tr><td colspan="5" style="text-align:center; padding:10px; color:#a0aec0; font-size:12px;">No resources added</td></tr>`;
	} else {
		resource_rows += `
			<tr style="background:#f7f9fc; border-top:2px solid #cbd5e0;">
				${td_label("Total", true)}
				${td("")}
				${td("")}
				${td("")}
				${td(fmt(resource_cost_total), true)}
			</tr>
		`;
	}

	const resource_html = `
		<div style="margin-bottom:24px;">
			<div style="font-size:14px; font-weight:700; color:#2d3748; margin-bottom:10px; padding-bottom:6px; border-bottom:2px solid #5b7fdb;">
				Resource Summary
			</div>
			<table style="width:100%; border-collapse:collapse; font-size:13px; border:1px solid #e2e8f0;">
				<thead>
					<tr>
						${th("Resource Type", "left")}
						${th("No. of Persons")}
						${th("No. of Days")}
						${th(`Cost Rate (${currency})`)}
						${th(`Cost Amount (${currency})`)}
					</tr>
				</thead>
				<tbody>
					${resource_rows}
				</tbody>
			</table>
		</div>
	`;

	$wrapper.html(resource_html + commercial_html);
}

// ── Calculations ──────────────────────────────────────────────────────────────

async function set_item_category(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	if (!row.item_code) return;
    const selectedItem = row.item_code;

	const r = await frappe.call({method:"bsgroup.dcs.item_category.get_item_category",args:{item_code:selectedItem}});
    if (row.item_code !== selectedItem) return;
	const category = r.message;
	await frappe.model.set_value(cdt, cdn, "item_category", category);
}

function recalc_item(frm, cdt, cdn) {
	const row = locals[cdt][cdn];

	const qty = flt(row.qty);
	const cost_rate = flt(row.cost_rate);
	const selling_rate = flt(row.selling_rate);

	const cost_amount = qty * cost_rate;
	const selling_amount = qty * selling_rate;
	const gp_value = selling_amount - cost_amount;
	const gp_percent = selling_amount ? (gp_value / selling_amount) * 100 : 0;

	frappe.model.set_value(cdt, cdn, "cost_amount", cost_amount);
	frappe.model.set_value(cdt, cdn, "selling_amount", selling_amount);
	frappe.model.set_value(cdt, cdn, "gp_value", gp_value);
	frappe.model.set_value(cdt, cdn, "gp_percent", gp_percent);

	recalc_parent(frm);
}

function recalc_resource(frm, cdt, cdn) {
	const row = locals[cdt][cdn];

	const persons = flt(row.no_of_persons);
	const days = flt(row.no_of_days);
	const hours = flt(row.hours);
	const rate = flt(row.cost_rate);

	let cost_amount = 0;
	if (persons > 0 && days > 0) {
		cost_amount = persons * days * rate;
	} else if (hours > 0) {
		cost_amount = hours * rate;
	}

	frappe.model.set_value(cdt, cdn, "cost_amount", cost_amount);
	recalc_parent(frm);
}

function recalc_parent(frm) {
	if (frm.doc.docstatus === 1) {
		render_summary_with_currency(frm);
		return;
	}

	let products_cost_total = 0;
	let products_selling_total = 0;
	let services_cost_total = 0;
	let services_selling_total = 0;

	(frm.doc.items || []).forEach((row) => {
		const category = row.item_category || "Products";
		if (category === "Professional Services") {
			services_cost_total += flt(row.cost_amount);
			services_selling_total += flt(row.selling_amount);
		} else {
			products_cost_total += flt(row.cost_amount);
			products_selling_total += flt(row.selling_amount);
		}
	});

	let additional_charges_total = 0;
	(frm.doc.addtional_charges || []).forEach((row) => {
		additional_charges_total += flt(row.amount);
	});

	let total_resource_cost = 0;
	(frm.doc.resources || []).forEach((row) => {
		total_resource_cost += flt(row.cost_amount);
	});

	const total_cost = products_cost_total + services_cost_total + additional_charges_total + total_resource_cost;
	const total_selling = products_selling_total + services_selling_total +
		(frm.doc.addtional_charges || []).reduce((sum, row) => sum + flt(row.selling_amount), 0);
	const margin_value = total_selling - total_cost;
	const margin_percent = total_selling ? (margin_value / total_selling) * 100 : 0;

	frm.doc.products_cost_total    = products_cost_total;
	frm.doc.products_selling_total = products_selling_total;
	frm.doc.services_cost_total    = services_cost_total;
	frm.doc.services_selling_total = services_selling_total;
	frm.doc.total_resource_cost    = total_resource_cost;
	frm.doc.total_cost             = total_cost;
	frm.doc.total_selling          = total_selling;
	frm.doc.margin_value           = margin_value;
	frm.doc.margin_percent         = margin_percent;

	frm.refresh_fields([
		"products_cost_total", "products_selling_total",
		"services_cost_total", "services_selling_total",
		"total_resource_cost", "total_cost", "total_selling", "margin_value", "margin_percent"
	]);

	render_summary_with_currency(frm);
}

function create_quotation(frm) {
	frappe.call({
		method: "bsgroup.bs_group.doctype.deal_cost_sheet.deal_cost_sheet.make_quotation",
		args: { source_name: frm.doc.name },
		freeze: true,
		callback(r) {
			if (r.message) {
				frappe.set_route("Form", "Quotation", r.message);
			}
		}
	});
}

function set_customer_item(frm, cdt, cdn) {
	let row = locals[cdt][cdn];

	let value;
	if (row.exclude_item_name_and_brand) {
		value = `${row.item_name || ""}`.trim();
	} else {
		const parts = [row.brand, row.item_code, row.item_name].filter(p => p);
		value = parts.join(" - ");
	}

	frappe.model.set_value(cdt, cdn, "customer_item_name", value);
	frappe.model.set_value(cdt, cdn, "description", value);
}

function exclude_all_items(frm) {
	const value = frm.doc.apply_exclude_to_all_items ? 1 : 0;
	(frm.doc.items || []).forEach(row => {
		frappe.model.set_value(row.doctype, row.name, "exclude_item_name_and_brand", value);
		set_customer_item(frm, row.doctype, row.name);
	});
	
	frm.refresh_field("items");
}

function render_site_visit_evidence(frm) {
	const $wrapper = frm.fields_dict.site_visit_evidence_html
		? $(frm.fields_dict.site_visit_evidence_html.wrapper)
		: null;
	if (!$wrapper) return;

	if (!frm.doc.site_visit) {
		$wrapper.html("");
		return;
	}

	frappe.call({
		method: "bsgroup.bs_group.doctype.deal_cost_sheet.deal_cost_sheet.get_site_visit_evidence",
		args: { site_visit: frm.doc.site_visit },
		callback(r) {
			const data = r.message || {};
			$wrapper.html(build_site_visit_html(frm.doc.site_visit, data));
		}
	});
}

function build_site_visit_html(site_visit, data) {
	const row = (label, value) => value
		? `<tr><td style="padding:4px 8px;border:1px solid #e0e0e0;font-weight:600;width:200px;">${label}</td><td style="padding:4px 8px;border:1px solid #e0e0e0;">${frappe.utils.escape_html(value)}</td></tr>`
		: "";

	const measurement_rows = (data.measurements || []).map(m =>
		`<tr><td style="padding:4px 8px;border:1px solid #e0e0e0;">${frappe.utils.escape_html(m.measurement_type || "")}</td>
		<td style="padding:4px 8px;border:1px solid #e0e0e0;text-align:right;">${frappe.utils.escape_html(String(m.value ?? ""))}</td>
		<td style="padding:4px 8px;border:1px solid #e0e0e0;">${frappe.utils.escape_html(m.unit || "")}</td>
		<td style="padding:4px 8px;border:1px solid #e0e0e0;">${frappe.utils.escape_html(m.remarks || "")}</td></tr>`
	).join("");

	const evidence_links = (data.evidence || []).map(e =>
		`<li><a href="${e.attachment}" target="_blank">${frappe.utils.escape_html(e.evidence_type || "Attachment")}</a>${e.description ? " - " + frappe.utils.escape_html(e.description) : ""}</li>`
	).join("");

	return `
		<div style="margin:6px 0;">
			<a href="/app/site-visit/${site_visit}" target="_blank"><b>${site_visit}</b></a>
			&nbsp;<span class="indicator-pill ${data.status === "Completed" ? "green" : "orange"}">${data.status || ""}</span>
			<table style="width:100%;border-collapse:collapse;margin-top:8px;font-size:12px;">
				${row("Findings", data.findings)}
				${row("Recommendations", data.recommendations)}
				${row("Visit Result", data.visit_result)}
				${row("Technical Observations", data.technical_observations)}
				${row("Requirements Identified", data.requirements_identified)}
				${row("Constraints / Issues", data.constraints_issues)}
			</table>
			${measurement_rows ? `
				<div style="margin-top:10px;font-weight:600;">Measurements</div>
				<table style="width:100%;border-collapse:collapse;margin-top:4px;font-size:12px;">
					<thead><tr>
						<th style="padding:4px 8px;border:1px solid #e0e0e0;text-align:left;">Type</th>
						<th style="padding:4px 8px;border:1px solid #e0e0e0;text-align:right;">Value</th>
						<th style="padding:4px 8px;border:1px solid #e0e0e0;text-align:left;">Unit</th>
						<th style="padding:4px 8px;border:1px solid #e0e0e0;text-align:left;">Remarks</th>
					</tr></thead>
					<tbody>${measurement_rows}</tbody>
				</table>` : ""}
			${evidence_links ? `<div style="margin-top:10px;font-weight:600;">Evidence</div><ul>${evidence_links}</ul>` : ""}
		</div>
	`;
}

function fetch_customer(frm) {
    if (frm.doc.presales_request) {
        frappe.db.get_value("Presales Request", frm.doc.presales_request, "customer")
            .then(r => {
                if (r.message && r.message.customer) {
                    frm.set_value("customer", r.message.customer);
                }
            });
    }
}

// function set_presales_filter(frm) {
//     frm.set_query("presales_request", function() {
//         return {
//             filters: {
//                 opportunity: frm.doc.opportunity,
//                 // docstatus: 1
//             }
//         };
//     });
// }

function fetch_presales(frm) {
    if (!frm.doc.opportunity) return;

    frappe.db.get_value(
        "Presales Request",
        {
            opportunity: frm.doc.opportunity,
            docstatus: 1
        },
        "name"
    ).then(r => {
        if (r.message && r.message.name) {
            frm.set_value("presales_request", r.message.name);
        } else {
            frappe.db.get_value(
                "Opportunity",
                frm.doc.opportunity,
                "custom_organization_name"
            ).then(res => {
                if (res.message && res.message.custom_organization_name) {
                    dcs_fetch_party_details(frm);
                }
            });
        }
    });
}


function fetch_document_data(frm){
	frappe.call({
		method: "bsgroup.bs_group.doctype.deal_cost_sheet.deal_cost_sheet.read_deal_cost_sheet",
		args: {
			file_url: frm.doc.document_upload,
			docname: frm.doc.name
		},
		callback: function(r) {
			frm.reload_doc();
		}
	});
}

function render_solution_matrix(frm) {

    let html_content = `
    <div style="
      background:#F0FCFF;
      border-left:5px solid #00AFC1;
      padding:12px 14px;
      border-radius:6px;
      margin:10px 0;
    ">
      <div style="font-size:15px;font-weight:600;color:#0A1F44;">
        Solution Responsibility Matrix
      </div>
      <div style="font-size:12px;color:#6b7280;margin-top:3px;">
        Click “Add Row”, select the required solutions, and then click “Load Responsibilities”.
      </div>
    </div>
    `;

    if (frm.fields_dict.solution_responsibility_matrix) {
        frm.fields_dict.solution_responsibility_matrix.$wrapper.html(html_content);
    }
}

async function load_responsibilities(frm) {

    if (!frm.doc.solutions || frm.doc.solutions.length === 0) {
        frappe.msgprint('Please select at least one Solution');
        return;
    }
    frm.clear_table('responsibilities');
    for (let s of frm.doc.solutions) {
        if (!s.solution) continue;
        try {
            let template = await frappe.db.get_doc(
                'Solution Responsibility Template',
                s.solution
            );
            if (!template) continue;
            let header = frm.add_child('responsibilities');
            header.activity = `--- ${s.solution} ---`;

            if (template.responsibilities && template.responsibilities.length > 0) {
                template.responsibilities.forEach(row => {
                    let child = frm.add_child('responsibilities');
                    child.activity = row.activity || "";
                    child.bits = row.bits || 0;
                    child.customer = row.customer || 0;
                });

            } else {
                frappe.msgprint(`No responsibilities found in template: ${s.solution}`);
            }

        } catch (e) {
            console.error(e);
            frappe.msgprint(`Error loading template: ${s.solution}`);
        }
    }

    frm.refresh_field('responsibilities');
    frappe.msgprint('Responsibilities Loaded');
}
// ═══════════════════════════════════════════════════════════════════════
// Merged from DCS File 2.txt
// ═══════════════════════════════════════════════════════════════════════

frappe.ui.form.on('Deal Cost Sheet', {
    custom_load_responsibilities: async function(frm) {

        if (!frm.doc.custom_solutions || frm.doc.custom_solutions.length === 0) {
            frappe.msgprint('Please select at least one Solution');
            return;
        }

        frm.clear_table('custom_responsibilities');

        for (let s of frm.doc.custom_solutions) {

            if (!s.solution) continue;

            try {
                let template = await frappe.db.get_doc(
                    'Solution Responsibility Template',
                    s.solution
                );

                if (!template) continue;

                // Add header
                let header = frm.add_child('custom_responsibilities');
                header.activity = `--- ${s.solution} ---`;

                if (template.responsibilities && template.responsibilities.length > 0) {

                    template.responsibilities.forEach(row => {
                        let child = frm.add_child('custom_responsibilities');
                        child.activity = row.activity || "";
                        child.bits = row.bits || 0;
                        child.customer = row.customer || 0;
                    });

                } else {
                    frappe.msgprint(`No responsibilities found in template: ${s.solution}`);
                }

            } catch (e) {
                console.error(e);
                frappe.msgprint(`Error loading template: ${s.solution}`);
            }
        }

        frm.refresh_field('custom_responsibilities');
        frappe.msgprint('Responsibilities Loaded');
    }
});


// ═══════════════════════════════════════════════════════════════════════
// DEAL COST SHEET — AI ASSISTANT
// Features: Company Validation, Price DB, Market Price Check,
//           Previous Proposal Comparison, Currency Conversion Check
// ═══════════════════════════════════════════════════════════════════════

// ── Price Database: Admin can update these values ──────────────────────
const AI_PRICE_DB = {
    // Format: 'item_code (lowercase)': { cost, sell, currency, notes }
    '3cx 24sc professional license': { cost: 2821, sell: 3425, currency: 'AED', notes: '3CX Annual License' },
    '3cx appliance':                  { cost: 500,  sell: 650,  currency: 'AED', notes: '3CX Hardware Appliance' },
    // ── ADD MORE PRODUCTS BELOW ──
    // 'fortinet fortigate 60f':    { cost: 1800, sell: 2400, currency: 'AED', notes: 'Firewall' },
    // 'cisco catalyst 9200l':      { cost: 3200, sell: 4200, currency: 'AED', notes: 'Switch' },
    // 'hikvision 4mp ip camera':   { cost: 120,  sell: 200,  currency: 'AED', notes: 'Surveillance' },
};

// ── Exchange rate: 1 AED = X OMR ──────────────────────────────────────
// Cross-currency reference prices are withheld until a dated rate is explicitly supplied.

// ══════════════════════════════════════════════════════════════════════
// FORM EVENTS
// ══════════════════════════════════════════════════════════════════════
frappe.ui.form.on('Deal Cost Sheet', {

    refresh(frm) {
        // Auto-validate company/currency on load
        dcs_ai_check_company_currency(frm);

        // Cancelled sheets are commercially dead - suppress all mutating actions
        if (frm.doc.docstatus === 2) { return; }

        // Add AI Assistant button group
        frm.add_custom_button(__('🔍 Run Full AI Check'), () => {
            dcs_ai_run_full_check(frm);
        }, __('More actions'));

        frm.add_custom_button(__('💰 Price Suggestions'), () => {
            dcs_ai_price_suggestions(frm);
        }, __('More actions'));

        frm.add_custom_button(__('📊 Compare Proposals'), () => {
            dcs_ai_compare_proposals(frm);
        }, __('More actions'));

        if (frm.doc.docstatus === 0) frm.add_custom_button(__('Quick add item master'), () => { dcs_quick_add_item(frm); }, __('More actions'));

    },

    company(frm) {
        dcs_ai_check_company_currency(frm);
    }

});

// ══════════════════════════════════════════════════════════════════════
// FUNCTION 1: Company/Currency Mismatch Detection
// ══════════════════════════════════════════════════════════════════════
function dcs_ai_check_company_currency(frm) {
    const company  = (frm.doc.company  || '').toUpperCase();
    const currency = (frm.doc.currency || '').toUpperCase();

    if (company.includes('-AE') && currency === 'OMR') {
        frm.dashboard.set_headline_alert(
            '⚠️ <b>AI Warning:</b> UAE company (-AE) selected but currency is OMR. Should this be AED?',
            'orange'
        );
    } else if (company.includes('-OM') && currency === 'AED') {
        frm.dashboard.set_headline_alert(
            '⚠️ <b>AI Warning:</b> Oman company (-OM) selected but currency is AED. Should this be OMR?',
            'orange'
        );
    } else if (company.includes('-AE') && currency === 'AED') {
        frm.dashboard.clear_headline();
    } else if (company.includes('-OM') && currency === 'OMR') {
        frm.dashboard.clear_headline();
    }
}

// ══════════════════════════════════════════════════════════════════════
// FUNCTION 2: Full AI Validation Report
// ══════════════════════════════════════════════════════════════════════
function dcs_ai_run_full_check(frm) {
    let issues   = [];
    let warnings = [];
    let passed   = [];

    const company  = frm.doc.company  || '';
    const currency = (frm.doc.currency || 'AED').toUpperCase();
    const isAE     = company.toUpperCase().includes('-AE');
    const isOM     = company.toUpperCase().includes('-OM');
    const isAED    = currency === 'AED';
    const isOMR    = currency === 'OMR';
    const fxRate   = 1.0;

    // ── Check 1: Company/Currency Match ───────────────────────────────
    if (isAE && isOMR)
        issues.push('Company is UAE (<b>-AE</b>) but currency is <b>OMR</b>. Expected: AED');
    else if (isOM && isAED)
        issues.push('Company is Oman (<b>-OM</b>) but currency is <b>AED</b>. Expected: OMR');
    else if (!isAE && !isOM)
        warnings.push('Company name has no <b>-AE</b> or <b>-OM</b> suffix — cannot validate region automatically');
    else if (isAE && isAED)
        passed.push('Company UAE ↔ Currency AED ✓');
    else if (isOM && isOMR)
        passed.push('Company Oman ↔ Currency OMR ✓');

    // ── Check 2: Item Price Validation ────────────────────────────────
    const items = frm.doc.items || [];
    if (!items.length) {
        warnings.push('No items found in the Items table');
    }

    items.forEach((item, idx) => {
        const key     = (item.item_code || '').toLowerCase().trim();
        const ref     = dcs_reference_price(key, currency);
        const rowNum  = idx + 1;
        const rowName = item.item_code || 'Unknown';

        if (!ref) {
            warnings.push('Row ' + rowNum + ' — <b>' + rowName + '</b>: Not in AI price database (add it for future checks)');
            return;
        }

        const refCost = ref.cost * fxRate;
        const myCost  = item.cost_rate || 0;
        const mySell  = item.selling_rate || 0;
        const myGP    = item.gp_percent;

        // Cost check (±15% threshold)
        if (myCost <= 0) {
            warnings.push('Row ' + rowNum + ' — <b>' + rowName + '</b>: Cost Rate is 0 or empty');
        } else {
            const dev = Math.abs((myCost - refCost) / refCost * 100);
            if (dev > 25)
                issues.push('Row ' + rowNum + ' — <b>' + rowName + '</b>: Cost ' + myCost.toFixed(dcs_money_precision(frm)) + ' deviates <b>' + dev.toFixed(1) + '%</b> from reference (' + refCost.toFixed(dcs_money_precision(frm)) + ' ' + currency + ')');
            else if (dev > 15)
                warnings.push('Row ' + rowNum + ' — <b>' + rowName + '</b>: Cost ' + myCost.toFixed(dcs_money_precision(frm)) + ' deviates ' + dev.toFixed(1) + '% from reference (' + refCost.toFixed(dcs_money_precision(frm)) + ' ' + currency + ')');
            else
                passed.push('Row ' + rowNum + ' ' + rowName + ': Cost within 15% of reference (' + dev.toFixed(1) + '% deviation)');
        }

        // Selling below cost check
        if (mySell > 0 && mySell < refCost)
            issues.push('Row ' + rowNum + ' — <b>' + rowName + '</b>: Selling price (' + mySell.toFixed(dcs_money_precision(frm)) + ') is BELOW reference cost (' + refCost.toFixed(dcs_money_precision(frm)) + ') — <b>loss-making!</b>');
        else if (mySell <= 0)
            warnings.push('Row ' + rowNum + ' — <b>' + rowName + '</b>: Selling Rate is 0 — no revenue from this item');

        // GP% check
        if (myGP !== undefined && myGP !== null) {
            if (myGP < 5)
                warnings.push('Row ' + rowNum + ' — <b>' + rowName + '</b>: GP% is <b>' + myGP.toFixed(1) + '%</b> — very thin margin');
            else if (myGP < 10)
                warnings.push('Row ' + rowNum + ' — <b>' + rowName + '</b>: GP% is ' + myGP.toFixed(1) + '% — consider reviewing pricing');
            else
                passed.push('Row ' + rowNum + ' ' + rowName + ': GP% is ' + myGP.toFixed(1) + '% ✓');
        }
    });

    // ── Build Report HTML ────────────────────────────────────────────
    let html = '<div style="font-size:13px;line-height:1.8">';
    html += '<div style="background:#f4f6f7;padding:8px 12px;border-radius:4px;margin-bottom:12px">';
    html += '<b>Deal:</b> ' + (frm.doc.name || 'New') + ' &nbsp;|&nbsp; ';
    html += '<b>Customer:</b> ' + (frm.doc.customer || '—') + ' &nbsp;|&nbsp; ';
    html += '<b>Company:</b> ' + (company || '—') + ' &nbsp;|&nbsp; ';
    html += '<b>Currency:</b> ' + currency;
    html += '</div>';

    if (issues.length) {
        html += '<div style="background:#fdecea;border-left:4px solid #e74c3c;padding:10px 14px;margin:8px 0;border-radius:4px">';
        html += '<b style="color:#c0392b">🚨 Issues — Action Required (' + issues.length + ')</b><ul style="margin:6px 0 0 0;padding-left:18px">';
        issues.forEach(i => html += '<li style="color:#c0392b;margin:3px 0">' + i + '</li>');
        html += '</ul></div>';
    }
    if (warnings.length) {
        html += '<div style="background:#fef9e7;border-left:4px solid #e67e22;padding:10px 14px;margin:8px 0;border-radius:4px">';
        html += '<b style="color:#d35400">⚠️ Warnings — Review Recommended (' + warnings.length + ')</b><ul style="margin:6px 0 0 0;padding-left:18px">';
        warnings.forEach(w => html += '<li style="color:#d35400;margin:3px 0">' + w + '</li>');
        html += '</ul></div>';
    }
    if (passed.length) {
        html += '<div style="background:#eafaf1;border-left:4px solid #27ae60;padding:10px 14px;margin:8px 0;border-radius:4px">';
        html += '<b style="color:#1e8449">✅ Passed (' + passed.length + ')</b><ul style="margin:6px 0 0 0;padding-left:18px">';
        passed.forEach(p => html += '<li style="color:#1e8449;margin:3px 0">' + p + '</li>');
        html += '</ul></div>';
    }
    if (!issues.length && !warnings.length) {
        html += '<p style="font-size:16px;color:#27ae60;text-align:center;padding:20px">🎉 All checks passed! This deal looks great.</p>';
    }
    html += '</div>';

    frappe.msgprint({ title: '🤖 AI Deal Validation — ' + (frm.doc.name || 'New'), message: html, wide: true });
}

// ══════════════════════════════════════════════════════════════════════
// FUNCTION 3: Price Suggestions from AI Database
// ══════════════════════════════════════════════════════════════════════
function dcs_ai_price_suggestions(frm) {
    const items    = frm.doc.items || [];
    const currency = (frm.doc.currency || 'AED').toUpperCase();
    const fxRate   = 1.0;

    let html = '<div style="font-size:13px">';
    html += '<p style="color:#555;margin-bottom:10px">Same-currency reference prices (<b>' + currency + '</b>). Cross-currency references are omitted; no automatic conversion is applied.</p>';

    // Current items comparison table
    html += '<table style="width:100%;border-collapse:collapse">';
    html += '<thead><tr style="background:#2980b9;color:white;font-size:12px">';
    ['Item', 'Ref Cost (' + currency + ')', 'Ref Sell (' + currency + ')', 'Your Cost', 'Your Sell', 'GP%', 'AI Status'].forEach(h => {
        html += '<th style="padding:7px 10px;text-align:' + (h === 'Item' ? 'left' : 'right') + '">' + h + '</th>';
    });
    html = html.replace('text-align:right">AI Status', 'text-align:center">AI Status');
    html += '</tr></thead><tbody>';

    if (!items.length) {
        html += '<tr><td colspan="7" style="padding:14px;text-align:center;color:#999">No items in this Deal Cost Sheet</td></tr>';
    }

    items.forEach((item, idx) => {
        const key     = (item.item_code || '').toLowerCase().trim();
        const ref     = dcs_reference_price(key, currency);
        const bg      = idx % 2 === 0 ? '#f4f6f7' : '#fff';
        const refCost = ref ? (ref.cost * fxRate).toFixed(dcs_money_precision(frm)) : '—';
        const refSell = ref ? (ref.sell * fxRate).toFixed(dcs_money_precision(frm)) : '—';
        const myCost  = (item.cost_rate  || 0).toFixed(dcs_money_precision(frm));
        const mySell  = (item.selling_rate || 0).toFixed(dcs_money_precision(frm));
        const myGP    = item.gp_percent !== undefined ? item.gp_percent.toFixed(1) + '%' : '—';

        let status = '⚠️ No Ref'; let stClr = '#e67e22';
        if (ref) {
            const refC = ref.cost * fxRate;
            const dev  = item.cost_rate ? Math.abs((item.cost_rate - refC) / refC * 100) : 0;
            if ((item.selling_rate || 0) < refC && item.selling_rate > 0)
                { status = '🚨 Below Cost'; stClr = '#e74c3c'; }
            else if (dev > 25)
                { status = '🚨 High Deviation'; stClr = '#e74c3c'; }
            else if (dev > 15)
                { status = '⚠️ Check Price'; stClr = '#e67e22'; }
            else
                { status = '✅ OK'; stClr = '#27ae60'; }
        }

        html += '<tr style="background:' + bg + '">';
        html += '<td style="padding:7px 10px"><b>' + (item.item_code || '') + '</b></td>';
        html += '<td style="padding:7px 10px;text-align:right;color:#2980b9">' + refCost + '</td>';
        html += '<td style="padding:7px 10px;text-align:right;color:#2980b9">' + refSell + '</td>';
        html += '<td style="padding:7px 10px;text-align:right">' + myCost + '</td>';
        html += '<td style="padding:7px 10px;text-align:right">' + mySell + '</td>';
        html += '<td style="padding:7px 10px;text-align:right">' + myGP + '</td>';
        html += '<td style="padding:7px 10px;text-align:center;color:' + stClr + ';font-weight:bold">' + status + '</td>';
        html += '</tr>';
    });
    html += '</tbody></table>';

    // Full price DB panel
    const dbKeys = Object.keys(AI_PRICE_DB);
    html += '<br><details style="margin-top:8px"><summary style="cursor:pointer;font-weight:bold;color:#2980b9;background:#eaf4fb;padding:7px 12px;border-radius:4px">📚 Full AI Price Database (' + dbKeys.length + ' items — click to expand)</summary>';
    html += '<table style="width:100%;border-collapse:collapse;margin-top:8px;font-size:12px">';
    html += '<thead><tr style="background:#27ae60;color:white"><th style="padding:6px 8px;text-align:left">Item Code</th><th style="padding:6px 8px;text-align:right">Cost</th><th style="padding:6px 8px;text-align:right">Selling</th><th style="padding:6px 8px">Currency</th><th style="padding:6px 8px">Notes</th></tr></thead><tbody>';
    dbKeys.forEach((k, i) => {
        const v = AI_PRICE_DB[k];
        const bg = i % 2 === 0 ? '#f9f9f9' : '#fff';
        html += '<tr style="background:' + bg + '"><td style="padding:5px 8px">' + k + '</td><td style="padding:5px 8px;text-align:right">' + v.cost + '</td><td style="padding:5px 8px;text-align:right">' + v.sell + '</td><td style="padding:5px 8px">' + frappe.utils.escape_html(v.currency || '') + '</td><td style="padding:5px 8px;color:#777">' + (v.notes||'') + '</td></tr>';
    });
    html += '</tbody></table>';
    html += '<p style="margin:8px 0 0;color:#999;font-size:11px">💡 To add more items: Go to Build → Client Script → Deal Cost Sheet AI Assistant and update the AI_PRICE_DB object.</p>';
    html += '</details></div>';

    frappe.msgprint({ title: '💰 AI Price Suggestions', message: html, wide: true });
}

// ══════════════════════════════════════════════════════════════════════
// FUNCTION 4: Compare with Previous Proposals
// ══════════════════════════════════════════════════════════════════════
function dcs_ai_compare_proposals(frm) {
    if (!frm.doc.customer) {
        frappe.msgprint({ title: 'No Customer Selected', message: 'Please select a <b>Customer</b> first to compare previous proposals.', indicator: 'orange' });
        return;
    }

    frappe.show_alert({ message: '🤖 Loading previous proposals...', indicator: 'blue' });

    frappe.call({
        method: 'frappe.client.get_list',
        args: {
            doctype:  'Deal Cost Sheet',
            filters: [
                ['customer', '=', frm.doc.customer],
                ['currency', '=', frm.doc.currency],
                ['name',     '!=', frm.doc.name || '__new__'],
            ],
            fields:   ['name', 'company', 'currency', 'total_cost', 'total_selling', 'status', 'creation'],
            order_by: 'creation desc',
            limit:    10
        },
        callback(r) {
            const docs = r.message || [];
            let html   = '<div style="font-size:13px">';

            if (!docs.length) {
                html += '<div style="text-align:center;padding:30px;color:#777">';
                html += '<p style="font-size:16px">📋 No previous proposals found for <b>' + frm.doc.customer + '</b></p>';
                html += '<p>This appears to be the <b>first deal</b> for this customer!</p>';
                html += '</div>';
            } else {
                html += '<p style="margin-bottom:10px">Found <b>' + docs.length + '</b> previous Deal Cost Sheet(s) for <b>' + frm.doc.customer + '</b>:</p>';
                html += '<table style="width:100%;border-collapse:collapse">';
                html += '<thead><tr style="background:#8e44ad;color:white;font-size:12px">';
                html += '<th style="padding:8px;text-align:left">DCS ID</th>';
                html += '<th style="padding:8px">Company</th>';
                html += '<th style="padding:8px">Currency</th>';
                html += '<th style="padding:8px;text-align:right">Total Cost</th>';
                html += '<th style="padding:8px;text-align:right">Total Selling</th>';
                html += '<th style="padding:8px;text-align:right">Margin %</th>';
                html += '<th style="padding:8px;text-align:center">Status</th>';
                html += '<th style="padding:8px">Date</th>';
                html += '</tr></thead><tbody>';

                docs.forEach((doc, i) => {
                    const bg     = i % 2 === 0 ? '#f4f6f7' : '#fff';
                    const date   = (doc.creation || '').split(' ')[0];
                    const margin = doc.total_selling > 0
                        ? (((doc.total_selling - doc.total_cost) / doc.total_selling) * 100).toFixed(1) + '%'
                        : 'N/A';
                    const stColor = doc.status === 'Submitted' ? '#27ae60' : doc.status === 'Cancelled' ? '#e74c3c' : '#e67e22';

                    html += '<tr style="background:' + bg + '">';
                    html += '<td style="padding:8px"><a href="' + frappe.utils.get_form_link('Deal Cost Sheet', doc.name) + '" target="_blank" style="color:#2980b9">' + doc.name + '</a></td>';
                    html += '<td style="padding:8px">' + (doc.company || '') + '</td>';
                    html += '<td style="padding:8px">' + (doc.currency || '') + '</td>';
                    html += '<td style="padding:8px;text-align:right">' + ((doc.total_cost || 0).toFixed(dcs_money_precision(frm))) + '</td>';
                    html += '<td style="padding:8px;text-align:right">' + ((doc.total_selling || 0).toFixed(dcs_money_precision(frm))) + '</td>';
                    html += '<td style="padding:8px;text-align:right">' + margin + '</td>';
                    html += '<td style="padding:8px;text-align:center"><span style="background:' + stColor + ';color:white;padding:2px 8px;border-radius:3px;font-size:11px">' + (doc.status || '') + '</span></td>';
                    html += '<td style="padding:8px;color:#777">' + date + '</td>';
                    html += '</tr>';
                });
                html += '</tbody></table>';

                // Current vs Last comparison box
                const currMargin = frm.doc.total_selling > 0
                    ? (((frm.doc.total_selling - frm.doc.total_cost) / frm.doc.total_selling) * 100).toFixed(1) + '%'
                    : 'N/A';

                html += '<br><div style="background:#eaf4fb;padding:12px 16px;border-radius:6px;border-left:4px solid #3498db">';
                html += '<b>📌 Current Deal:</b> ';
                html += 'Cost: <b>' + ((frm.doc.total_cost || 0).toFixed(dcs_money_precision(frm))) + '</b> | ';
                html += 'Selling: <b>' + ((frm.doc.total_selling || 0).toFixed(dcs_money_precision(frm))) + '</b> | ';
                html += 'Margin: <b>' + currMargin + '</b>';
                if (docs.length > 0 && docs[0].total_selling > 0) {
                    const lastSell = docs[0].total_selling;
                    const currSell = frm.doc.total_selling || 0;
                    const change   = ((currSell - lastSell) / lastSell * 100).toFixed(1);
                    const icon     = parseFloat(change) >= 0 ? '📈' : '📉';
                    html += ' | vs Last Proposal: ' + icon + ' <b>' + (parseFloat(change) >= 0 ? '+' : '') + change + '%</b>';
                }
                html += '</div>';
            }

            html += '</div>';
            frappe.msgprint({ title: '📊 Previous Proposals — ' + frm.doc.customer, message: html, wide: true });
        }
    });
}

// ══════════════════════════════════════════════════════════════════════
// FUNCTION 5: Quick Add Item — Create Item master + add to table
// ══════════════════════════════════════════════════════════════════════
function dcs_quick_add_item(frm) {
    const d = new frappe.ui.Dialog({
        title: '➕ Quick Add Item to Deal',
        fields: [
            {
                label: 'Item Name',
                fieldname: 'item_name',
                fieldtype: 'Data',
                reqd: 1,
                description: 'Full descriptive name (becomes the Item Code if new)'
            },
            {
                label: 'Item Category',
                fieldname: 'item_category',
                fieldtype: 'Select',
                options: '\nProducts\nProfessional Services',
                reqd: 1
            },
            {
                label: 'Item Group',
                fieldname: 'item_group',
                fieldtype: 'Link',
                options: 'Item Group',
                reqd: 1,
                default: 'Products'
            },
            { fieldtype: 'Column Break' },
            {
                label: 'Qty',
                fieldname: 'qty',
                fieldtype: 'Float',
                reqd: 1,
                default: 1
            },
            {
                label: 'Cost Rate',
                fieldname: 'cost_rate',
                fieldtype: 'Currency',
                reqd: 1
            },
            {
                label: 'Selling Rate',
                fieldname: 'selling_rate',
                fieldtype: 'Currency',
                reqd: 1
            },
            { fieldtype: 'Section Break' },
            {
                label: 'Header / Section Label',
                fieldname: 'header',
                fieldtype: 'Data',
                description: 'Optional — e.g. "Supply", "Installation"'
            },
            {
                label: 'Brand',
                fieldname: 'brand',
                fieldtype: 'Link',
                options: 'Brand'
            }
        ],
        primary_action_label: '✅ Create & Add',
        primary_action(values) {
            d.hide();
            const itemName = (values.item_name || '').trim();
            if (!itemName) { frappe.msgprint('Item Name is required'); return; }

            frappe.show_alert({ message: '⏳ Checking item...', indicator: 'blue' });

            // Check if item already exists
            frappe.call({
                method: 'frappe.client.get_list',
                args: {
                    doctype: 'Item',
                    filters: [['item_name', '=', itemName]],
                    fields: ['name', 'item_name'],
                    limit: 1
                },
                callback(r) {
                    const existing = r.message && r.message.length > 0 ? r.message[0] : null;
                    if (existing) {
                        // Item exists — add directly to table
                        frappe.show_alert({ message: '✅ Item found — adding to table', indicator: 'green' });
                        dcs_add_row_to_items(frm, existing.name, existing.item_name, values);
                    } else {
                        // Create new Item master
                        frappe.show_alert({ message: '⚙️ Creating new item...', indicator: 'orange' });
                        frappe.call({
                            method: 'frappe.client.insert',
                            args: {
                                doc: {
                                    doctype: 'Item',
                                    item_code: itemName,
                                    item_name: itemName,
                                    item_group: values.item_group || 'Products',
                                    stock_uom: 'Nos',
                                    is_stock_item: 0,
                                    include_item_in_manufacturing: 0
                                }
                            },
                            callback(res) {
                                if (res.message) {
                                    frappe.show_alert({ message: '✅ Item created: ' + res.message.name, indicator: 'green' });
                                    dcs_add_row_to_items(frm, res.message.name, res.message.item_name, values);
                                } else {
                                    frappe.msgprint({ title: 'Error', message: 'Failed to create item. Check permissions.', indicator: 'red' });
                                }
                            },
                            error(err) {
                                frappe.msgprint({ title: 'Item Creation Failed', message: err.message || 'Unknown error', indicator: 'red' });
                            }
                        });
                    }
                }
            });
        }
    });
    d.show();
}

function dcs_add_row_to_items(frm, item_code, item_name, values) {
    const row = frappe.model.add_child(frm.doc, 'Deal Cost Item', 'items');
    row.item_code      = item_code;
    row.item_name      = item_name;
    row.item_category  = values.item_category || '';
    row.qty            = values.qty || 1;
    row.cost_rate      = values.cost_rate || 0;
    row.selling_rate   = values.selling_rate || 0;
    row.header         = values.header || '';
    row.brand          = values.brand || '';
    frm.refresh_field('items');
    frappe.show_alert({ message: '🎉 "' + item_name + '" added to the Items table!', indicator: 'green' });
}


// Deal Cost Sheet List View - Hide cancelled (amended) records by default
frappe.listview_settings["Deal Cost Sheet"] = {
    onload: function(listview) {
        // Remove any existing docstatus filter first to avoid conflicts
        listview.filter_area.add([
            ["Deal Cost Sheet", "docstatus", "!=", "2"]
        ]);
    },
    before_render: function() {
        // Ensure filter is applied before rendering
    }
};

// Also apply via route_options for initial page load
if (frappe.route_options === undefined || frappe.route_options === null) {
    frappe.route_options = {};
}


/* =====================================================================
   SUPERSEDED / DEAD LEGACY LOGIC - DO NOT REACTIVATE OR REUSE
   Recorded 2026-08-08 during the production ERPNext build.
   Renders custom_version_no / custom_version_history /
   custom_last_revised_by / custom_last_revised_on - none of which exist.
   SUPERSEDED BY: DocType 'DCS Revision' + 'dcs_apply_revision'.
   Retained, not deleted. Already disabled. Keep disabled.
   ===================================================================== */

frappe.ui.form.on("Deal Cost Sheet", {
    refresh: function(frm) {
        // Show version badge in form header
        if (frm.doc.custom_version_no) {
            frm.set_intro(
                '<b>Version ' + frm.doc.custom_version_no + '</b>' +
                (frm.doc.custom_last_revised_by ? ' &nbsp;|&nbsp; Last revised by: <b>' + frm.doc.custom_last_revised_by + '</b>' : '') +
                (frm.doc.custom_last_revised_on ? ' on <b>' + frappe.datetime.str_to_user(frm.doc.custom_last_revised_on) + '</b>' : ''),
                'blue'
            );
        }

        // Render version history table if available
        if (frm.doc.custom_version_history) {
            try {
                var history = JSON.parse(frm.doc.custom_version_history);
                if (history && history.length > 0) {
                    var rows = history.map(function(v) {
                        return '<tr>' +
                            '<td style="padding:4px 8px;border:1px solid #e0e0e0;"><b>v' + v.version + '</b></td>' +
                            '<td style="padding:4px 8px;border:1px solid #e0e0e0;">' + (v.revised_by || '-') + '</td>' +
                            '<td style="padding:4px 8px;border:1px solid #e0e0e0;">' + (v.revised_on ? v.revised_on.substring(0,16) : '-') + '</td>' +
                            '<td style="padding:4px 8px;border:1px solid #e0e0e0;text-align:right;">' + dcs_money(frm, v.total_cost || 0) + '</td>' +
                            '<td style="padding:4px 8px;border:1px solid #e0e0e0;text-align:right;">' + dcs_money(frm, v.total_selling || 0) + '</td>' +
                        '</tr>';
                    }).join('');

                    var html = '<div style="margin:10px 0;">' +
                        '<b>Version History</b>' +
                        '<table style="width:100%;border-collapse:collapse;margin-top:6px;font-size:12px;">' +
                        '<thead><tr style="background:#f5f5f5;">' +
                        '<th style="padding:4px 8px;border:1px solid #e0e0e0;text-align:left;">Ver</th>' +
                        '<th style="padding:4px 8px;border:1px solid #e0e0e0;text-align:left;">Revised By</th>' +
                        '<th style="padding:4px 8px;border:1px solid #e0e0e0;text-align:left;">Date</th>' +
                        '<th style="padding:4px 8px;border:1px solid #e0e0e0;text-align:right;">Cost</th>' +
                        '<th style="padding:4px 8px;border:1px solid #e0e0e0;text-align:right;">Selling</th>' +
                        '</tr></thead><tbody>' + rows + '</tbody></table></div>';

                    frm.set_df_property('custom_version_history', 'description', html);
                }
            } catch(e) {}
        }
    }
});


// DCS_QA_VERSION: V19 2026-07-15 - Same as V18 plus: the 'Analysis: N new item(s) not in ERP...' banner text above the preview table now also refreshes live when 'Use Generic' is clicked, instead of staying stuck on the stale pre-click wording.
// AUTO-EXPOSE: These functions must be global for onclick handlers
(function() {
    // This block runs immediately when the script loads
    console.log("DCS_SCRIPT_LOADED: version check");
})();
frappe.ui.form.on('Deal Cost Sheet', {
    refresh: function(frm) { dcsInit(frm); if (window.dcsLiveCalc) window.dcsLiveCalc(frm);
        // Override app's strict presales_request filter — allow all PRs when no opportunity set
        frm.set_query('presales_request', function() {
            if (frm.doc.opportunity) {
                return { filters: { opportunity: frm.doc.opportunity } };
            }
            return {}; // No filter — show all Presales Requests
        });
        // Guard: intercept frappe.call to block read_deal_cost_sheet when no attachment
        if (!window._dcsCallIntercepted) {
            window._dcsCallIntercepted = true;
            var _origFrappeCall = frappe.call;
            frappe.call = function(opts) {
                if (opts && opts.method && opts.method.indexOf('read_deal_cost_sheet') >= 0) {
                    if (!opts.args || !opts.args.file_url) {
                        frappe.show_alert({ message: '📎 Please attach a PDF document first, then click Get Data', indicator: 'orange' }, 5);
                        return;
                    }
                }
                return _origFrappeCall.apply(frappe, arguments);
            };
        }
    },
    onload_post_render: function(frm) { dcsInit(frm); if (window.dcsLiveCalc) window.dcsLiveCalc(frm); }
,
    onload: function(frm) {
        dcs_fetch_party_details(frm);
        // Default Deal Owner to current user on new DCS
        if (frm.is_new() && !frm.doc.deal_owner) {
            frm.set_value('deal_owner', frappe.session.user);
        }
    },
    opportunity: function(frm) {
        // Re-set presales_request filter when opportunity changes
        frm.set_query('presales_request', function() {
            if (frm.doc.opportunity) {
                return { filters: { opportunity: frm.doc.opportunity } };
            }
            return {};
        });
        // Clear presales_request if it doesn't match new opportunity
        if (frm.doc.presales_request && frm.doc.opportunity) {
            frappe.db.get_value('Presales Request', frm.doc.presales_request, 'opportunity', function(r) {
                if (r && r.opportunity !== frm.doc.opportunity) {
                    frm.set_value('presales_request', '');
                }
            });
        }
        var opp = frm.doc.opportunity;
        if (!opp || frm.doc.docstatus !== 0) return;
        frappe.db.get_value('Opportunity', opp, ['opportunity_from', 'party_name', 'opportunity_owner', 'custom_subject'], function(r) {
            if (!r || frm.doc.opportunity !== opp) return;
            frm.set_value({party_type:r.opportunity_from, party:r.party_name,
                customer:r.opportunity_from === 'Customer' ? r.party_name : ''});
            if (r.custom_subject && !frm.doc.subject) frm.set_value('subject', r.custom_subject);
            if (r.opportunity_owner && !frm.doc.deal_owner) frm.set_value('deal_owner', r.opportunity_owner);
            dcs_fetch_party_details(frm);
        });
    }
});

// =====================================================================
// LIVE COMMERCIAL SUMMARY - Updates totals as items are edited
// =====================================================================
frappe.ui.form.on('Deal Cost Item', {
    cost_rate: function(frm, cdt, cdn) { if (window.dcsLiveCalc) window.dcsLiveCalc(frm, true); },
    selling_rate: function(frm, cdt, cdn) { if (window.dcsLiveCalc) window.dcsLiveCalc(frm, true); },
    qty: function(frm, cdt, cdn) { if (window.dcsLiveCalc) window.dcsLiveCalc(frm, true); },
    items_remove: function(frm) { if (window.dcsLiveCalc) window.dcsLiveCalc(frm, true); }
});

function dcsInit(frm) {
  ['dcs-quick-add-btn','dcs-bulk-modal','dcs-modal-overlay','dcs-ai-provider-btn','dcs-styles'].forEach(function(id) {
    var el = document.getElementById(id); if (el) el.remove();
  });

  // Fetch valid Item Groups once per session so Quick Add never assigns/creates
  // items with a group that doesn't exist in this ERP (previously caused silent
  // Item-creation failures and invalid Item Codes being added to the deal).
  if (!window._dcsValidGroups) {
    window._dcsValidGroups = ['Products','Services','Professional Services'];
    frappe.call({
      method: 'frappe.client.get_list',
      args: { doctype: 'Item Group', fields: ['name'], filters: [['is_group','=',0]], limit_page_length: 100 },
      callback: function(r) {
        var list = (r && r.message) ? r.message.map(function(g) { return g.name; }) : [];
        if (list.length) window._dcsValidGroups = list;
      }
    });
  }

    // CSS
    var style = document.createElement('style');
    style.id = 'dcs-styles';
    style.textContent = [
        '#dcs-quick-add-btn{background:linear-gradient(135deg,#6c63ff,#4ecdc4);color:#fff;border:none;border-radius:8px;padding:8px 18px;font-size:13px;font-weight:600;cursor:pointer;margin:8px 4px;box-shadow:0 3px 10px rgba(108,99,255,.4);}',
        '#dcs-ai-provider-btn{position:fixed;bottom:20px;right:20px;z-index:9000;background:linear-gradient(135deg,#667eea,#764ba2);color:#fff;border:none;border-radius:25px;padding:10px 18px;font-size:13px;font-weight:600;cursor:pointer;}',
        '#dcs-modal-overlay{position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:9998;display:flex;align-items:center;justify-content:center;}',
        '#dcs-bulk-modal{background:#fff;border-radius:14px;width:960px;max-width:96vw;max-height:90vh;overflow:hidden;display:flex;flex-direction:column;position:relative;box-shadow:0 20px 60px rgba(0,0,0,.3);font-family:-apple-system,BlinkMacSystemFont,\'Segoe UI\',sans-serif;}',
        '.dcs-mhdr{background:linear-gradient(135deg,#6c63ff,#4ecdc4);color:#fff;padding:18px 24px;border-radius:14px 14px 0 0;display:flex;justify-content:space-between;align-items:center;flex:0 0 auto;}',
        '.dcs-mhdr h3{margin:0;font-size:17px;}',
        '.dcs-mclose{background:rgba(255,255,255,.2);border:none;color:#fff;width:30px;height:30px;border-radius:50%;cursor:pointer;font-size:17px;}',
        '.dcs-tabs{display:flex;border-bottom:2px solid #e8e8e8;padding:0 24px;background:#fafafa;flex:0 0 auto;}',
        '.dcs-tab{padding:11px 18px;cursor:pointer;font-size:13px;font-weight:500;color:#666;border-bottom:3px solid transparent;margin-bottom:-2px;}',
        '.dcs-tab.active{color:#6c63ff;border-bottom-color:#6c63ff;font-weight:600;}',
        '.dcs-tpane{display:none;padding:18px 24px;}.dcs-tpane.active{display:block;}',
        '.dcs-ta{width:100%;min-height:150px;border:2px solid #e0e0e0;border-radius:8px;padding:12px;font-size:13px;font-family:\'Courier New\',monospace;resize:vertical;box-sizing:border-box;}',
        '.dcs-ta:focus{outline:none;border-color:#6c63ff;}',
        '.dcs-btn{padding:9px 18px;border:none;border-radius:8px;font-size:13px;font-weight:600;cursor:pointer;margin:3px;}',
        '.dcs-bp{background:linear-gradient(135deg,#6c63ff,#4ecdc4);color:#fff;}',
        '.dcs-bs{background:linear-gradient(135deg,#56ab2f,#a8e063);color:#fff;}',
        '.dcs-bn{background:#f0f0f0;color:#555;}',
        '.dcs-sbar{display:flex;gap:10px;padding:12px 24px;background:#f8f9ff;border-top:1px solid #e8e8e8;flex-wrap:wrap;align-items:center;}',
        '.dcs-chip{padding:4px 12px;border-radius:20px;font-size:12px;font-weight:700;}',
        '.chip-t{background:#e8eaff;color:#3d35b5;}.chip-r{background:#d4f5e3;color:#1a7a3f;}.chip-n{background:#e0f0ff;color:#1565c0;}.chip-w{background:#fff3cd;color:#856404;}.chip-e{background:#fde8e8;color:#c0392b;}',
        '.dcs-arev{margin:0 24px 12px;padding:10px 15px;background:linear-gradient(135deg,#f3e8ff,#e8f0ff);border-left:4px solid #9c6fe4;border-radius:0 8px 8px 0;font-size:12px;color:#4a2d82;}',
        '.dcs-pwrap{padding:0 24px 16px;}',
        '.dcs-pt{width:100%;border-collapse:collapse;font-size:12.5px;}',
        '.dcs-pt th{background:#f0f0f0;padding:7px 10px;text-align:left;font-weight:600;color:#444;border-bottom:2px solid #ddd;}',
        '.dcs-pt td{padding:6px 9px;border-bottom:1px solid #eee;vertical-align:middle;}',
        '.dcs-pt tr.row-ready{background:#f6fff9;}.dcs-pt tr.row-new{background:#f0f8ff;}.dcs-pt tr.row-warn{background:#fffdf0;}.dcs-pt tr.row-error{background:#fff5f5;}',
        '.dcs-badge{display:inline-block;padding:2px 8px;border-radius:12px;font-size:11px;font-weight:700;}',
        '.b-r{background:#d4f5e3;color:#1a7a3f;}.b-n{background:#e0f0ff;color:#1565c0;}.b-w{background:#fff3cd;color:#856404;}.b-e{background:#fde8e8;color:#c0392b;}',
        '.dcs-note{padding:2px 6px;border-radius:5px;font-size:11px;display:inline-block;margin:1px;}',
        '.note-ai{background:#f0ebff;color:#5b2d91;}.note-rule{background:#e8f0ff;color:#1565c0;}',
        '.dcs-ed{border:1px solid transparent;border-radius:4px;padding:2px 5px;min-width:45px;display:inline-block;}',
        '.dcs-ed:hover{border-color:#b0b0ff;}.dcs-ed:focus{outline:none;border-color:#6c63ff;background:#f8f7ff;}',
        '.dcs-sel{font-size:11px;border:1px solid #ccc;border-radius:4px;padding:2px 4px;}',
        '.dcs-foot{padding:12px 24px;background:#fafafa;border-top:1px solid #eee;display:flex;justify-content:space-between;align-items:center;border-radius:0 0 14px 14px;flex:0 0 auto;}',
        '#dcs-tp-paste,#dcs-tp-upload,#dcs-tp-type,#dcs-tp-guide,#dcs-preview-area{flex:1 1 auto;min-height:0;overflow-y:auto;}',
        '.dcs-load{text-align:center;padding:20px;color:#6c63ff;font-size:13px;}',
        '.dcs-spin{display:inline-block;width:18px;height:18px;border:3px solid #e0e0ff;border-top-color:#6c63ff;border-radius:50%;animation:dcs-spin .8s linear infinite;margin-right:6px;vertical-align:middle;}',
        '@keyframes dcs-spin{to{transform:rotate(360deg);}}',
        '.dcs-upzone{border:2px dashed #b0b0ff;border-radius:10px;padding:28px;text-align:center;color:#888;cursor:pointer;}',
        '.dcs-aira-help-btn{background:linear-gradient(135deg,#6c63ff,#4ecdc4);color:#fff;border:none;border-radius:20px;padding:5px 12px;font-size:11px;font-weight:600;cursor:pointer;display:flex;align-items:center;gap:5px;letter-spacing:.3px;transition:opacity .2s;}',
        '.dcs-aira-help-btn:hover{opacity:.85;}',
        '#dcs-help-panel{position:absolute;top:0;right:0;width:380px;height:100%;background:#fff;border-left:2px solid #e8eaff;border-radius:0 14px 14px 0;overflow-y:auto;padding:20px;box-sizing:border-box;z-index:10;transform:translateX(100%);transition:transform .25s ease;}',
        '#dcs-help-panel.open{transform:translateX(0);}',
        '.dcs-help-title{font-size:15px;font-weight:700;color:#6c63ff;margin:0 0 4px;display:flex;align-items:center;gap:6px;}',
        '.dcs-help-sub{font-size:11px;color:#888;margin:0 0 14px;}',
        '.dcs-help-section{margin-bottom:14px;}',
        '.dcs-help-section h4{font-size:12px;font-weight:700;color:#333;margin:0 0 6px;padding:4px 8px;background:#f0f0ff;border-radius:4px;border-left:3px solid #6c63ff;}',
        '.dcs-help-step{display:flex;gap:8px;margin-bottom:7px;font-size:12px;align-items:flex-start;}',
        '.dcs-help-step .dcs-step-num{background:#6c63ff;color:#fff;border-radius:50%;width:18px;height:18px;display:flex;align-items:center;justify-content:center;font-size:10px;font-weight:700;flex-shrink:0;margin-top:1px;}',
        '.dcs-help-badge{display:inline-block;padding:2px 7px;border-radius:10px;font-size:10px;font-weight:600;margin:2px 2px 2px 0;}',
        '.dcs-badge-green{background:#e6f9f0;color:#1a7a4a;}',
        '.dcs-badge-blue{background:#e8eaff;color:#4b4bcc;}',
        '.dcs-badge-orange{background:#fff3e0;color:#b36a00;}',
        '.dcs-help-table{width:100%;border-collapse:collapse;font-size:11px;margin-top:6px;}',
        '.dcs-help-table th{background:#f0f0ff;padding:5px 7px;text-align:left;border:1px solid #e0e0ff;color:#555;}',
        '.dcs-help-table td{padding:5px 7px;border:1px solid #eee;vertical-align:top;}',
        '.dcs-help-note{background:#fffbe6;border-left:3px solid #f5c518;border-radius:4px;padding:8px 10px;font-size:11px;color:#666;margin-top:8px;}',
        '.dcs-help-close{float:right;background:none;border:none;font-size:18px;cursor:pointer;color:#999;margin-top:-2px;}',
    ].join('');
    document.head.appendChild(style);

    // Quick Add Button (suppressed on cancelled sheets)
    dcsQuickAddButton(frm);

    // Keep administration settings in the native secondary-actions menu.
    if (frappe.user.has_role('System Manager') || frappe.user.has_role('Administrator')) {
        frm.add_custom_button(__('AI provider settings'),function(){dcsOpenAISettings();},__('More actions'));
    }

    // Expose functions as globals for onclick attributes
    window.dcsToggleHelp = dcsToggleHelp;
    window.dcsAnalyse = dcsAnalyse;
    window.dcsAnalyseType = dcsAnalyseType;
    window.dcsDoImport = dcsDoImport;
    window.dcsDownloadTemplate = dcsDownloadTemplate;
    window.dcsTab = dcsTab;
    window.dcsUF = dcsUF;
    window.dcsToggleAll = dcsToggleAll;
    window.dcsTogRow = dcsTogRow;
    window.dcsOpenAISettings = dcsOpenAISettings;
    window.dcsAutoCreateItems = dcsAutoCreateItems;
    // Define dcsProcess and dcsUpdateMargin here in closure scope
    window.dcsProcess = function dcsProcess(rows, erp, aiText, provider, errMsg) {
    window._dcsErrMsg = errMsg;
        var useAI = !!(aiText && !errMsg);
        var aiData = {};
        if (useAI) {
            try {
                var cleaned = aiText.replace(/^```json\s*/,'').replace(/```\s*$/,'').trim();
                var arr = JSON.parse(cleaned);
                if (Array.isArray(arr)) {
                    arr.forEach(function(a) { if (a.row) aiData[a.row] = a; });
                }
            } catch(e) { useAI = false; }
        }
    
        // Status bar
        var total = rows.length, newCount = 0, errCount = 0;
        var provLabel = useAI ? (provider || 'AI') : 'Rule-based';
        window._dcsProvLabel = provLabel;
        var provClass = useAI ? 'note-ai' : 'note-rule';
    
        // Build rows
        window._dcsRows = [];
        var tbody = document.getElementById('dcs-tbody');
        var html = '';
        rows.forEach(function(row, i) {
            var ai = aiData[row.idx] || {};
            // Apply AI suggested sell price if user did not provide one
            if (ai && ai.suggested_sell > 0 && !(row.sell > 0)) { row.sell = parseFloat(ai.suggested_sell) || 0; }
            // Match against ERP
            var match = null, bestScore = 0;
            erp.forEach(function(e) {
                var sc = (row.itemCode && e.item_code && row.itemCode.toLowerCase() === e.item_code.toLowerCase()) ? 1 : dcsSim(row.name, e.item_name || e.item_code || '');
                if (sc > bestScore) { bestScore = sc; match = e; }
            });
            var isExisting = match && bestScore > 0.55;
            var status, statusCls, badgeCls, rowCls;
            var sellOK = row.sell > 0 && row.sell >= row.cost;
            
            if (row.sell > 0 && row.sell < row.cost) {
                status = 'Error'; statusCls = 'b-e'; rowCls = 'row-error';
            } else if (isExisting) {
                status = 'Existing Item'; statusCls = 'b-r'; rowCls = 'row-ready';
            } else {
                status = 'New Item'; statusCls = 'b-n'; rowCls = 'row-new';
            }
            
            var validGroups = (window._dcsValidGroups && window._dcsValidGroups.length) ? window._dcsValidGroups : ['Products','Services','Professional Services'];
        var itemGroup = ai.item_group || dcsGuess(row.name);
        if (validGroups.indexOf(itemGroup) === -1) {
          itemGroup = (validGroups.indexOf('Products') !== -1) ? 'Products' : validGroups[0];
        }
            var note = useAI ? ('<span class="dcs-note note-ai">AI</span> ' + (ai.reason || '')) : '<span class="dcs-note note-rule">Rule-based</span>';
            if (row.sell > 0 && row.sell < row.cost) note += ' <b style="color:#c0392b">Selling below cost! Margin: ' + (((row.sell-row.cost)/row.cost)*100).toFixed(1) + '%</b>';
            
            var margin = (row.cost > 0 && row.sell > 0) ? (((row.sell-row.cost)/row.sell)*100).toFixed(1)+'%' : '-';
            var marginColour = (row.sell > 0 && row.sell < row.cost) ? 'color:#c0392b' : (parseFloat(margin) > 20 ? 'color:#1a7a3f' : 'color:#856404');
            
            var itemName = isExisting ? (match.item_name || match.item_code) : row.name;
            var itemCode = isExisting ? (match.item_code || row.name) : (row.itemCode || row.name);
            
            var rowObj = { idx: row.idx, name: itemName, item_code: itemCode, qty: row.qty, cost: row.cost, sell: row.sell, header: row.header, item_group: itemGroup, _status: isExisting ? 'existing' : 'new_item', _checked: !(row.sell > 0 && row.sell < row.cost) };
            window._dcsRows.push(rowObj);
            newCount += isExisting ? 0 : 1;
            if (row.sell > 0 && row.sell < row.cost) errCount++;
            
            var groups = validGroups;
            var groupOpts = groups.map(function(g){ return '<option value="'+g+'"'+(g===itemGroup?' selected':'')+'>'+g+'</option>'; }).join('');
            
            var chk = rowObj._checked ? 'checked' : '';
            html += '<tr class="'+rowCls+'" id="dcs-row-'+i+'">' +
                '<td><input type="checkbox" '+chk+' onchange="dcsTogRow('+i+',this.checked)"></td>' +
                '<td>'+row.idx+'</td>' +
                '<td><span class="dcs-badge '+statusCls+'">'+status+'</span>'+(status==='New Item'?(' <a href="#" onclick="dcsUseGeneric('+i+');return false;" style="font-size:10px;color:#4f8cff;text-decoration:underline;white-space:nowrap;display:block;margin-top:2px;">Use Generic</a>'):'')+'</td>' +
                '<td contenteditable="true" class="dcs-ed" data-row="'+i+'" data-field="name" onblur="dcsUF('+i+',\'name\',this.textContent)">'+itemName+'</td>' +
                '<td><input type="number" class="dcs-ed" value="'+row.qty+'" min="0.001" step="any" style="width:55px" onchange="dcsUF('+i+',\'qty\',this.value)"></td>' +
                '<td><input type="number" class="dcs-ed" value="'+row.cost+'" min="0" step="any" style="width:75px" onchange="dcsUF('+i+',\'cost\',this.value)"></td>' +
                '<td><input type="number" class="dcs-ed" value="'+row.sell+'" min="0" step="any" style="width:75px" onchange="dcsUF('+i+',\'sell\',this.value);dcsUpdateMargin('+i+')"></td>' +
                '<td id="dcs-margin-'+i+'" style="font-weight:700;'+marginColour+'">'+margin+'</td>' +
                '<td><select class="dcs-sel" onchange="dcsUF('+i+',\'item_group\',this.value)">'+groupOpts+'</select></td>' +
                '<td style="font-size:11px;color:#666;max-width:200px">'+note+'</td>' +
                '</tr>';
        });
        
        if (tbody) tbody.innerHTML = html || '<tr><td colspan="10" style="text-align:center;color:#999;padding:20px">No items found</td></tr>';
        
        // Status bar
        function dcsRefreshSummaryBar() {
        var rows = window._dcsRows || [];
        var total = rows.length, newCount = 0, errCount = 0;
        rows.forEach(function(r) {
            newCount += (r._status === 'new_item') ? 1 : 0;
            if (r.sell > 0 && r.sell < r.cost) errCount++;
        });
        var provLabel = window._dcsProvLabel || 'AI';
        var sbar = document.getElementById('dcs-sbar');
        if (sbar) {
            var chips = '<span class="dcs-chip chip-t">'+total+' Total</span>';
            if (newCount > 0) chips += ' <span class="dcs-chip chip-n">'+newCount+' New</span>';
            if (errCount > 0) chips += ' <span class="dcs-chip chip-e">'+errCount+' Error</span>';
            if (total - newCount - errCount > 0) chips += ' <span class="dcs-chip chip-r">'+(total-newCount-errCount)+' Existing</span>';
            if (newCount > 0) chips += ' <button id="dcs-autocreate-btn" onclick="dcsAutoCreateItems()" style="margin-left:8px;padding:4px 12px;background:linear-gradient(135deg,#1565c0,#42a5f5);color:#fff;border:none;border-radius:14px;font-size:11px;font-weight:700;cursor:pointer;">&#9889; Add '+newCount+' New Item(s) to ERP</button>';
            chips += ' <span style="margin-left:auto;font-size:11px;color:#888">'+provLabel+'</span>';
            sbar.innerHTML = chips;
        }
    }
    window.dcsRefreshSummaryBar = dcsRefreshSummaryBar;
    dcsRefreshSummaryBar();
        
        // Analysis note
        function dcsRefreshAnalysisNote() {
        var rows = window._dcsRows || [];
        var newCount = 0, errCount = 0;
        rows.forEach(function(r) {
            newCount += (r._status === 'new_item') ? 1 : 0;
            if (r.sell > 0 && r.sell < r.cost) errCount++;
        });
        var errMsg = window._dcsErrMsg || '';
        var arev = document.getElementById('dcs-arev');
        if (arev) {
            if (errMsg) {
                arev.style.display = 'block';
                arev.innerHTML = '<b>Analysis:</b> ' + errMsg + (rows.length > 0 ? ' ' + rows.length + ' item(s) processed via rule-based fallback.' : '');
            } else {
                arev.style.display = 'block';
                var newItems = rows.length - errCount;
                var msg = '';
                if (newCount > 0) msg += newCount + ' new item(s) not in ERP — click the <b>⚡ Add to ERP</b> button above to create them first.';
                if (errCount > 0) msg += (msg ? ' ' : '') + errCount + ' item(s) have issues (e.g. selling below cost) - fix before importing.';
                if (!msg) msg = rows.length + ' item(s) ready to add.';
                arev.innerHTML = '<b>Analysis:</b> ' + msg;
            }
        }
    }
    window.dcsRefreshAnalysisNote = dcsRefreshAnalysisNote;
    dcsRefreshAnalysisNote();
        
        // Show import button
        var importBtn = document.getElementById('dcs-import-btn');
        if (importBtn) importBtn.style.display = '';
        
        // Toggle all header
        var toggleAll = document.getElementById('dcs-toggle-all');
        if (toggleAll) toggleAll.checked = errCount < total;
    }
    window.dcsUpdateMargin = function dcsUpdateMargin(rowIdx) {
        var row = window._dcsRows && window._dcsRows[rowIdx];
        if (!row) return;
        var cell = document.getElementById('dcs-margin-' + rowIdx);
        if (!cell) return;
        var margin = (row.cost > 0 && row.sell > 0) ? (((row.sell-row.cost)/row.sell)*100).toFixed(1)+'%' : '-';
        var colour = (row.sell > 0 && row.sell < row.cost) ? 'color:#c0392b' : (parseFloat(margin) > 20 ? 'color:#1a7a3f' : 'color:#856404');
        cell.style.cssText = 'font-weight:700;' + colour;
        cell.textContent = margin;
    }
        // Global helpers for onclick/closure access
    console.log("DCSINIT_RUNNING: dcsProcess_defined=" + (typeof dcsProcess));
    window.dcsParse = dcsParse;
    window.dcsGuess = dcsGuess;
    window.dcsSim = dcsSim;
    window.dcsCallAIWithFallback = dcsCallAIWithFallback;
    // Expose all global functions to window for onclick handlers
    window.dcsLiveCalc = dcsLiveCalc;
    window.dcsRunAnalysis = dcsRunAnalysis;
    window.dcsOpenModal = dcsOpenModal;
    window.dcsHandleFile = dcsHandleFile;
    window.dcsShowAI = dcsShowAI;
    window.dcsSaveAI = dcsSaveAI;
    window.dcsTestAI = dcsTestAI;
    window._dcsRows = window._dcsRows || [];
}
function dcsLiveCalc(frm, applyToDoc) {
    // Calculate commercial totals from current items (live, before save)
    if (!frm || !frm.doc || !frm.doc.items) return;
    
    // Group items by item_group category
    var cats = {};
    (frm.doc.items || []).forEach(function(item) {
        var qty = parseFloat(item.qty) || 1;
        var cost = (parseFloat(item.cost_rate) || 0) * qty;
        var sell = (parseFloat(item.selling_rate) || 0) * qty;
        var grp = item.header || item.item_group || 'Products';
        if (!cats[grp]) cats[grp] = { cost: 0, sell: 0 };
        cats[grp].cost += cost;
        cats[grp].sell += sell;
    });
    
    var totalCost = 0, totalSell = 0;
    var productsCost = 0, productsSell = 0, servicesCost = 0, servicesSell = 0;
    
    for (var grp in cats) {
        var isService = (grp && (grp.toLowerCase().includes('service') || grp.toLowerCase().includes('professional')));
        totalCost += cats[grp].cost;
        totalSell += cats[grp].sell;
        if (isService) { servicesCost += cats[grp].cost; servicesSell += cats[grp].sell; }
        else { productsCost += cats[grp].cost; productsSell += cats[grp].sell; }
    }
    var resourceCost = (frm.doc.resources || []).reduce(function (sum, row) {
        var units = flt(row.no_of_persons) && flt(row.no_of_days) ? flt(row.no_of_persons) * flt(row.no_of_days) : flt(row.hours);
        return sum + units * flt(row.cost_rate);
    }, 0);
    var chargeCost = (frm.doc.addtional_charges || []).reduce(function (sum, row) { return sum + flt(row.amount); }, 0);
    totalCost += resourceCost + chargeCost;
    if (resourceCost) { cats['Labour / Resources'] = {cost:resourceCost, sell:0}; }
    if (chargeCost) { cats['Additional Charges'] = {cost:chargeCost, sell:0}; }
    
    var marginVal = totalSell - totalCost;
    var marginPct = totalSell > 0 ? (marginVal / totalSell * 100) : 0;
    
    // Commercial totals derived from the current item rows.
    // These are LOCAL display values. They are written back to the document ONLY on an
    var _calcFields = {
        products_cost_total: productsCost, products_selling_total: productsSell,
        services_cost_total: servicesCost, services_selling_total: servicesSell,
        total_resource_cost: resourceCost,
        total_cost: totalCost, total_selling: totalSell,
        margin_value: marginVal, margin_percent: parseFloat(marginPct.toFixed(3))
    };
    // explicit user edit (applyToDoc). A refresh/display pass never mutates frm.doc.
    if (applyToDoc) {
        Object.keys(_calcFields).forEach(function(f) {
            frm.doc[f] = _calcFields[f];
        });
    }
    var wrapper = frm.fields_dict['commercial_summary_html'] && frm.fields_dict['commercial_summary_html'].wrapper;
    if (wrapper) {
        var rows = '';
        for (var g in cats) {
            var c = cats[g].cost, s = cats[g].sell;
            var m = s - c, mp = s > 0 ? (m / s * 100) : 0;
            rows += '<tr><td>' + g + '</td>' +
                '<td style="text-align:right">' + frappe.format(c, {fieldtype:'Currency'}) + '</td>' +
                '<td style="text-align:right">' + frappe.format(s, {fieldtype:'Currency'}) + '</td>' +
                '<td style="text-align:right">' + frappe.format(m, {fieldtype:'Currency'}) + '</td>' +
                '<td style="text-align:right">' + mp.toFixed(2) + '%</td></tr>';
        }
        // Living commercial position - same source as the Living DCS headline.
        // The table below remains the item cost build-up and is labelled as such,
        // so base-sheet totals are never presented as a competing commercial truth.
        var _lvRev = cint(frm.doc.custom_dcs_revision_no);
        var _lvSell = flt(frm.doc.custom_working_total_selling);
        var _lvCost = flt(frm.doc.custom_working_total_cost);
        var _lvMpc = flt(frm.doc.custom_working_margin_percent);
        var _lvCur = frm.doc.currency || 'AED';
        var _lvHead = '';
        if (_lvRev > 0) {
            _lvHead = '<div style="margin:0 0 10px;padding:8px 10px;background:#f0f6ff;border-left:3px solid #1f6fd0;border-radius:4px;font-size:12px">' +
                '<div style="color:#555;margin-bottom:2px">Living commercial position &middot; revision ' + _lvRev + '</div>' +
                '<div style="font-weight:600">Selling ' + format_currency(_lvSell, _lvCur,dcs_money_precision(frm)) +
                ' &nbsp;&middot;&nbsp; Cost ' + format_currency(_lvCost, _lvCur,dcs_money_precision(frm)) +
                ' &nbsp;&middot;&nbsp; Margin ' + _lvMpc.toFixed(3) + '%</div>' +
                '<div style="color:#777;margin-top:3px">Figures below include items, labour and additional charges. Earlier totals-only adjustments may differ until reconciled to a BOQ revision.</div>' +
                '</div>';
        }
        wrapper.innerHTML = '<div style="margin:8px 0">' +
            '<h6 style="font-weight:600;margin-bottom:8px">Commercial Summary</h6>' +
            _lvHead +
            '<table class="table table-bordered table-sm" style="font-size:13px">' +
            '<thead style="background:#f5f5f5"><tr>' +
            '<th>Category</th><th style="text-align:right">Cost</th>' +
            '<th style="text-align:right">Selling (AED)</th>' +
            '<th style="text-align:right">Margin (AED)</th>' +
            '<th style="text-align:right">Margin %</th></tr></thead>' +
            '<tbody>' + rows +
            '<tr style="font-weight:bold;background:#f5f5f5">' +
            '<td>' + (_lvRev > 0 ? 'Total (cost build-up)' : 'Total') + '</td>' +
            '<td style="text-align:right">' + frappe.format(totalCost, {fieldtype:'Currency'}) + '</td>' +
            '<td style="text-align:right">' + frappe.format(totalSell, {fieldtype:'Currency'}) + '</td>' +
            '<td style="text-align:right">' + frappe.format(marginVal, {fieldtype:'Currency'}) + '</td>' +
            '<td style="text-align:right">' + marginPct.toFixed(2) + '%</td>' +
            '</tr></tbody></table></div>';
    }
}

function dcsOpenModal() {
    if (document.getElementById('dcs-modal-overlay')) return;
    var ov = document.createElement('div');
    ov.id = 'dcs-modal-overlay';
    ov.innerHTML = '<div id="dcs-bulk-modal">' +
        '<div class="dcs-mhdr">' +
            '<div><h3>&#9889; Quick Add Items</h3><div style="font-size:11px;opacity:.85;margin-top:2px;">Paste, upload or type items &mdash; AI analyses each one</div></div>' +
            '<div style="display:flex;align-items:center;gap:8px;">' +
            '<button class="dcs-aira-help-btn" onclick="dcsToggleHelp()">&#129302; AIRA Help</button>' +
            '<button class="dcs-mclose" onclick="document.getElementById(\'dcs-modal-overlay\').remove()">&times;</button>' +
        '</div>' +
        '</div>' +
        '<div class="dcs-tabs">' +
            '<div class="dcs-tab active" onclick="dcsTab(\'paste\')">Paste from Excel</div>' +
            '<div class="dcs-tab" onclick="dcsTab(\'upload\')">Upload CSV</div>' +
            '<div class="dcs-tab" onclick="dcsTab(\'type\')">Quick Type</div>' +
            '<div class="dcs-tab" onclick="dcsTab(\'guide\')">Format Guide</div>' +
        '</div>' +
        '<div id="dcs-tp-paste" class="dcs-tpane active">' +
            '<p style="font-size:12px;color:#666;margin:0 0 8px;">Copy rows from Excel/Google Sheets. Columns: <b>Item Name | Qty | Cost | Selling | Header (optional)</b></p>' +
            '<textarea id="dcs-paste-area" class="dcs-ta" placeholder="Microsoft 365 Business Standard&#9;10&#9;150&#9;200"></textarea>' +
            '<div style="margin-top:10px;display:flex;gap:8px;align-items:center;">' +
                '<button class="dcs-btn dcs-bp" onclick="dcsAnalyse()">Analyse &amp; Preview</button>' +
                '<button class="dcs-btn dcs-bn" onclick="document.getElementById(\'dcs-paste-area\').value=\'\'">Clear</button>' +
                '<span style="font-size:11px;color:#999;">Tab-separated or one item per line</span>' +
            '</div>' +
        '</div>' +
        '<div id="dcs-tp-upload" class="dcs-tpane">' +
            '<div class="dcs-upzone" onclick="document.getElementById(\'dcs-file-input\').click()">' +
                '<div style="font-size:36px;">&#128194;</div>' +
                '<div style="font-size:14px;font-weight:600;margin-top:8px;">Click to upload CSV file</div>' +
                '<div style="font-size:12px;color:#aaa;margin-top:4px;">CSV or TXT &#8212; Columns: Item Name, Qty, Cost, Selling, Header (optional)</div>' +
            '</div>' +
            '<input type="file" id="dcs-file-input" style="display:none" accept=".csv,.txt" onchange="dcsHandleFile(event)">' +
            '<div style="margin-top:12px;display:flex;gap:8px;align-items:center;flex-wrap:wrap;">' +
                '<button class="dcs-btn dcs-bp" style="font-size:12px;padding:6px 14px;" onclick="dcsDownloadTemplate(\'csv\')">&#11015; Download CSV Template</button>' +
                '<button class="dcs-btn dcs-bn" style="font-size:12px;padding:6px 14px;" onclick="dcsDownloadTemplate(\'tsv\')">&#11015; Open in Excel Template</button>' +
                '<span style="font-size:11px;color:#999;">Sample file — fill &amp; upload</span>' +
            '</div>' +
        '</div>' +
        '<div id="dcs-tp-type" class="dcs-tpane">' +
            '<p style="font-size:12px;color:#666;margin:0 0 8px;">Type items one per line. Just the name is fine - fill qty/cost/selling in the preview.</p>' +
            '<textarea id="dcs-type-area" class="dcs-ta" placeholder="Cisco Catalyst 9200 Switch&#10;Fortinet FortiGate 100F&#10;Annual Support Contract"></textarea>' +
            '<div style="margin-top:10px;"><button class="dcs-btn dcs-bp" onclick="dcsAnalyseType()">Analyse &amp; Preview</button></div>' +
        '</div>' +
        '<div id="dcs-tp-guide" class="dcs-tpane">' +
            '<div style="background:#f8f9ff;border-radius:8px;padding:16px;font-size:13px;">' +
                '<b>Accepted Formats</b><br><br>' +
                '<table style="width:100%;border-collapse:collapse;font-size:12px;">' +
                    '<tr style="background:#e8eaff;"><th style="padding:6px;border:1px solid #ddd;">Format</th><th style="padding:6px;border:1px solid #ddd;">Example</th></tr>' +
                    '<tr><td style="padding:6px;border:1px solid #ddd;">Name only</td><td style="padding:6px;border:1px solid #ddd;font-family:monospace;">Microsoft 365 Business Standard</td></tr>' +
                    '<tr><td style="padding:6px;border:1px solid #ddd;">Name+Qty+Cost+Selling</td><td style="padding:6px;border:1px solid #ddd;font-family:monospace;">Item Name [TAB] 5 [TAB] 1200 [TAB] 1500</td></tr>' +
                '</table>' +
                '<p style="margin-top:10px;font-size:12px;color:#666;">Blank rows auto-skipped. New items auto-created. AI analyses each row. Edit values before importing.</p>' +
            '</div>' +
        '</div>' +
        '<div id="dcs-preview-area" style="display:none;">' +
            '<div class="dcs-sbar" id="dcs-sbar"></div>' +
            '<div id="dcs-arev" class="dcs-arev" style="display:none;"></div>' +
            '<div class="dcs-pwrap" style="overflow-x:auto;">' +
                '<table class="dcs-pt"><thead><tr>' +
                    '<th width="28"><input type="checkbox" id="dcs-sel-all" onchange="dcsToggleAll(this.checked)"></th>' +
                    '<th>#</th><th>Status</th><th style="min-width:160px">Item Name</th>' +
                    '<th>Qty</th><th>Cost</th><th>Selling</th><th>Margin%</th><th>Item Group</th><th>AI Notes</th>' +
                '</tr></thead><tbody id="dcs-tbody"></tbody></table>' +
            '</div>' +
        '</div>' +
        '<div class="dcs-foot">' +
            '<div id="dcs-foot-l" style="font-size:12px;color:#888;">Paste or type items above, then click Analyse &amp; Preview</div>' +
            '<div>' +
                '<button class="dcs-btn dcs-bn" onclick="document.getElementById(\'dcs-modal-overlay\').remove()">Cancel</button>' +
                '<button id="dcs-import-btn" class="dcs-btn dcs-bs" style="display:none" onclick="dcsDoImport()">Add Selected to Deal</button>' +
            '</div>' +
        '</div>' +
    '<div id="dcs-help-panel">' +
        '<button class="dcs-help-close" onclick="dcsToggleHelp()">&times;</button>' +
        '<div class="dcs-help-title">&#129302; AIRA — What AI Does</div>' +
        '<div class="dcs-help-sub">AI-powered item recognition &amp; classification</div>' +
        '<div class="dcs-help-section"><h4>&#128161; The Big Picture</h4><p style="font-size:12px;color:#555;margin:0;">When you paste items from Excel, AIRA automatically understands each item, matches it to your ERP, classifies it, and flags what needs to be created — so your team focuses on selling, not data entry.</p></div>' +
        '<div class="dcs-help-section"><h4>&#128296; Step-by-Step: What AI Does</h4>' +
            '<div class="dcs-help-step"><div class="dcs-step-num">1</div><div><b>Receives your pasted items</b> — item name, qty, cost, selling price extracted automatically. Header rows and serial number columns are auto-skipped.</div></div>' +
            '<div class="dcs-help-step"><div class="dcs-step-num">2</div><div><b>Matches against ERP Item Master</b> — compares each pasted name against your live ERP items.<br><span class="dcs-help-badge dcs-badge-green">Existing Item</span> found in ERP &nbsp;<span class="dcs-help-badge dcs-badge-orange">New Item</span> not found — will be auto-created</div></div>' +
            '<div class="dcs-help-step"><div class="dcs-step-num">3</div><div><b>Auto-classifies Item Group</b><br><span class="dcs-help-badge dcs-badge-blue">Products</span> hardware, devices, physical goods<br><span class="dcs-help-badge dcs-badge-blue">Services</span> subscriptions, support, SLA, renewals<br><span class="dcs-help-badge dcs-badge-blue">Professional Services</span> installation, consulting, training</div></div>' +
            '<div class="dcs-help-step"><div class="dcs-step-num">4</div><div><b>Cleans item names</b> — normalizes spacing, casing, and common abbreviations from raw Excel data.</div></div>' +
            '<div class="dcs-help-step"><div class="dcs-step-num">5</div><div><b>Adds AI Notes</b> — short explanation per row: why it was classified, whether it was matched or created.</div></div>' +
        '</div>' +
        '<div class="dcs-help-section"><h4>&#128683; What AI Does NOT Do</h4>' +
            '<table class="dcs-help-table"><tr><th>Action</th><th>Who Does It</th></tr>' +
            '<tr><td>Add items to deal</td><td>You — click <b>Add Selected to Deal</b></td></tr>' +
            '<tr><td>Create items in ERP</td><td>Auto — on Add Selected</td></tr>' +
            '<tr><td>Modify prices</td><td>You — prices from your paste</td></tr>' +
            '<tr><td>Save the DCS</td><td>You — click Save on form</td></tr>' +
            '</table></div>' +
        '<div class="dcs-help-section"><h4>&#9881;&#65039; Fallback: Rule-Based Mode</h4><p style="font-size:12px;color:#555;margin:0 0 6px;">If the AI server is unavailable, the system uses keyword rules:</p>' +
            '<table class="dcs-help-table"><tr><th>Keyword in Name</th><th>Classified As</th></tr>' +
            '<tr><td>support, maintenance, sla, warranty, subscription, annual</td><td>Services</td></tr>' +
            '<tr><td>install, implement, deploy, consult, train, migration</td><td>Professional Services</td></tr>' +
            '<tr><td>license, licensing, renewal, assurance</td><td>Services</td></tr>' +
            '<tr><td>everything else</td><td>Products</td></tr>' +
            '</table>' +
            '<div class="dcs-help-note">&#128276; When rule-based is active, the preview shows <b>Rule-based analysis</b> in the top-right corner.</div>' +
        '</div>' +
        '<div class="dcs-help-section"><h4>&#128203; Paste Format Tips</h4>' +
            '<table class="dcs-help-table"><tr><th>Format</th><th>Example</th></tr>' +
            '<tr><td>Name only</td><td style="font-family:monospace;">Microsoft 365 Business Standard</td></tr>' +
            '<tr><td>With prices</td><td style="font-family:monospace;">Item Name [TAB] Qty [TAB] Cost [TAB] Selling</td></tr>' +
            '<tr><td>Excel with serial col</td><td style="font-family:monospace;">1 [TAB] Item Name [TAB] 1 [TAB] 100 [TAB] 150</td></tr>' +
            '</table>' +
            '<div class="dcs-help-note">&#9989; Header rows (Sl No, Description, #) are auto-detected and skipped.</div>' +
        '</div>' +
    '</div>' +
    '</div>';
    document.body.appendChild(ov);
}
function dcsToggleHelp() {
    var p = document.getElementById('dcs-help-panel');
    if (p) p.classList.toggle('open');
}

function dcsTab(t) {
    var names = ['paste','upload','type','guide'];
    document.querySelectorAll('.dcs-tab').forEach(function(el, i) { el.classList.toggle('active', names[i] === t); });
    names.forEach(function(n) { var p = document.getElementById('dcs-tp-' + n); if (p) p.classList.toggle('active', n === t); });
}

function dcsHandleFile(evt) {
  var f = evt.target.files[0]; if (!f) return;
  var fname = (f.name || '').toLowerCase();
  if (fname.endsWith('.xlsx') || fname.endsWith('.xls') || fname.endsWith('.xlsm')) {
    frappe.msgprint({
      title: 'Excel file not supported here',
      indicator: 'orange',
      message: 'This upload box only reads plain CSV/TXT files, not binary Excel files (.xlsx/.xls). Please either:<br>1) Open the file in Excel and use <b>File &rarr; Save As &rarr; CSV (Comma delimited)</b>, then upload the CSV, or<br>2) Copy the rows directly from Excel and paste them into the <b>Paste from Excel</b> tab instead (no file needed).'
    });
    evt.target.value = '';
    return;
  }
  var rd = new FileReader();
  rd.onload = function(e) {
    var text = e.target.result;
    if (/^PK/.test(text) || /\u0000/.test(text.slice(0, 200))) {
      frappe.msgprint({
        title: 'Could not read file',
        indicator: 'red',
        message: 'This file appears to be a binary Excel file rather than CSV/TXT. Please save it as CSV from Excel and try again, or use the Paste from Excel tab.'
      });
      evt.target.value = '';
      return;
    }
    dcsRunAnalysis(dcsParse(text));
  };
  rd.onerror = function() {
    frappe.msgprint({ title: 'Upload failed', indicator: 'red', message: 'Could not read the selected file. Please try again or use the Paste from Excel tab.' });
  };
  rd.readAsText(f);
}

function dcsDownloadTemplate(fmt) {
    var templateRows = [
        ["Item Name","Qty","Cost Price","Selling Price","Section Header (optional)"],
        ["Cisco Catalyst 9200L 24-Port Switch","2","4800","6200",""],
        ["Fortinet FortiGate 100F Firewall","1","8500","11000","Network Security"],
        ["Structured Cabling - Cat6A per point","24","150","220","Cabling Works"],
        ["Microsoft 365 Business Standard (Annual)","10","900","1200",""],
        ["Annual Maintenance Contract","1","5000","7500","Services"]
    ];
    var sep = (fmt === "tsv") ? "\t" : ",";
    function esc(v) {
        if (fmt !== "tsv" && (v.indexOf(",") >= 0 || v.indexOf("\"") >= 0)) {
            return "\"" + v.replace(/"/g, "\"\"") + "\"";
        }
        return v;
    }
    var content = templateRows.map(function(row) { return row.map(esc).join(sep); }).join("\n");
    var bom = "\uFEFF";
    var blob = new Blob([bom + content], { type: "text/csv;charset=utf-8;" });
    var url = URL.createObjectURL(blob);
    var a = document.createElement("a");
    a.href = url;
    a.download = (fmt === "tsv") ? "DCS_Template_Excel.csv" : "DCS_Template.csv";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    frappe.show_alert({ message: "\u2705 Template downloaded. Open in Excel, fill your items, save as CSV, then upload.", indicator: "green" }, 6);
}


function dcsAutoCreateItems() {
    // Pre-create all new items in ERP so badges update before import
    if (!window._dcsRows || !window._dcsRows.length) { return; }
    var newRows = window._dcsRows.filter(function(r) { return r._status === 'new_item'; });
    if (!newRows.length) {
        frappe.show_alert({message: '✅ All items already exist in ERP', indicator: 'green'}, 3);
        return;
    }
    var btn = document.getElementById('dcs-autocreate-btn');
    if (btn) { btn.disabled = true; btn.textContent = '⏳ Creating... 0/' + newRows.length; }
    var created = 0, failed = [];
    var total = newRows.length;
    function onDone() {
        window._dcsRows.forEach(function(row, i) {
            if (row._justCreated) {
                row._status = 'existing';
                row._justCreated = false;
                var tr = document.getElementById('dcs-row-' + i);
                if (tr) {
            tr.className = row._genericFallback ? 'row-warn' : 'row-ready';
            var badge = tr.querySelector('.dcs-badge');
            if (badge) {
              if (row._genericFallback) { badge.className = 'dcs-badge b-w'; badge.textContent = 'Generic (Review)'; }
              else { badge.className = 'dcs-badge b-r'; badge.textContent = 'Existing Item'; }
            }
          }
            }
        });
        if (btn) {
            if (failed.length === 0) {
          btn.style.background = 'linear-gradient(135deg,#1a7a3f,#56ab2f)';
          btn.textContent = '✅ ' + created + ' Item(s) Created in ERP';
          btn.disabled = true;
        } else {
          btn.style.background = 'linear-gradient(135deg,#e6a817,#f5c518)';
          btn.textContent = '⚠️ ' + created + ' Item(s) Ready (' + failed.length + ' used Generic placeholder)';
          btn.disabled = true;
        }
        }
        var arev = document.getElementById('dcs-arev');
        if (arev) {
            var msg2 = '';
            if (created - failed.length > 0) msg2 += (created - failed.length) + ' new item(s) created in ERP. ';
            if (failed.length > 0) msg2 += failed.length + ' failed: ' + failed.slice(0,2).join(', ') + (failed.length > 2 ? '...' : '') + '. ';
            msg2 += 'Click <b>Add Selected to Deal</b> to import.';
            arev.innerHTML = '<b>Status:</b> ' + msg2;
        }
        if (failed.length > 0) {
        frappe.msgprint({
          title: 'Some items used the Generic placeholder',
          indicator: 'orange',
          message: 'The following item(s) could not be created or matched in the ERP Item Master (e.g. invalid Item Group, duplicate/blocked name, or missing permission) and were mapped to the <b>Generic</b> placeholder item instead of failing:<br><br>' + failed.map(function(n){ return frappe.utils.escape_html(n); }).join('<br>') + '<br><br>You can still click <b>Add Selected to Deal</b> - please review and correct the Item Code on these rows afterwards if you need a specific catalogue item.'
        });
        frappe.show_alert({message: '⚠️ ' + failed.length + ' item(s) used the Generic placeholder - review before finalizing.', indicator: 'orange'}, 8);
      } else {
        frappe.show_alert({message: '✅ ' + created + ' item(s) created in ERP — now click Add Selected to Deal!', indicator: 'green'}, 5);
      }
    }
    newRows.forEach(function(row) {
        var safeCode = (row.item_code && row.item_code !== row.name) ? row.item_code.substring(0, 140) : (row.name.length > 140 ? row.name.substring(0, 137) + '...' : row.name);
            var safeName = row.name.length > 140 ? row.name.substring(0, 137) + '...' : row.name;
        var itemGroup = row.item_group || 'Products';
        frappe.call({
            method: 'frappe.client.insert',
            args: { doc: { doctype: 'Item', item_code: safeCode, item_name: safeName, item_group: itemGroup, is_sales_item: 1, is_purchase_item: 1, stock_uom: 'Nos', description: row.name } },
            callback: function(r) {
                if (r && r.message) { row.item_code = r.message.name; row._justCreated = true; }
                created++;
                if (btn) btn.textContent = '⏳ Creating... ' + created + '/' + total;
                if (created >= total) onDone();
            },
            error: function() {
        frappe.db.get_value('Item', {item_code: safeCode}, 'name', function(res) {
          if (res && res.name) {
            row.item_code = res.name; row._justCreated = true;
          } else {
            // Could not create or find this item in ERP - fall back to the Generic
            // placeholder item so the deal can still be saved, flagged for review.
            row.item_code = dcsGenericFallback(itemGroup);
            row._justCreated = true;
            row._genericFallback = true;
            failed.push(row.name);
          }
          created++;
          if (btn) btn.textContent = '⏳ Creating... ' + created + '/' + total;
          if (created >= total) onDone();
        });
      }
        });
    });
}

function dcsNum(v, def) {
    if (v === undefined || v === null || v === '') return def;
    var n = parseFloat(String(v).replace(/[^0-9.\-]/g, ''));
    return isNaN(n) ? def : n;
}

function dcsParse(raw) {
    var rows = [], idx = 0;
    var lines = raw.split('\n');
    // Auto-detect if first column is a serial number or header label
    var hasSerialCol = false;
    for (var li = 0; li < lines.length; li++) {
        var l = lines[li].trim();
        if (!l) continue;
        var parts0 = l.indexOf('\t') >= 0 ? l.split('\t') : (l.indexOf(',') >= 0 ? dcsSplitCSVLine(l) : [l]);
        parts0 = parts0.map(function(p){ return p.trim(); });
        var firstVal = parts0[0];
        // If first cell is a text header label (Sl No, Description, #, etc.) -> has serial col, skip this row
        if (/^(sl[\s.]*no|s\.?no|no\.|sr\.?|#|item\s*no|sn|description|item\s*name|item)$/i.test(firstVal)) {
            hasSerialCol = true;
            continue;
        }
        // If first cell is purely numeric -> has serial col
        if (/^\d+$/.test(firstVal)) { hasSerialCol = true; }
        break;
    }
    lines.forEach(function(line) {
        line = line.trim(); if (!line) return;
        var parts;
        if (line.indexOf('\t') >= 0) parts = line.split('\t').map(function(p) { return p.trim(); });
        else if (line.indexOf(',') >= 0) parts = dcsSplitCSVLine(line);
        else parts = [line];
        var firstCell = parts[0] || '';
        // Skip header rows where first cell is a column label
        if (/^(sl[\s.]*no|s\.?no|no\.|sr\.?|#|item\s*no|sn|description|item\s*name|item|qty|cost|selling|buying|price|rate)$/i.test(firstCell)) return;
        var name, qty, cost, sell, header, itemCode;
        if (hasSerialCol && /^\d+$/.test(firstCell)) {
            // col0=serial, col1=name, col2=qty, col3=cost, col4=selling, col5=header
            name   = parts[1] || ''; if (!name) return;
            qty    = dcsNum(parts[2], 1);
            cost   = dcsNum(parts[3], 0);
            sell   = dcsNum(parts[4], 0);
            header = parts[5] || '';
        } else if (parts.length >= 5 && !/\s/.test(firstCell) && !/^[\d.,$-]+$/.test(firstCell) && /\s/.test(parts[1]||'')) {
            // col0=itemCode, col1=name, col2=qty, col3=cost, col4=selling, col5=header (optional)
            itemCode = firstCell;
            name   = parts[1] || ''; if (!name) return;
            qty    = dcsNum(parts[2], 1);
            cost   = dcsNum(parts[3], 0);
            sell   = dcsNum(parts[4], 0);
            header = parts[5] || '';
        } else {
            // Standard format: col0=name, col1=qty, col2=cost, col3=selling, col4=header
            name   = firstCell; if (!name) return;
            qty    = dcsNum(parts[1], 1);
            cost   = dcsNum(parts[2], 0);
            sell   = dcsNum(parts[3], 0);
            header = parts[4] || '';
        }
        idx++;
        rows.push({ idx: idx, name: name, qty: qty, cost: cost, sell: sell, header: header, itemCode: itemCode || '' });
    });
    return rows;
}

function dcsAnalyse() {
    var t = document.getElementById('dcs-paste-area').value;
    if (!t.trim()) { frappe.msgprint('Please paste some items first.'); return; }
    window.dcsRunAnalysis(window.dcsParse(t));
}

function dcsAnalyseType() {
    var t = document.getElementById('dcs-type-area').value;
    if (!t.trim()) { frappe.msgprint('Please type some items first.'); return; }
    window.dcsRunAnalysis(window.dcsParse(t));
}

function dcsGuess(name) {
    var n = name.toLowerCase();
    if (/support|maintenance|sla|warranty|subscription|annual|yearly|monthly/.test(n)) return 'Services';
    if (/install|implement|deploy|config|consult|train|migration|project|professional/.test(n)) return 'Professional Services';
    if (/license|licensing|renewal|assurance/.test(n)) return 'Services';
  return 'Products';
}

function dcsGenericFallback(itemGroup) {
  // Safe, always-exists placeholder Item used when an item cannot be auto-created
  // or matched in the ERP Item Master, so the Deal Cost Sheet can still be saved
  // instead of failing with a broken/non-existent Item Code link.
  var g = (itemGroup || '').toLowerCase();
  return (g.indexOf('service') >= 0) ? 'Generic Service' : 'Generic';
}
window.dcsGenericFallback = dcsGenericFallback;

function dcsUseGeneric(i) {
    // Lets the user proactively pick the safe Generic placeholder for a New Item
    // row instead of waiting for an ERP creation attempt to fail first.
    if (!window._dcsRows || !window._dcsRows[i]) return;
    var row = window._dcsRows[i];
    if (row._status !== 'new_item') return;
    row.item_code = dcsGenericFallback(row.item_group);
    row._genericFallback = true;
    row._justCreated = false;
    row._status = 'existing';
    var tr = document.getElementById('dcs-row-' + i);
    if (tr) {
        tr.className = 'row-warn';
        var badge = tr.querySelector('.dcs-badge');
        if (badge) { badge.className = 'dcs-badge b-w'; badge.textContent = 'Generic (Review)'; }
        var useGenLink = tr.querySelector('a[onclick*="dcsUseGeneric"]');
        if (useGenLink) { useGenLink.remove(); }
    }
    if (window.dcsRefreshSummaryBar) window.dcsRefreshSummaryBar();
    if (window.dcsRefreshAnalysisNote) window.dcsRefreshAnalysisNote();
}
window.dcsUseGeneric = dcsUseGeneric;

function dcsSplitCSVLine(line) {
  // Proper CSV splitter that respects quoted fields containing commas, e.g.
  // "Router, 24-port",5,100,150 must keep "Router, 24-port" as one field.
  var result = [];
  var cur = '';
  var inQuotes = false;
  for (var i = 0; i < line.length; i++) {
    var ch = line[i];
    if (ch === '"') {
      if (inQuotes && line[i+1] === '"') { cur += '"'; i++; }
      else { inQuotes = !inQuotes; }
    } else if (ch === ',' && !inQuotes) {
      result.push(cur); cur = '';
    } else {
      cur += ch;
    }
  }
  result.push(cur);
  return result.map(function(p) { return p.trim(); });
}

function dcsSim(a, b) {
    var aW = a.toLowerCase().split(/\s+/), bW = b.toLowerCase().split(/\s+/);
    var ov = aW.filter(function(w) { return w.length > 2 && bW.indexOf(w) >= 0; });
    return ov.length / Math.max(aW.length, bW.length);
}

function dcsRunAnalysis(rows) {
    if (!rows.length) { frappe.msgprint('No items found.'); return; }
    var pa = document.getElementById('dcs-preview-area');
    pa.style.display = 'block';
    document.getElementById('dcs-tbody').innerHTML = '<tr><td colspan="9" class="dcs-load"><span class="dcs-spin"></span>Analysing ' + rows.length + ' item(s)...</td></tr>';
    document.getElementById('dcs-sbar').innerHTML = '';
    document.getElementById('dcs-arev').style.display = 'none';
    document.getElementById('dcs-import-btn').style.display = 'none';

    frappe.call({
        method: 'frappe.client.get_list',
        args: { doctype: 'Item', fields: ['item_code','item_name','item_group'], filters: [['disabled','=',0]], limit_page_length: 20000 },
        callback: function(r) {
            var erp = (r && r.message) ? r.message : [];
            frappe.call({
                method: 'aira_ai_gateway',
                args: {
                    caller: 'dcs_quick_add',
                    system_prompt: 'You are an ERP pricing analyst for an IT reseller. Analyse the items and return a JSON array. For each item return: {"row":<n>,"suggested_sell":<number>,"confidence":"high|medium|low","reason":"<short>"}. Return ONLY valid JSON array, no markdown.',
                    user_message: JSON.stringify(rows),
                    max_tokens: 1500
                },
                callback: function(ar) {
                    const cfg = (ar && ar.message && ar.message.success) ? ar.message : null;
                    if (!cfg) {
                        dcsProcess(rows, erp, null, null, (ar && ar.message && ar.message.error) || 'AI configuration error');
                        return;
                    }
                    dcsCallAIWithFallback(cfg, rows, erp);
                },
                error: function() { dcsProcess(rows, erp, null, null, 'Gateway unreachable'); }
            });
        }
    });
}


function dcsCallAIWithFallback(res, rows, erp) {
    // AIRA Gateway v4.0 - completion is produced server-side.
    // No API key, provider endpoint or browser fetch to an AI provider is used here.
    if (!res || !res.text) {
        dcsProcess(rows, erp, null, null, (res && res.error) || 'AI returned no response');
        return;
    }
    dcsProcess(rows, erp, res.text, res.provider_used || res.provider || 'AI');
}


// BEGIN DCSPROCESS ASSIGN


function dcsOpenAISettings() {
    if (document.getElementById('dcs-ai-dialog')) return;
    frappe.call({
        method: 'frappe.client.get_value',
        args: {
            doctype: 'AI Provider Settings',
            filters: { name: 'AI Provider Settings' },
            fieldname: ['ai_provider','is_enabled','ai_model','max_tokens','fallback_to_rules',
                        'fallback_provider','fallback_model','gateway_status','active_provider_display','last_used']
        },
        callback: function(r) { dcsShowAI((r && r.message) ? r.message : {}); },
        error: function() { dcsShowAI({}); }
    });
}

function dcsShowAI(cfg) {
    const providers = ['Anthropic (Claude)', 'OpenAI (GPT)', 'Azure OpenAI', 'Google Gemini', 'Ollama (Local)'];
    const fbProviders = ['', 'OpenAI (ChatGPT)'];
    const isEnabled = cfg.is_enabled ? 1 : 0;

    // Status indicator colour
    const gwStatus   = cfg.gateway_status || 'Not yet used';
    const activeProv = cfg.active_provider_display || '';
    let statusColour = '#888';
    if (activeProv.includes('Anthropic'))          statusColour = '#7c3aed';
    if (activeProv.includes('OpenAI'))             statusColour = '#10a37f';
    if (gwStatus.startsWith('Fallback:'))          statusColour = '#f59e0b';
    if (!activeProv && !gwStatus.startsWith('A'))  statusColour = '#888';

    const html = `<div id="dcs-ai-dialog" style="font-family:sans-serif;padding:0">
        <!-- Status Banner -->
        <div style="background:${statusColour};color:#fff;border-radius:6px;padding:8px 14px;margin-bottom:14px;display:flex;align-items:center;gap:10px">
            <span style="font-size:18px">${gwStatus.startsWith('Fallback:') ? '🟠' : activeProv.includes('Anthropic') ? '🟣' : activeProv.includes('OpenAI') ? '🟢' : '⚪'}</span>
            <div>
                <div style="font-weight:700;font-size:13px">Gateway Status</div>
                <div style="font-size:12px;opacity:0.9">${gwStatus}</div>
            </div>
        </div>

        <!-- Primary Provider -->
        <div style="margin-bottom:12px">
            <label style="font-size:11px;font-weight:600;color:#555;text-transform:uppercase;letter-spacing:.5px">Primary AI Provider</label>
            <select id="dcs-ai-provider" style="width:100%;padding:7px 10px;border:1px solid #d1d5db;border-radius:5px;margin-top:4px;font-size:13px">
                ${providers.map(p => `<option value="${p}" ${p===cfg.ai_provider?'selected':''}>${p}</option>`).join('')}
            </select>
        </div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:12px">
            <div>
                <label style="font-size:11px;font-weight:600;color:#555;text-transform:uppercase;letter-spacing:.5px">Model Name</label>
                <input id="dcs-ai-model" type="text" value="${cfg.ai_model||''}" placeholder="e.g. claude-sonnet-4-5-20251022"
                    style="width:100%;padding:7px 10px;border:1px solid #d1d5db;border-radius:5px;margin-top:4px;font-size:13px;box-sizing:border-box"/>
            </div>
            <div>
                <label style="font-size:11px;font-weight:600;color:#555;text-transform:uppercase;letter-spacing:.5px">Max Tokens</label>
                <input id="dcs-ai-tokens" type="number" value="${cfg.max_tokens||2000}" min="500" max="8000"
                    style="width:100%;padding:7px 10px;border:1px solid #d1d5db;border-radius:5px;margin-top:4px;font-size:13px;box-sizing:border-box"/>
            </div>
        </div>
        <div style="margin-bottom:12px">
            <label style="font-size:11px;font-weight:600;color:#555;text-transform:uppercase;letter-spacing:.5px">API Key (Primary)</label>
            <input id="dcs-ai-key" type="password" placeholder="sk-ant-api03-...  or sk-...  (leave blank to keep current)"
                style="width:100%;padding:7px 10px;border:1px solid #d1d5db;border-radius:5px;margin-top:4px;font-size:13px;box-sizing:border-box"/>
            <div style="font-size:10px;color:#888;margin-top:3px">Stored securely in server DB — enter to update</div>
        </div>
        <div style="margin-bottom:14px;display:flex;align-items:center;gap:8px">
            <input id="dcs-ai-enabled" type="checkbox" ${isEnabled?'checked':''} style="width:16px;height:16px;cursor:pointer"/>
            <label for="dcs-ai-enabled" style="font-size:13px;cursor:pointer">Enable AI Analysis</label>
            <span style="margin-left:12px"><input id="dcs-ai-fallback" type="checkbox" ${cfg.fallback_to_rules?'checked':''} style="width:16px;height:16px;cursor:pointer"/></span>
            <label for="dcs-ai-fallback" style="font-size:13px;cursor:pointer">Fallback to rule-based if AI fails</label>
        </div>

        <!-- ChatGPT Fallback Section -->
        <div style="border-top:1px solid #e5e7eb;padding-top:12px;margin-bottom:12px">
            <div style="font-size:11px;font-weight:700;color:#10a37f;text-transform:uppercase;letter-spacing:.5px;margin-bottom:8px">🔄 ChatGPT Fallback (if primary AI fails)</div>
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-bottom:10px">
                <div>
                    <label style="font-size:11px;font-weight:600;color:#555;text-transform:uppercase;letter-spacing:.5px">Fallback Provider</label>
                    <select id="dcs-fb-provider" style="width:100%;padding:7px 10px;border:1px solid #d1d5db;border-radius:5px;margin-top:4px;font-size:13px">
                        ${fbProviders.map(p => `<option value="${p}" ${p===cfg.fallback_provider?'selected':''}>${p||'— None —'}</option>`).join('')}
                    </select>
                </div>
                <div>
                    <label style="font-size:11px;font-weight:600;color:#555;text-transform:uppercase;letter-spacing:.5px">Fallback Model</label>
                    <input id="dcs-fb-model" type="text" value="${cfg.fallback_model||'gpt-4o-mini'}" placeholder="gpt-4o-mini"
                        style="width:100%;padding:7px 10px;border:1px solid #d1d5db;border-radius:5px;margin-top:4px;font-size:13px;box-sizing:border-box"/>
                </div>
            </div>
            <div>
                <label style="font-size:11px;font-weight:600;color:#555;text-transform:uppercase;letter-spacing:.5px">Fallback API Key (OpenAI)</label>
                <input id="dcs-fb-key" type="password" placeholder="sk-...  (leave blank to keep current)"
                    style="width:100%;padding:7px 10px;border:1px solid #d1d5db;border-radius:5px;margin-top:4px;font-size:13px;box-sizing:border-box"/>
                <div style="font-size:10px;color:#888;margin-top:3px">OpenAI key — only used if primary provider fails</div>
            </div>
        </div>

        <div style="font-size:10px;color:#aaa;text-align:right">Last used: ${cfg.last_used ? cfg.last_used.substring(0,16) : 'Never'}</div>
    </div>`;

    const d = new frappe.ui.Dialog({
        title: '🤖 AI Provider Settings',
        fields: [{ fieldtype: 'HTML', options: html }],
        primary_action_label: '💾 Save Settings',
        primary_action: function(values) { dcsSaveAI(d); },
        secondary_action_label: '🧪 Test Connection',
        secondary_action: function() { dcsTestAI(d); }
    });
    d.show();
}

function dcsSaveAI(d) {
    const provider   = document.getElementById('dcs-ai-provider').value;
    const model      = document.getElementById('dcs-ai-model').value.trim();
    const key        = document.getElementById('dcs-ai-key').value.trim();
    const tokens     = parseInt(document.getElementById('dcs-ai-tokens').value) || 2000;
    const enabled    = document.getElementById('dcs-ai-enabled').checked ? 1 : 0;
    const fallback   = document.getElementById('dcs-ai-fallback').checked ? 1 : 0;
    const fbProvider = document.getElementById('dcs-fb-provider').value;
    const fbModel    = document.getElementById('dcs-fb-model').value.trim();
    const fbKey      = document.getElementById('dcs-fb-key').value.trim();

    if (!model) { frappe.msgprint('Model Name is required'); return; }

    const toSave = {
        ai_provider: provider, ai_model: model, max_tokens: tokens,
        is_enabled: enabled, fallback_to_rules: fallback,
        fallback_provider: fbProvider, fallback_model: fbModel
    };
    if (key)   toSave.api_key = key;
    if (fbKey) toSave.fallback_api_key = fbKey;

    frappe.call({
        method: 'frappe.client.set_value',
        args: { doctype: 'AI Provider Settings', name: 'AI Provider Settings', fieldname: toSave },
        callback: function() {
            frappe.show_alert({ message: '✅ AI Settings saved', indicator: 'green' });
            d.hide();
        }
    });
}

function dcsTestAI(d) {
    const provider = document.getElementById('dcs-ai-provider').value;
    frappe.show_alert({ message: '🧪 Testing connection to ' + provider + '...', indicator: 'blue' });
    frappe.call({
        method: 'aira_ai_gateway',
        args: {
            caller: 'settings_test',
            system_prompt: 'You are a helpful assistant.',
            user_message: 'Reply with exactly: AIRA OK',
            max_tokens: 20
        },
        callback: function(r) {
            const res = r.message || {};
            if (res.success) {
                const provBadge = res.provider_used || provider;
                const colour = provBadge.includes('fallback') ? 'orange' : 'green';
                frappe.show_alert({
                    message: '✅ Connected via ' + provBadge + ' (' + (res.model_used || '') + ')',
                    indicator: colour
                }, 6);
                // Update status banner in dialog
                const statusDiv = document.querySelector('#dcs-ai-dialog div[style*="Gateway Status"]');
                if (statusDiv) {
                    statusDiv.closest('div').style.background = provBadge.includes('OpenAI') ? '#10a37f' : '#7c3aed';
                }
            } else {
                frappe.show_alert({ message: '❌ Failed: ' + (res.error || 'Unknown error'), indicator: 'red' }, 8);
            }
        },
        error: function() {
            frappe.show_alert({ message: '❌ Gateway unreachable', indicator: 'red' }, 6);
        }
    });
}


console.log("SCRIPT_END_MARKER: dcsProcess=" + typeof window.dcsProcess);

function dcsTestAI(dialog) {
    // AIRA Gateway v4.0 - connectivity is tested through the governed server proxy.
    frappe.show_alert({ message: '🔌 Testing AI connectivity via governed gateway...', indicator: 'blue' }, 4);
    frappe.call({
        method: 'aira_ai_gateway',
        args: {
            caller: 'settings_test',
            system_prompt: 'You are a connectivity test assistant.',
            user_message: 'Reply with exactly: AIRA GATEWAY ACTIVE',
            max_tokens: 20
        },
        callback: function(r) {
            const res = (r && r.message) || {};
            if (res.success && res.text) {
                frappe.show_alert({
                    message: '✅ Connected via ' + (res.provider_used || res.provider || 'AI') + ' (' + (res.model_used || res.model || '') + ')',
                    indicator: 'green'
                }, 6);
            } else {
                frappe.show_alert({ message: '❌ Failed: ' + (res.error || 'No response'), indicator: 'red' }, 8);
            }
        },
        error: function() {
            frappe.show_alert({ message: '❌ Gateway unreachable', indicator: 'red' }, 6);
        }
    });
}


// MISSING GLOBAL FUNCTIONS (inline edit handlers for dcsProcess table)
// These are called from onclick/onchange/onblur in dcsProcess HTML
// =====================================================================

function dcsTogRow(i, checked) {
    // Toggle row selection in the preview table
    if (!window._dcsRows) return;
    if (window._dcsRows[i]) {
        window._dcsRows[i].checked = checked;
    }
    // Update the selected count display
    var total = window._dcsRows.length;
    var sel = window._dcsRows.filter(function(r) { return r.checked !== false; }).length;
    var selSpan = document.getElementById('dcs-sel-count');
    if (selSpan) selSpan.textContent = sel + ' of ' + total + ' rows selected';
    // Show/hide import button based on selection
    var importBtn = document.getElementById('dcs-import-btn');
    if (importBtn) importBtn.style.display = sel > 0 ? '' : 'none';
}

function dcsToggleAll(checked) {
    // Toggle all rows in the preview table
    if (!window._dcsRows) return;
    window._dcsRows.forEach(function(r) { r.checked = checked; });
    // Update all row checkboxes
    var checkboxes = document.querySelectorAll('#dcs-bulk-modal [type="checkbox"]:not(#dcs-sel-all)');
    checkboxes.forEach(function(cb) { cb.checked = checked; });
    // Update count
    var total = window._dcsRows.length;
    var sel = checked ? total : 0;
    var selSpan = document.getElementById('dcs-sel-count');
    if (selSpan) selSpan.textContent = sel + ' of ' + total + ' rows selected';
    var importBtn = document.getElementById('dcs-import-btn');
    if (importBtn) importBtn.style.display = sel > 0 ? '' : 'none';
}

function dcsUF(i, field, value) {
    // Update a field value in the preview row data
    if (!window._dcsRows) return;
    if (!window._dcsRows[i]) return;
    var row = window._dcsRows[i];
    
    // Parse numeric fields
    if (field === 'qty' || field === 'cost' || field === 'sell') {
        value = parseFloat(value) || 0;
    }
    row[field] = value;
    
    // Recalculate margin if cost or sell changed
    if (field === 'cost' || field === 'sell') {
        if (window.dcsUpdateMargin) {
            window.dcsUpdateMargin(i);
        } else {
            // Inline margin calc fallback
            var cost = parseFloat(row.cost) || 0;
            var sell = parseFloat(row.sell) || 0;
            var marginPct = cost > 0 ? ((sell - cost) / sell * 100) : 0;
            row._margin = marginPct;
            // Update margin display cell if visible
            var marginCell = document.querySelector('[data-row="' + i + '"][data-field="margin"]');
            if (marginCell) marginCell.textContent = marginPct.toFixed(1) + '%';
        }
    }
}

function dcsDoImport() {
    // Add selected items from preview table to the Deal Cost Sheet
    // FIXED: Creates new ERP items first (async), then adds rows to DCS
    if (!window._dcsRows || !window._dcsRows.length) {
        frappe.show_alert({message: 'No items to import', indicator: 'orange'}, 3);
        return;
    }
    var selectedRows = window._dcsRows.filter(function(r) { return r._checked !== false; });
    if (!selectedRows.length) {
        frappe.show_alert({message: 'No rows selected. Check at least one item.', indicator: 'orange'}, 3);
        return;
    }
    var frm = cur_frm;
    if (!frm || !frm.doc) {
        frappe.show_alert({message: 'No active form found', indicator: 'red'}, 3);
        return;
    }
    var importBtn = document.getElementById('dcs-import-btn');
    if (importBtn) { importBtn.disabled = true; importBtn.textContent = 'Adding...'; }
    var newItems = selectedRows.filter(function(r) { return r._status === 'new_item'; });
    function addRowToForm(row) {
        var child = frm.add_child('items');
        // Use item_code (already truncated to 140 chars) as fallback
        child.item_code = row.item_code || dcsGenericFallback(row.item_group);
        child.item_name = (row.name || row.item_code).substring ? (row.name || row.item_code).substring(0, 140) : (row.name || row.item_code);
        child.qty = parseFloat(row.qty) || 1;
        child.cost_rate = parseFloat(row.cost) || 0;
        child.cost_amount = child.cost_rate * child.qty;
        child.selling_rate = parseFloat(row.sell) || 0;
        child.selling_amount = child.selling_rate * child.qty;
        if (row.item_group) child.item_group = row.item_group;
        if (row.header) child.header = row.header;
    }
    function finishImport(addedCount) {
        frm.refresh_field('items');
        if (window.dcsLiveCalc) setTimeout(function() { window.dcsLiveCalc(frm, true); }, 50);
        var overlay = document.getElementById('dcs-modal-overlay');
        if (overlay) overlay.remove();
        var modal = document.getElementById('dcs-bulk-modal');
        if (modal) modal.remove();
        frappe.show_alert({ message: '\u2705 ' + addedCount + ' item(s) added to the deal', indicator: 'green' }, 5);
        window._dcsRows = [];
    }
    if (newItems.length === 0) {
        selectedRows.forEach(addRowToForm);
        finishImport(selectedRows.length);
    } else {
        var createdCount = 0;
        var failedItems = [];
        var totalNew = newItems.length;
        function onAllCreated() {
      selectedRows.forEach(addRowToForm);
      finishImport(selectedRows.length);
      if (failedItems.length > 0) {
        frappe.msgprint({
          title: 'Some items used the Generic placeholder',
          indicator: 'orange',
          message: 'These item(s) could not be created or matched in the ERP Item Master, so they were added to this deal using the <b>Generic</b> placeholder item instead of failing:<br><br>' + failedItems.map(function(n){ return frappe.utils.escape_html(n); }).join('<br>') + '<br><br>Please open each row in the Items table and set the correct Item Code before finalizing this deal.'
        });
      }
    }
        newItems.forEach(function(row) {
            var itemGroup = row.item_group || 'Products';
            // Truncate item_code to 140 chars max (ERP limit)
            var safeCode = (row.item_code && row.item_code !== row.name) ? row.item_code.substring(0, 140) : (row.name.length > 140 ? row.name.substring(0, 137) + '...' : row.name);
            var safeName = row.name.length > 140 ? row.name.substring(0, 137) + '...' : row.name;
            frappe.call({
                method: 'frappe.client.insert',
                args: { doc: { doctype: 'Item', item_code: safeCode, item_name: safeName, item_group: itemGroup, is_sales_item: 1, is_purchase_item: 1, stock_uom: 'Nos', description: row.name } },
                callback: function(r) {
                    if (r && r.message) row.item_code = r.message.name;
                    createdCount++;
                    if (createdCount >= totalNew) onAllCreated();
                },
                error: function() {
                    // Try to find by safeCode (truncated) or by item_name
                    frappe.db.get_value('Item', {'item_code': safeCode}, 'name', function(res) {
                        if (res && res.name) {
                            row.item_code = res.name;
                            createdCount++;
                            if (createdCount >= totalNew) onAllCreated();
                        } else {
                            frappe.db.get_value('Item', {'item_name': row.name}, 'name', function(res2) {
                                if (res2 && res2.name) row.item_code = res2.name;
                                else {
                  // Could not create or find this item in ERP - fall back to the Generic
                  // placeholder item so the Deal Cost Sheet can still be saved instead of
                  // failing with a broken Item Code link.
                  failedItems.push(row.name);
                  row.item_code = dcsGenericFallback(itemGroup);
                  row._genericFallback = true;
                }
                                createdCount++;
                                if (createdCount >= totalNew) onAllCreated();
                            });
                        }
                    });
                }
            });
        });
    }
}


function dcsQuickAddButton(frm) {
    var field=frm.fields_dict.dcs_quick_add_html;
    if (!field || !field.$wrapper) return;
    field.$wrapper.empty();
    if (frm.doc.docstatus !== 0) {
        field.$wrapper.append($('<p class="text-muted small">').text(__('Submitted BOQ — use Revise BOQ to record changes.')));
        return;
    }
    var btn=$('<button type="button" class="btn btn-default btn-sm dcs-quick-add">').text(__('+ Quick add items'));
    btn.on('click',function(){dcsOpenModal();});
    field.$wrapper.append(btn);
}


// Compact CRM is scoped to this form; no desk-wide theme installer.


frappe.ui.form.on('Deal Cost Sheet', {
    refresh: function(frm) {
        render_summary_dashboard(frm);
    },
    currency: function(frm) {
        render_summary_dashboard(frm);
    },
    total_cost: function(frm) {
        render_summary_dashboard(frm);
    },
    total_selling: function(frm) {
        render_summary_dashboard(frm);
    },
    margin_value: function(frm) {
        render_summary_dashboard(frm);
    },
    margin_percent: function(frm) {
        render_summary_dashboard(frm);
    },
    workflow_state: function(frm) {
        render_summary_dashboard(frm);
    }
});

function render_summary_dashboard(frm) {
    var field=frm.fields_dict.custom_deal_summary_dashboard;
    if (!field) return;
    dcs_visual_styles(frm);
    if (dcs_is_draft(frm)) {
        frm.__dcs={};
        frm.__dcs_docname=frm.doc.name;
        ['custom_negotiation_html','custom_approval_html','custom_award_history_html','custom_handover_html'].forEach(function(name) {
            dcs_set_html(frm,name,'<div class="dcs-quiet">Available after the sheet is submitted.</div>');
        });
        dcs_render_draft_summary(frm, field); dcs_obligation_render(frm); return;
    }
    if (frm.__dcs_docname && frm.__dcs_docname !== frm.doc.name) frm.__dcs = {};
    var state=frm.__dcs || {}, s2=state.s2 || {}, s5=state.s5 || {};
    if (s2.ok !== 1 || s2.projection !== 'commercial') {
        field.$wrapper.html('<div class="dcs-panel dcs-quiet">' + dcs_esc(s2.error || 'Commercial evaluation is not available in this view.') + '</div>');
        dcs_obligation_render(frm);
        return;
    }
    var d=frm.doc, bridge=s2.margin_bridge, p=dcs_effective_position(frm,s5);
    var approval=dcs_approval_presentation(frm,s5), st=s5.states || {}, cond=s5.conditions || {};
    var next=dcs_next_step(frm,state.s3,state.s4,s5), esc=dcs_esc;
    var number=function(v){return format_number(Number(v)||0,null,dcs_money_precision(frm));};
    var money=function(v){return esc(d.currency || '') + ' ' + number(v);};
    var margin=function(v){
        return '<span class="' + dcs_margin_tone(v.selling > 0 ? Number(v.margin_percent)||0 : null) + '">'
            + (v.selling > 0 ? (Number(v.margin_percent)||0).toFixed(2)+'%' : 'Not priced') + '</span>';
    };
    var positions=bridge ? [['Original',bridge.original],['Current',bridge.current]] :
        [['Submitted BOQ',{cost:d.total_cost,selling:d.total_selling,gp:d.margin_value,margin_percent:d.margin_percent}]];
    if (bridge && bridge.awarded) positions.push(['Awarded',bridge.awarded]);
    var table='<div class="table-responsive"><table class="dcs-ledger"><thead><tr><th>Position</th><th>Buying</th><th>Selling</th><th>Gross profit</th><th>Margin</th></tr></thead><tbody>'
        + positions.map(function(x){var v=x[1] || {}; return '<tr class="'+(x[0]==='Current'?'dcs-current':(x[0]==='Awarded'?'dcs-awarded':''))+'"><th>'+esc(x[0])+'</th><td>'+number(v.cost)+'</td><td>'+number(v.selling)+'</td><td>'+number(v.gp)+'</td><td>'+margin(v)+'</td></tr>';}).join('')
        + '</tbody></table></div>';
    var movement='';
    if(bridge) {
        movement='<div class="dcs-movement">' + [['GP movement',bridge.gp_movement],['Customer impact',(bridge.gp_impacts || {}).customer],['Vendor impact',(bridge.gp_impacts || {}).vendor]].map(function(x){
            return '<div><span>'+x[0]+'</span><strong class="'+(x[1]<0?'dcs-tone-danger':'')+'">'+money(x[1])+'</strong></div>';
        }).join('')+'</div>';
    }
    var links=[['Opportunity','opportunity',d.opportunity],['Presales request','presales-request',d.presales_request],['Project','project',d.project]].filter(function(x){return !!x[2];}).map(function(x){
        return '<div class="dcs-detail"><span>'+x[0]+'</span><a href="/desk/'+x[1]+'/'+encodeURIComponent(x[2])+'">'+esc(x[2])+'</a></div>';
    }).join('');
    var evaluated=s5.ok===1 && st.customer_award==='Awarded' && Number(p.revision_no)>0;
    var blockers=evaluated && Number.isFinite(Number(cond.open_blockers)) ? Number(cond.open_blockers) : null;
    var delivery=st.delivery_release || 'Not evaluated';
    var html='<div class="dcs-panel dcs-overview">'
        + '<div class="dcs-overview-heading"><div><div class="dcs-eyebrow">COMMERCIAL OVERVIEW</div><h2>'+esc(d.customer || d.title || d.name)+'</h2></div><span class="dcs-revision">R'+p.revision_no+' · '+esc(d.currency || '')+'</span></div>'
        + '<div class="dcs-metrics">'
        + '<div><span>Current selling</span><strong>'+money(p.selling)+'</strong><small>Buying '+money(p.cost)+'</small></div>'
        + '<div><span>Gross profit</span><strong class="'+(p.gp<0?'dcs-tone-danger':'')+'">'+money(p.gp)+'</strong><small>Current commercial position</small></div>'
        + '<div><span>Gross margin</span><strong class="'+dcs_margin_tone(p.margin)+'">'+(p.margin===null?'Not priced':dcs_pct(p.margin))+'</strong><small>'+ (p.margin===null?'Selling price required':(p.margin<20?'Below the 20% floor':'Meets the 20% floor'))+'</small></div></div>'
        + '<div class="dcs-overview-grid"><section><div class="dcs-section-heading"><h3>Commercial position</h3><span>Amounts in ' + esc(d.currency || '') + ' · baseline → award</span></div>'+table+movement
        + '<details class="dcs-linked"><summary>Deal details &amp; linked records</summary>'+links
        + '<div class="dcs-detail"><span>Deal owner</span><strong>'+esc(d.deal_owner || 'Not assigned')+'</strong></div>'
        + '<div class="dcs-detail"><span>Prepared by</span><strong>'+esc(d.owner)+'</strong></div></details></section>'
        + '<aside><div class="dcs-decision"><div class="dcs-eyebrow">COMMERCIAL DECISION</div><h3>'+esc(approval.label)+'</h3><p>'+esc(approval.note)+'</p></div>'
        + (p.approval_required === 'Manager' && state.s2.manager_route ? '<p class="dcs-quiet">' + esc(state.s2.manager_route.approval_routing_error || ('Manager: ' + (state.s2.manager_route.approval_manager_name || state.s2.manager_route.approval_manager || 'Not configured'))) + '</p>' : '')
        + '<div class="dcs-release"><div class="dcs-eyebrow">AWARD &amp; DELIVERY</div><div class="dcs-detail"><span>Award</span><strong>'+esc(st.customer_award || 'Not Awarded')+'</strong></div>'
        + '<div class="dcs-detail"><span>Delivery</span><strong class="'+(delivery==='Blocked'?'dcs-tone-danger':'')+'">'+esc(delivery)+'</strong></div>'
        + '<div class="dcs-detail"><span>Open blockers</span><strong class="'+(blockers>0?'dcs-tone-danger':'')+'">'+(blockers===null?'Not evaluated':blockers)+'</strong></div>'
        + '<p class="dcs-quiet">Commercial approval and delivery release are separate decisions.</p></div></aside></div>'
        + '<div class="dcs-next"><span class="dcs-eyebrow">NEXT ACTION</span><div><strong>'+esc(next.label)+'</strong><p>'+esc(next.note)+'</p></div></div></div>';
    field.$wrapper.html(html);
    dcs_obligation_render(frm);
}

// Presentation only; server services remain the authority for every mutation.
function dcs_is_draft(frm) {
    return Number(frm.doc.docstatus || 0) === 0 || !!frm.doc.__islocal;
}

function dcs_draft_position(frm) {
    var doc=frm.doc, rows=(doc.items || []).length+(doc.resources || []).length+(doc.addtional_charges || []).length;
    var totals=rows ? dcs_boq_totals(doc.items,doc.resources,doc.addtional_charges) :
        {cost:Number(doc.total_cost)||0,selling:Number(doc.total_selling)||0};
    totals.gp=totals.selling-totals.cost;
    totals.margin=totals.selling>0 ? 100*totals.gp/totals.selling : null;
    totals.revision_no=0;
    return totals;
}

function dcs_render_draft_summary(frm, field) {
    var p=dcs_draft_position(frm), esc=dcs_esc;
    var full=frappe.session && frappe.session.user==='Administrator' ||
        ['Managing Director','Commercial Controller','Sales Manager','Presales'].some(function(role){return frappe.user.has_role(role);});
    var invalid=[];
    [['items',['qty','cost_rate','selling_rate']],['resources',['no_of_persons','no_of_days','hours','cost_rate']],['addtional_charges',['amount','selling_amount']]].forEach(function(pair){
        (frm.doc[pair[0]] || []).forEach(function(row,index){
            pair[1].forEach(function(key){
                var value=Number(row[key] || 0);
                if (!Number.isFinite(value) || value<0) invalid.push(pair[0]+' row '+(index+1)+': '+key.replaceAll('_',' '));
            });
        });
    });
    if (invalid.length) {
        field.$wrapper.html('<div class="dcs-panel alert alert-danger"><b>Correct invalid costing inputs</b><p>Negative or non-finite values cannot be saved or submitted.</p><p>'+esc(invalid.join('; '))+'</p></div>');
        return;
    }
    var entered=full ? p.cost!==0 || p.selling!==0 : p.selling!==0;
    if (!entered) {
        field.$wrapper.html('<div class="dcs-panel dcs-quiet"><b>Prepare the draft costing</b><p>'+ (frm.doc.party && frm.doc.subject ? 'Add BOQ lines in Costing. Your draft figures will appear here as you enter them.' : 'Enter customer and scope details first, then add BOQ lines in Costing. Your draft figures will appear here as you enter them.') + '</p></div>');
        return;
    }
    var money=function(v){return esc(frm.doc.currency || 'AED')+' '+format_number(v,null,dcs_money_precision(frm));};
    var html='<div class="dcs-panel dcs-overview"><div class="dcs-eyebrow">DRAFT ESTIMATE</div>'
        +'<h2>'+esc(frm.doc.organisation_name || frm.doc.customer || frm.doc.subject || 'New deal')+'</h2>'
        +'<div class="dcs-metrics"><div><span>Draft selling</span><strong>'+money(p.selling)+'</strong>'
        +(full ? '<small>Buying '+money(p.cost)+'</small>' : '')+'</div>';
    if (full) html+='<div><span>Gross profit</span><strong>'+money(p.gp)+'</strong><small>Draft BOQ estimate</small></div>'
        +'<div><span>Gross margin</span><strong class="'+dcs_margin_tone(p.margin)+'">'+(p.margin===null?'Selling price required':dcs_pct(p.margin))+'</strong></div>';
    var unpriced=(frm.doc.items || []).filter(function(row){return Number(row.qty)>0 && !(Number(row.selling_rate)>0);}).length;
    html+='</div>';
    if (unpriced) html+='<p class="text-warning">'+unpriced+' BOQ line(s) have no selling price. This is an incomplete pricing estimate.</p>';
    html+='<p>Recalculates as you edit the BOQ. Approval is evaluated when the sheet is submitted.</p></div>';
    field.$wrapper.html(html);
}

function dcs_margin_tone(margin) {
    return margin === null || !Number.isFinite(Number(margin)) ? 'dcs-tone-neutral' :
        (Number(margin) < 20 ? 'dcs-tone-danger' : 'dcs-tone-success');
}

function dcs_visual_styles(frm) {
    if (typeof document === 'undefined') return;
    if (frm.wrapper) $(frm.wrapper).addClass('dcs-workbench-v2 dcs-compact-crm');
    if (frm.page && frm.page.wrapper) $(frm.page.wrapper).addClass('dcs-workbench-v2 dcs-compact-crm');
    if (!frm.__dcs_compact_css && frappe.require) {
        frm.__dcs_compact_css=true;
        frappe.require('dcs_compact.bundle.css');
    }
    if (document.getElementById('dcs-workbench-v2-styles')) return;
    var style=document.createElement('style');
    style.id='dcs-workbench-v2-styles';
    style.textContent = `
.dcs-workbench-v2.dcs-workbench-v2 .dcs-panel {color:var(--text-color,#243247);font-size:13px;line-height:1.5}
.dcs-workbench-v2.dcs-workbench-v2 .dcs-overview {border:1px solid var(--border-color,#e3e7ee);border-radius:12px;background:var(--card-bg,#fff);padding:26px;box-shadow:none}
.dcs-workbench-v2.dcs-workbench-v2 .dcs-overview-heading {display:flex;justify-content:space-between;gap:16px;align-items:flex-start;margin-bottom:18px}
.dcs-workbench-v2.dcs-workbench-v2 .dcs-eyebrow {font-size:10px;letter-spacing:1.1px;font-weight:650;color:var(--text-muted,#68758a)}
.dcs-workbench-v2.dcs-workbench-v2 .dcs-overview h2 {font-size:21px;font-weight:650;line-height:1.3;margin:6px 0 0;overflow-wrap:anywhere;color:var(--text-color)}
.dcs-workbench-v2.dcs-workbench-v2 .dcs-revision {font-size:12px;color:var(--text-muted);white-space:nowrap;padding-top:4px}
.dcs-workbench-v2.dcs-workbench-v2 .dcs-metrics {display:grid;grid-template-columns:repeat(3,minmax(0,1fr));margin-bottom:20px;border-bottom:1px solid var(--border-color);padding-bottom:18px}
.dcs-workbench-v2.dcs-workbench-v2 .dcs-metrics>div {padding:0 24px;border-left:1px solid var(--border-color)}
.dcs-workbench-v2.dcs-workbench-v2 .dcs-metrics>div:first-child {padding-left:0;border:0}
.dcs-workbench-v2.dcs-workbench-v2 .dcs-metrics span,.dcs-workbench-v2.dcs-workbench-v2 .dcs-metrics small {display:block;color:var(--text-muted);font-size:12px}
.dcs-workbench-v2.dcs-workbench-v2 .dcs-metrics strong {display:block;font-size:27px;letter-spacing:-.5px;font-weight:650;margin:6px 0;line-height:1.3;font-variant-numeric:tabular-nums}
.dcs-workbench-v2.dcs-workbench-v2 .dcs-overview-grid {display:grid;grid-template-columns:minmax(0,2fr) minmax(240px,1fr);gap:28px}
.dcs-workbench-v2.dcs-workbench-v2 .dcs-section-heading {display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:14px}
.dcs-workbench-v2.dcs-workbench-v2 .dcs-panel h3 {font-size:14px;font-weight:650;margin:0;color:var(--text-color)}
.dcs-workbench-v2.dcs-workbench-v2 .dcs-section-heading>span {font-size:11px;color:var(--text-muted)}
.dcs-workbench-v2.dcs-workbench-v2 .dcs-panel table {width:100%;border-collapse:collapse;font-size:12px;min-width:530px}
.dcs-workbench-v2.dcs-workbench-v2 .dcs-panel .dcs-ledger {table-layout:fixed;min-width:0;box-sizing:border-box}
.dcs-workbench-v2.dcs-workbench-v2 .dcs-panel table thead,.dcs-workbench-v2.dcs-workbench-v2 .dcs-panel table thead tr,.dcs-workbench-v2.dcs-workbench-v2 .dcs-panel table th {background:var(--subtle-fg,#f6f8fa)!important;color:var(--text-muted,#667489)!important;box-shadow:none!important;border:0!important}
.dcs-workbench-v2.dcs-workbench-v2 .dcs-panel table th,.dcs-workbench-v2.dcs-workbench-v2 .dcs-panel table td {padding:11px 10px!important;white-space:nowrap;border-bottom:1px solid var(--border-color)!important;text-align:right;background:transparent!important;color:var(--text-color)!important;font-variant-numeric:tabular-nums;box-shadow:none!important}
.dcs-workbench-v2.dcs-workbench-v2 .dcs-panel table th:first-child,.dcs-workbench-v2.dcs-workbench-v2 .dcs-panel table td:first-child {text-align:left}
.dcs-workbench-v2.dcs-workbench-v2 .dcs-panel table thead th {font-weight:500!important;font-size:11px;color:var(--text-muted)!important;background:var(--subtle-fg,#f6f8fa)!important}
.dcs-workbench-v2.dcs-workbench-v2 .dcs-panel table .dcs-current td,.dcs-workbench-v2.dcs-workbench-v2 .dcs-panel table .dcs-current th {font-weight:650!important}
.dcs-workbench-v2.dcs-workbench-v2 .dcs-panel table .dcs-awarded td,.dcs-workbench-v2.dcs-workbench-v2 .dcs-panel table .dcs-awarded th {background:var(--subtle-fg,#f6f8fa)!important}
.dcs-workbench-v2.dcs-workbench-v2 .dcs-movement {display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin-top:18px}
.dcs-workbench-v2.dcs-workbench-v2 .dcs-movement span,.dcs-workbench-v2.dcs-workbench-v2 .dcs-movement strong {display:block;font-size:11px}
.dcs-workbench-v2.dcs-workbench-v2 .dcs-movement span {color:var(--text-muted);margin-bottom:4px}
.dcs-workbench-v2.dcs-workbench-v2 .dcs-movement strong {font-size:13px;font-weight:600}
.dcs-workbench-v2.dcs-workbench-v2 .dcs-decision {padding:18px;border:1px solid var(--border-color);border-radius:8px;background:var(--subtle-fg,#f6f8fa)}
.dcs-workbench-v2.dcs-workbench-v2 .dcs-decision h3 {font-size:18px;margin-top:8px}
.dcs-workbench-v2.dcs-workbench-v2 .dcs-panel p {font-size:12px;color:var(--text-muted);margin:8px 0 0}
.dcs-workbench-v2.dcs-workbench-v2 .dcs-release {padding:18px 0 0}
.dcs-workbench-v2.dcs-workbench-v2 .dcs-detail {display:flex;justify-content:space-between;gap:16px;padding:8px 0;font-size:12px;border-bottom:1px solid var(--border-color)}
.dcs-workbench-v2.dcs-workbench-v2 .dcs-detail>span {color:var(--text-muted);flex:none}
.dcs-workbench-v2.dcs-workbench-v2 .dcs-detail>strong,.dcs-workbench-v2.dcs-workbench-v2 .dcs-detail>a {font-weight:550;text-align:right;overflow-wrap:anywhere}
.dcs-workbench-v2.dcs-workbench-v2 .dcs-linked {margin-top:24px}
.dcs-workbench-v2.dcs-workbench-v2 .dcs-linked summary {cursor:pointer;font-size:12px;color:var(--text-muted);padding:8px 0}
.dcs-workbench-v2.dcs-workbench-v2 .dcs-next {display:flex;align-items:flex-start;gap:20px;margin-top:26px;padding-top:20px;border-top:1px solid var(--border-color)}
.dcs-workbench-v2.dcs-workbench-v2 .dcs-next>.dcs-eyebrow {white-space:nowrap;padding-top:3px}
.dcs-workbench-v2.dcs-workbench-v2 .dcs-next strong {font-size:14px;font-weight:650}
.dcs-workbench-v2.dcs-workbench-v2 .dcs-next p {margin:3px 0 0}
.dcs-workbench-v2.dcs-workbench-v2 .dcs-panel .dcs-tone-danger,.dcs-workbench-v2.dcs-workbench-v2 .dcs-compact .dcs-tone-danger {color:#b54735!important}
.dcs-workbench-v2.dcs-workbench-v2 .dcs-panel .dcs-tone-success,.dcs-workbench-v2.dcs-workbench-v2 .dcs-compact .dcs-tone-success {color:#25755a!important}
.dcs-workbench-v2.dcs-workbench-v2 .dcs-panel .dcs-tone-neutral {color:var(--text-muted)!important}
.dcs-workbench-v2.dcs-workbench-v2 .dcs-compact {display:flex;justify-content:space-between;gap:12px;align-items:center;font-size:12px;color:var(--text-color);padding-right:24px}
.dcs-workbench-v2.dcs-workbench-v2 .dcs-compact small {font-size:11px;color:var(--text-muted);margin-left:12px}
.dcs-workbench-v2.dcs-workbench-v2 .form-message {background:var(--card-bg,#fff)!important;border-bottom:1px solid var(--border-color);padding:10px 16px!important;box-shadow:none!important}
.dcs-workbench-v2.dcs-workbench-v2 .dcs-panel-title {font-size:14px;font-weight:650;margin:4px 0 18px}
.dcs-workbench-v2 .form-tabs {overflow-x:auto;flex-wrap:nowrap}.dcs-workbench-v2 .form-tabs .nav-item {flex-shrink:0}.dcs-workbench-v2 .table-responsive {overflow-x:auto}.dcs-workbench-v2 .table-responsive table {min-width:720px}.dcs-workbench-v2 .page-actions {flex-wrap:wrap;gap:4px}.dcs-workbench-v2 .dcs-overview {min-width:0;max-width:100%;overflow-wrap:anywhere}.dcs-workbench-v2 .dcs-overview-grid {min-width:0}.dcs-workbench-v2 .dcs-metrics {min-width:0}.dcs-workbench-v2 .form-grid [data-fieldname="cost_rate"] .static-area {direction:ltr;unicode-bidi:isolate;overflow:visible;white-space:nowrap}
@media(max-width:1000px) {.dcs-workbench-v2 .page-head-content {flex-wrap:wrap;height:auto}.dcs-workbench-v2 .page-actions {max-width:100%;height:auto}.dcs-workbench-v2 .dcs-overview-grid main {min-width:0}.dcs-workbench-v2.dcs-workbench-v2 .dcs-overview-grid {grid-template-columns:1fr}.dcs-workbench-v2.dcs-workbench-v2 .dcs-overview-grid aside {display:grid;grid-template-columns:1fr 1fr;gap:20px}.dcs-workbench-v2.dcs-workbench-v2 .dcs-release {padding-top:0}.dcs-workbench-v2.dcs-workbench-v2 .dcs-metrics strong {font-size:23px}}
@media(max-width:600px) {.dcs-workbench-v2.dcs-workbench-v2 .dcs-overview {padding:16px}.dcs-workbench-v2.dcs-workbench-v2 .dcs-metrics {grid-template-columns:1fr;gap:16px}.dcs-workbench-v2.dcs-workbench-v2 .dcs-metrics>div {padding:0;border:0}.dcs-workbench-v2.dcs-workbench-v2 .dcs-overview-grid aside {grid-template-columns:1fr}.dcs-workbench-v2.dcs-workbench-v2 .dcs-section-heading {display:block}.dcs-workbench-v2.dcs-workbench-v2 .dcs-compact {display:block}.dcs-workbench-v2.dcs-workbench-v2 .dcs-movement {grid-template-columns:1fr}.dcs-workbench-v2.dcs-workbench-v2 .dcs-next {display:block}}
`;
    document.head.appendChild(style);
}

function dcs_read_view(s2,s5) {
    if (s5.ok === 1 || s2.ok !== 1 || s2.projection !== 'commercial') return s5;
    var guard=s2.negotiation_guard || {}, position=(s2.margin_bridge || {}).current || {}, award=s2.award || {};
    return {ok:1,projection:'commercial',authority:{},conditions:{},limited_read:1,
        living:{revision_no:guard.revision_no,total_cost:position.cost,total_selling:position.selling,
            margin_percent:position.margin_percent,approval_required:guard.approval_required,
            approval_state:guard.approval_state,margin_gate:guard.margin_gate,authorised_position:guard.authorised_position},
        states:{customer_award:award.state || 'Not Awarded',delivery_release:award.delivery_release_state || 'Not Applicable'},
        frozen_baseline:{frozen:award.frozen,revision_no:award.frozen_revision_no,total_cost:award.frozen_total_cost,
            total_selling:award.frozen_total_selling,margin_percent:award.frozen_margin_percent},
        release_readiness:{pre_award_note:'Commercial read view. Award and delivery actions are available only to authorised commercial owners.'}};
}

function dcs_effective_position(frm, s5) {
    if (dcs_is_draft(frm)) return dcs_draft_position(frm);
    var doc = frm.doc, lv = (s5 || {}).living || {};
    var rev = Number(lv.revision_no !== undefined ? lv.revision_no : doc.custom_dcs_revision_no) || 0;
    var value = function (key, field, fallback) {
        var raw = lv[key] !== undefined && lv[key] !== null ? lv[key] : doc[field];
        return Number(raw !== undefined && raw !== null ? raw : fallback) || 0;
    };
    var cost = rev > 0 ? value('total_cost', 'custom_working_total_cost', doc.total_cost) : Number(doc.total_cost) || 0;
    var selling = rev > 0 ? value('total_selling', 'custom_working_total_selling', doc.total_selling) : Number(doc.total_selling) || 0;
    return {revision_no: rev, cost: cost, selling: selling, gp: selling-cost,
        margin: selling > 0 ? 100*(selling-cost)/selling : null,
        approval_required: lv.approval_required, approval_state: lv.approval_state,
        margin_gate: lv.margin_gate, authorised: lv.authorised_position === 1};
}

function dcs_approval_presentation(frm, s5) {
    if (dcs_is_draft(frm)) return {label:'Draft estimate',note:'Approval is evaluated when the sheet is submitted.',color:'gray'};
    var p = dcs_effective_position(frm, s5);
    if (!s5 || s5.ok !== 1 || !s5.living) {
        return {label:'Not available', note:'Commercial evaluation is unavailable for this view.', color:'gray'};
    }
    if (!p.revision_no || p.selling <= 0) {
        return {label:'Not evaluated', note:p.selling <= 0 ? 'Add selling prices, then record a BOQ revision.' : 'Record a revision to evaluate this legacy baseline.', color:'gray'};
    }
    if (p.approval_state === 'Rejected' || p.approval_state === 'Returned for Rework') {
        return {label:p.approval_state, note:'Revise this sheet. The new position is evaluated independently; this decision stays in history.', color:'red'};
    }
    if (p.approval_required === 'Blocked') {
        return {label:'Rework required', note:'Concession exceeds the ceiling. Revise the commercial position.', color:'red'};
    }
    if (p.margin < 20 || ['Manager','Managing Director'].indexOf(p.approval_required) !== -1) {
        return {label:p.authorised ? (p.approval_required === 'Manager' ? 'Manager approved' : 'Approved') : 'Manager approval required',
            note:p.margin < 20 ? 'Below the 20% margin floor. Delivery conditions remain separate.' : 'Another commercial approval trigger applies.',
            color:p.authorised ? 'green' : 'orange'};
    }
    if (p.approval_required === 'None') {
        return {label:'Not required', note:'Margin is at least 20% and no other approval trigger applies.', color:'blue'};
    }
    return {label:'Not evaluated', note:'Refresh or revise to evaluate the current position.', color:'gray'};
}

function dcs_boq_totals(items, resources, charges) {
    var n = function (v) { return Number(v) || 0; }, cost = 0, selling = 0;
    (items || []).forEach(function (r) { cost += n(r.qty)*n(r.cost_rate); selling += n(r.qty)*n(r.selling_rate); });
    (resources || []).forEach(function (r) {
        cost += (n(r.no_of_persons) && n(r.no_of_days) ? n(r.no_of_persons)*n(r.no_of_days) : n(r.hours))*n(r.cost_rate);
    });
    (charges || []).forEach(function (r) { cost += n(r.amount); selling += n(r.selling_amount); });
    return {cost:cost, selling:selling, gp:selling-cost, margin:selling > 0 ? 100*(selling-cost)/selling : null};
}

function dcs_next_step(frm, s3, s4, s5) {
    if (frm.doc.docstatus === 2) return {label:'Cancelled record', note:'Historical record; no commercial action is available.'};
    if (frm.doc.docstatus !== 1) return {label:'Complete costing', note:'Prepare the BOQ and submit the sheet for commercial evaluation.'};
    var route=((frm.__dcs || {}).s2 || {}).manager_route || ((frm.__dcs || {}).s4 || {}).manager_route || {};
    if (route.approval_routing_error && route.changed_by === ((frappe.session || {}).user)) {
        return {key:'Refresh Manager Routing',group:'Approval',label:'Route to my manager',note:route.approval_routing_error + ' Correct the Employee reporting line, then retry routing.'};
    }

    var cap = (s3 || {}).capability || {}, st = (s5 || {}).states || {}, auth = (s5 || {}).authority || {};
    var p = dcs_effective_position(frm, s5), actions = (s4 || {}).actions || [];
    if (cap.can_negotiate && st.customer_award !== 'Awarded' && !p.revision_no && p.selling > 0) {
        return {key:'Evaluate submitted BOQ',group:'Negotiation',label:'Evaluate submitted BOQ',note:'Record the submitted baseline and calculate approval requirements without changing its totals.'};
    }
    if (cap.can_negotiate && st.customer_award !== 'Awarded' &&
        (!p.revision_no || p.selling <= 0 || ['Rejected','Returned for Rework','Blocked'].indexOf(p.approval_state) >= 0)) {
        return {key:'BOQ Revision', group:'Negotiation', label:'Revise BOQ', note:'Revise this sheet; approval is recalculated for the new position.'};
    }
    if (actions.length && p.approval_required && p.approval_required !== 'None' && p.approval_state !== 'Approved') {
        var preferred = actions.filter(function (a) { return ['Approve','Endorse','Return for Rework'].indexOf(a.key) >= 0; })[0] || actions[0];
        return {key:preferred.key, group:'Approval', label:preferred.label, note:preferred.note};
    }
    var required=p.approval_required || ((s4 || {}).deal || {}).approval_required;
    if (required === 'Manager' && !p.authorised && ['Rejected','Returned for Rework'].indexOf(p.approval_state) < 0) {
        return {label:'Await manager decision',note:route.approval_routing_error || ('Routed to ' + (route.approval_manager_name || route.approval_manager || 'the immediate manager') + '.')};
    }
    if (auth.can_record_award && p.authorised && st.customer_award !== 'Awarded') {
        return {key:'Record Award', group:'Award', label:'Record Award', note:'Record customer evidence and freeze the current commercial position.'};
    }
    if (st.customer_award === 'Awarded') {
        if (s5.release_readiness && s5.release_readiness.commercially_aligned === 0) return {label:'Review changed award',group:'Award',note:'The current position differs from the frozen award. Reverse and re-award before PO reconciliation or delivery.'};
        if (((s5 || {}).po || {}).reconciliation_state !== 'Reconciled' && auth.can_reconcile_po) {
            return {key:'Reconcile Customer PO', group:'Handover', label:'Reconcile Customer PO', note:'Check PO value, scope and payment terms against the awarded position.'};
        }
        if (!st.delivery_owner && auth.can_set_delivery_owner) {
            return {key:'Set Delivery Owner', group:'Handover', label:'Set Delivery Owner', note:'Name the person accountable for delivery.'};
        }
        if (auth.can_release && s5.release_readiness && s5.release_readiness.commercially_aligned &&
            Number((s5.conditions || {}).open_blockers) === 0 && (st.delivery_release || '').indexOf('Released') !== 0) {
            return {key:'Release to Delivery', group:'Handover', label:'Release to Delivery', note:'Confirm release of the awarded and reconciled position.'};
        }
        return {label:'Review handover conditions', group:'Handover', note:'Award, PO reconciliation and delivery release are separate decisions.'};
    }
    return {label:'Review commercial position', note:'Resolve pricing or approval requirements using the permitted actions.'};
}

// Deal Cost Sheet - Living DCS Experience
// Brings Negotiation, Approval, Award, Award Reversal, PO Reconciliation and Handover onto the
// Deal Cost Sheet document itself, using standard ERPNext form patterns: form dashboard headline,
// dashboard indicators, grouped inner buttons and HTML fields inside the existing sections.
// No business logic lives here. Every action calls the same governed server service that the
// Commercial Command Center calls, and every refusal is the server's refusal, shown verbatim.

frappe.ui.form.on('Deal Cost Sheet', {
	refresh: function (frm) {
		if (frm.is_new()) { return; }
		dcs_load(frm);
	}
});

function dcs_esc(v) {
	if (v === null || v === undefined) { return ''; }
	return String(v).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function dcs_money_precision(frm) { return (frm.doc.currency || '').toUpperCase() === 'OMR' ? 3 : 2; }
function dcs_reference_price(key, currency) {
    var ref = AI_PRICE_DB[key];
    return ref && ref.currency === currency ? ref : null;
}

function dcs_cur(frm) { return frm.doc.currency || frappe.defaults.get_default('currency'); }

function dcs_money(frm, v) {
	if (v === null || v === undefined || v === '') { return '&mdash;'; }
	return format_currency(v, dcs_cur(frm), dcs_money_precision(frm));
}

function dcs_pct(v) {
	if (v === null || v === undefined || v === '') { return '&mdash;'; }
	return Number(v).toFixed(Number(v) < 20 && Number(v) > 19.99 ? 4 : 2) + '%';
}

function dcs_when(v) { return v ? frappe.datetime.str_to_user(v) : '&mdash;'; }

function dcs_panel(title, body, note) {
	var n = note ? '<div class="text-muted small" style="margin-top:6px">' + dcs_esc(note) + '</div>' : '';
	return '<div class="dcs-panel"><div class="dcs-panel-title">'
		+ dcs_esc(title) + '</div>' + body + n + '</div>';
}

function dcs_empty(msg) {
	return '<div class="text-muted" style="padding:12px 0">' + dcs_esc(msg) + '</div>';
}

function dcs_set_html(frm, field, html) {
	var f = frm.get_field(field);
	if (f && f.$wrapper) { f.$wrapper.html(html); }
}

// A-14: governed DCS services now live in app code (bsgroup/api/dcs). Every
// workspace call resolves through this map to the dotted app method; the bare
// Server Script names are no longer called from the client.
var DCS_METHODS = {
	dcs_refresh_manager_route: 'bsgroup.dcs.manager_approval.dcs_refresh_manager_route',
	dcs_apply_revision: 'bsgroup.api.dcs.negotiation.dcs_apply_revision',
	dcs_screen2: 'bsgroup.api.dcs.living.dcs_screen2',
	dcs_screen3: 'bsgroup.api.dcs.negotiation.dcs_screen3',
	dcs_approval_decision: 'bsgroup.api.dcs.approval.dcs_approval_decision',
	dcs_screen4: 'bsgroup.api.dcs.approval.dcs_screen4',
	dcs_record_award: 'bsgroup.api.dcs.award.dcs_record_award',
	dcs_apply_boq_revision: 'bsgroup.api.dcs.boq_revision.dcs_apply_boq_revision',
	dcs_award_reversal: 'bsgroup.api.dcs.award.dcs_award_reversal',
	dcs_po_reconcile: 'bsgroup.api.dcs.award.dcs_po_reconcile',
	dcs_set_delivery_owner: 'bsgroup.api.dcs.handover.dcs_set_delivery_owner',
	dcs_handover_action: 'bsgroup.api.dcs.handover.dcs_handover_action',
	dcs_delivery_release: 'bsgroup.api.dcs.handover.dcs_delivery_release',
	dcs_screen5: 'bsgroup.api.dcs.handover.dcs_screen5'
};

function dcs_method(name) {
	if (!DCS_METHODS[name]) {
		throw new Error('Unknown governed DCS service: ' + name);
	}
	return DCS_METHODS[name];
}

function dcs_call(method, args) {
	return new Promise(function (resolve) {
		frappe.call({ method: dcs_method(method), args: args, callback: function (r) { resolve((r && r.message) || {}); }, error: function () { resolve({ok:0, load_failed:1, error:"Commercial evaluation could not be loaded. Refresh to retry."}); } });
	});
}

function dcs_load(frm) {
    var n=frm.doc.name;
    frm.__dcs={};
    frm.__dcs_docname=n;
    if (dcs_is_draft(frm)) {
        frm.__dcs_load_id=(frm.__dcs_load_id || 0)+1;
        render_summary_dashboard(frm);
        frm.dashboard.set_headline('<div class="dcs-compact"><span>' + (frm.doc.party && frm.doc.subject ? 'Complete the costing, then submit for commercial evaluation.' : 'Enter customer and scope details, then complete costing.') + '</span></div>');
        return;
    }
    var loadId = frm.__dcs_load_id = (frm.__dcs_load_id || 0) + 1;
	Promise.all([
		dcs_call('dcs_screen3', { dcs: n }),
		dcs_call('dcs_screen4', { dcs: n }),
		dcs_call('dcs_screen5', { dcs: n }),
		dcs_call('dcs_screen2', { dcs: n })
	]).then(function (res) {
		if (frm.doc.name !== n || frm.__dcs_load_id !== loadId) return;
        var s3 = res[0] || {}, s4 = res[1] || {}, s5 = dcs_read_view(res[3] || {},res[2] || {});
		frm.__dcs = { s3: s3, s4: s4, s5: s5, s2: res[3] || {} };
		render_summary_dashboard(frm);
		dcs_headline(frm, s5);
		dcs_indicators(frm, s5);
		dcs_render_negotiation(frm, s3);
		dcs_render_approval(frm, s4);
		dcs_render_award(frm, s5);
		dcs_render_handover(frm, s5);
		dcs_buttons(frm, s3, s4, s5);
	});
}

function dcs_headline(frm, s5) {
    dcs_visual_styles(frm);
    if (!s5.living || s5.ok !== 1) {
        if (((frm.__dcs || {}).s2 || {}).ok === 1) {
            frm.dashboard.set_headline('<div class="dcs-compact">Delivery financial position · Commercial actions require the assigned approver.</div>');
            return;
        }
        var routing=((frm.__dcs || {}).s4 || {});
        if (routing.projection === 'approval-routing') {
            var route=routing.manager_route || {}, deal=routing.deal || {};
            frm.dashboard.set_headline('<div class="dcs-compact"><b>' + dcs_esc(deal.approval_state || 'Manager approval') + '</b><span>' + dcs_esc(route.approval_routing_error || ('Manager: ' + (route.approval_manager_name || route.approval_manager || 'Not configured'))) + '</span></div>');
            return;
        }
        frm.dashboard.set_headline('<div class="dcs-compact">Commercial evaluation is not available in this view. ' + dcs_esc(s5.error || 'Refresh to retry.') + '</div>');
        return;
    }
    var p=dcs_effective_position(frm,s5), approval=dcs_approval_presentation(frm,s5);
    var next=dcs_next_step(frm,(frm.__dcs || {}).s3,(frm.__dcs || {}).s4,s5);
    frm.dashboard.set_headline('<div class="dcs-compact"><div><b>'+dcs_esc(approval.label)+'</b><small>Margin <span class="'+dcs_margin_tone(p.margin)+'">'+(p.margin===null?'Not priced':p.margin.toFixed(2)+'%')+'</span> · R'+p.revision_no+'</small></div><span>Next: <b>'+dcs_esc(next.label)+'</b></span></div>');
}

function dcs_indicators(frm, s5) {
	var st = s5.states || {}, lv = s5.living || {}, po = s5.po || {}, cond = s5.conditions || {};
	var add = function (label, colour) { frm.dashboard.add_indicator(__(label), colour); };
	if (lv.margin_gate) { add('Margin ' + lv.margin_gate, lv.margin_gate === 'Clear' ? 'green' : 'red'); }
	if (lv.approval_state) {
		var c = lv.approval_state === 'Approved' ? 'green' : (lv.approval_state === 'Rejected' ? 'red' : 'orange');
		add(lv.approval_state, c);
	}
	add('Award: ' + (st.customer_award || 'Not Awarded'), st.customer_award === 'Awarded' ? 'green' : 'gray');
	if (st.award_reversal_state) { add('Reversal: ' + st.award_reversal_state, 'red'); }
	if (po.reconciliation_state) { add('PO ' + po.reconciliation_state, po.reconciliation_state === 'Reconciled' ? 'green' : 'orange'); }
	var ob = Number(cond.open_blockers);
    var evaluated = s5.ok === 1 && st.customer_award === 'Awarded' && Number(lv.revision_no) > 0;
    add(!evaluated || !Number.isFinite(ob) ? 'Handover not evaluated' : (ob === 0 ? 'No open handover blockers' : ob + ' open handover blocker(s)'),
        !evaluated || !Number.isFinite(ob) ? 'gray' : (ob === 0 ? 'green' : 'red'));
	add('Delivery: ' + (st.delivery_release || 'Not Applicable'), (st.delivery_release || '').indexOf('Released') === 0 ? 'blue' : 'gray');
    if (s5.ok === 1 && s5.projection === 'commercial' && frm.dashboard.stats_area) frm.dashboard.stats_area.hide();
}

function dcs_revision_movement(frm, before, after, margin) {
    var format=margin ? dcs_pct : function(value){return dcs_money(frm,value);};
    // Isolate each amount: Arabic currency markers must not reverse old/new order.
    return '<span class="dcs-revision-movement" dir="ltr"><bdi dir="ltr">'+format(before)+'</bdi><span aria-hidden="true"> → </span><bdi dir="ltr">'+format(after)+'</bdi></span>';
}

function dcs_render_negotiation(frm, s3) {
	var revs = (s3.revisions || []).slice().sort(function (a, b) { return b.revision_no - a.revision_no; });
	var pol = s3.policy || {};
	var body;
	if (!revs.length) {
		body = dcs_empty('No baseline recorded yet. Valid submitted totals are initialised automatically on submission or the first authorised award.');
	} else {
		var rows = revs.map(function (r) {
			var gp = r.gp_movement || 0;
			var gpTxt = (gp > 0 ? '+' : '') + format_currency(gp, dcs_cur(frm),dcs_money_precision(frm));
			var gpCls = gp > 0 ? 'text-success' : (gp < 0 ? 'text-danger' : 'text-muted');
			var req = (r.approval_requirement && r.approval_requirement !== 'None') ? '<span class="indicator-pill orange">' + dcs_esc(r.approval_requirement) + '</span>' : '<span class="text-muted">None</span>';
			return '<tr>'
				+ '<td style="white-space:nowrap"><a href="' + frappe.utils.get_form_link('DCS Revision', r.name) + '">R' + dcs_esc(r.revision_no) + '</a></td>'
				+ '<td>' + dcs_esc(r.source) + '</td>'
				+ '<td class="text-right" dir="ltr" style="white-space:nowrap">' + dcs_revision_movement(frm,r.prev_total_cost,r.new_total_cost,false) + '</td>'
				+ '<td class="text-right" dir="ltr" style="white-space:nowrap">' + dcs_revision_movement(frm,r.prev_total_selling,r.new_total_selling,false) + '</td>'
				+ '<td class="text-right">' + dcs_revision_movement(frm,r.prev_margin_percent,r.new_margin_percent,true) + '</td>'
				+ '<td class="text-right ' + gpCls + '">' + gpTxt + '</td>'
				+ '<td>' + req + '</td>'
				+ '<td class="text-muted small">' + dcs_esc(r.changed_by) + '<br>' + dcs_when(r.changed_on) + '</td>'
				+ '</tr>'
				+ '<tr><td></td><td colspan="7" class="text-muted small" style="padding-bottom:10px">' + dcs_esc(r.reason)
				+ (r.technical_impact ? '<br><i>Technical impact:</i> ' + dcs_esc(r.technical_impact) : '') + '</td></tr>';
		}).join('');
		body = '<div class="table-responsive"><table class="table table-sm" style="font-size:12px">'
			+ '<thead><tr><th>Rev</th><th>Side</th><th class="text-right">Buying: before → after</th><th class="text-right">Selling: before → after</th>'
			+ '<th class="text-right">Margin</th><th class="text-right">GP move</th><th>Sign-off</th><th>Recorded</th></tr></thead>'
			+ '<tbody>' + rows + '</tbody></table></div>';
	}
	var note = 'Revisions are immutable and are never edited or deleted. Negotiation never cancels or amends this document.';
	if (pol.margin_floor_percent !== undefined) {
		note += ' Margin floor ' + pol.margin_floor_percent + '%, sign-off threshold ' + pol.md_threshold_percent + '% concession.';
	}
	dcs_set_html(frm, 'custom_negotiation_html', dcs_panel('Revision timeline', body, note));
}

function dcs_render_approval(frm, s4) {
	var hist = s4.approval_history || [], why = s4.why || {}, prev = s4.previous_approved || {}, cur = s4.current || {}, d = s4.delta || {};
	var body = '';
    if (s4.manager_route && s4.manager_route.approval_policy === 'Immediate Manager') {
        body += '<div class="dcs-decision"><div class="dcs-eyebrow">MANAGER APPROVAL</div><h3>' + dcs_esc(s4.manager_route.approval_manager_name || s4.manager_route.approval_manager || 'Manager not configured') + '</h3><p>' + dcs_esc(s4.manager_route.approval_routing_error || 'Routed from the current revision submitter’s Employee reporting line.') + '</p></div>';
    }
	if (why.approval_reason || why.margin_gate_reason) {
		body += '<div class="text-muted small" style="margin-bottom:10px">' + dcs_esc(why.approval_reason || '')
			+ (why.margin_gate_reason ? '<br>' + dcs_esc(why.margin_gate_reason) : '') + '</div>';
	}
	if (prev.available) {
		body += '<div class="table-responsive"><table class="table table-sm" style="font-size:12px">'
			+ '<thead><tr><th></th><th class="text-right">Cost</th><th class="text-right">Selling</th><th class="text-right">GP</th><th class="text-right">Margin</th></tr></thead><tbody>'
			+ '<tr><td class="text-muted">Last approved (R' + dcs_esc(prev.revision_no) + ')</td><td class="text-right">' + dcs_money(frm, prev.total_cost) + '</td><td class="text-right">' + dcs_money(frm, prev.total_selling) + '</td><td class="text-right">' + dcs_money(frm, prev.gp) + '</td><td class="text-right">' + dcs_pct(prev.margin_percent) + '</td></tr>'
			+ '<tr><td><b>Proposed now</b></td><td class="text-right"><b>' + dcs_money(frm, cur.total_cost) + '</b></td><td class="text-right"><b>' + dcs_money(frm, cur.total_selling) + '</b></td><td class="text-right"><b>' + dcs_money(frm, cur.gp) + '</b></td><td class="text-right"><b>' + dcs_pct(cur.margin_percent) + '</b></td></tr>'
			+ '<tr class="text-muted"><td>Movement</td><td class="text-right">' + dcs_money(frm, d.total_cost) + '</td><td class="text-right">' + dcs_money(frm, d.total_selling) + '</td><td class="text-right">' + dcs_money(frm, d.gp) + '</td><td class="text-right">' + dcs_pct(d.margin_points) + '</td></tr>'
			+ '</tbody></table></div>';
	}
	if (hist.length) {
		body += '<div class="table-responsive"><table class="table table-sm" style="font-size:12px">'
			+ '<thead><tr><th>Rev</th><th>Side</th><th>State</th><th>Requirement</th><th>Decision</th></tr></thead><tbody>'
			+ hist.map(function (h) {
				return '<tr><td>R' + dcs_esc(h.revision_no) + '</td><td>' + dcs_esc(h.source) + '</td><td>' + dcs_esc(h.state) + '</td><td>' + dcs_esc(h.requirement) + '</td>'
					+ '<td class="text-muted small">' + (h.decided_by ? dcs_esc(h.decided_by) + ' &middot; ' + dcs_when(h.decided_on) : 'Awaiting decision')
					+ (h.decision_reason ? '<br>' + dcs_esc(h.decision_reason) : '') + '</td></tr>';
			}).join('') + '</tbody></table></div>';
	} else {
		body += dcs_empty('No approval decisions have been recorded on this deal.');
	}
	dcs_set_html(frm, 'custom_approval_html', dcs_panel('Approval history and policy evaluation', body, why.policy_basis || ''));
}

function dcs_render_award(frm, s5) {
	var aw = s5.award || {}, fz = s5.frozen_baseline || {}, st = s5.states || {};
	var body = '<div class="table-responsive"><table class="table table-sm" style="font-size:12px"><tbody>'
		+ '<tr><td class="text-muted" style="width:36%">Award state</td><td>' + dcs_esc(aw.state || 'Not Awarded') + ' &middot; sequence ' + dcs_esc(st.award_sequence_no || 0) + '</td></tr>'
		+ '<tr><td class="text-muted">Evidence</td><td>' + dcs_esc(aw.evidence_type || '—') + ' ' + dcs_esc(aw.reference || '') + '</td></tr>'
		+ '<tr><td class="text-muted">Recorded</td><td>' + (aw.recorded_by ? dcs_esc(aw.recorded_by) + ' &middot; ' + dcs_when(aw.recorded_on) : '&mdash;') + '</td></tr>'
		+ '<tr><td class="text-muted">Frozen baseline</td><td>' + (fz.frozen ? 'Cost ' + dcs_money(frm, fz.total_cost) + ' &middot; Selling ' + dcs_money(frm, fz.total_selling) + ' &middot; GP ' + dcs_money(frm, fz.gp) + ' &middot; ' + dcs_pct(fz.margin_percent) + ' at revision ' + dcs_esc(fz.revision_no) : 'Not frozen') + '</td></tr>'
		+ '<tr><td class="text-muted">Reversals</td><td>' + dcs_esc(st.award_reversal_count || 0) + (st.award_reversal_state ? ' &middot; ' + dcs_esc(st.award_reversal_state) : '') + (st.award_reversal_ref ? ' &middot; <a href="' + frappe.utils.get_form_link('DCS Award Reversal', st.award_reversal_ref) + '">' + dcs_esc(st.award_reversal_ref) + '</a>' : '') + '</td></tr>'
		+ '</tbody></table></div>';
	var note = fz.note || '';
	if (st.separation_note) { note = note + ' ' + st.separation_note; }
	dcs_set_html(frm, 'custom_award_history_html', dcs_panel('Award and frozen baseline', body, note));
	frappe.call({
		method: 'frappe.client.get_list',
		args: { doctype: 'DCS Award Reversal', filters: { dcs: frm.doc.name }, fields: ['name', 'reversal_no', 'reversal_reason', 'status'], limit_page_length: 50 },
		callback: function (r) {
			var rows = (r && r.message) || [];
			if (!rows.length) { return; }
			var h = '<div class="table-responsive"><table class="table table-sm" style="font-size:12px"><thead><tr><th>Reversal</th><th>Status</th><th>Reason</th></tr></thead><tbody>'
				+ rows.map(function (x) {
					return '<tr><td style="white-space:nowrap"><a href="' + frappe.utils.get_form_link('DCS Award Reversal', x.name) + '">' + dcs_esc(x.name) + '</a></td>'
						+ '<td>' + dcs_esc(x.status || '&mdash;') + '</td><td class="text-muted small">' + dcs_esc(x.reversal_reason) + '</td></tr>';
				}).join('') + '</tbody></table></div>';
			var f = frm.get_field('custom_award_history_html');
			if (f && f.$wrapper) { f.$wrapper.append(dcs_panel('Award reversal records', h, 'Award reversal records are immutable and service-owned.')); }
		}
	});
}

function dcs_render_handover(frm, s5) {
	var c = s5.conditions || {}, rr = s5.release_readiness || {}, st = s5.states || {};
	var pill = function (state) {
		var map = { 'Open': 'red', 'Cleared': 'green', 'Accepted Risk': 'orange' };
		return '<span class="indicator-pill ' + (map[state] || 'gray') + '">' + dcs_esc(state) + '</span>';
	};
	var technical = s5.projection === 'technical';
    var all = technical ? (s5.technical_conditions || []) : (c.blockers || []).concat(c.watch_items || []).concat(c.accepted_risks || []);
    var evaluated = s5.ok === 1 && s5.projection === 'commercial' && rr.awarded_and_frozen;
    var body = '<div style="margin-bottom:10px">'
        + '<span class="indicator-pill ' + (!evaluated ? 'gray' : (rr.commercially_aligned ? 'green' : 'red')) + '">' + (!evaluated ? 'Handover not evaluated' : (rr.commercially_aligned ? 'Awarded position aligned' : 'Not commercially aligned')) + '</span> '
        + (evaluated ? '<span class="indicator-pill ' + ((c.open_blockers || 0) === 0 ? 'green' : 'red') + '">' + (c.open_blockers || 0) + ' open handover blocker(s)</span> ' : '')
		+ '<span class="indicator-pill gray">Delivery owner: ' + dcs_esc(st.delivery_owner || 'not named') + '</span>'
		+ (rr.note ? '<div class="text-danger small" style="margin-top:8px">' + dcs_esc(rr.note) + '</div>' : '') + '</div>';
	if (!all.length) {
		body += dcs_empty('No handover conditions have been raised on this deal.');
	} else {
		body += '<div class="table-responsive"><table class="table table-sm" style="font-size:12px">'
			+ '<thead><tr><th>#</th><th>Condition</th><th>Domain</th><th>Category</th><th>State</th><th>Latest note</th></tr></thead><tbody>'
			+ all.map(function (x) {
				var note = x.state === 'Accepted Risk' ? (x.acceptance_reason || '') : (x.clearance_note || x.last_action_note || '');
				return '<tr><td>' + dcs_esc(x.condition_no) + '</td>'
					+ '<td><a href="' + frappe.utils.get_form_link('DCS Handover Condition', x.name) + '">' + dcs_esc(x.condition_title) + '</a></td>'
					+ '<td>' + dcs_esc(x.domain) + '</td><td>' + dcs_esc(x.original_category || x.category) + '</td><td>' + pill(x.state) + '</td>'
					+ '<td class="text-muted small">' + dcs_esc(note) + '</td></tr>';
			}).join('') + '</tbody></table></div>';
	}
	dcs_set_html(frm, 'custom_handover_html', dcs_panel(technical ? 'Technical conditions' : 'Handover conditions and delivery readiness', body, technical ? 'Only technical conditions are shown in this view. Commercial clearance is evaluated separately.' : (rr.basis || '')));
}

function dcs_run(frm, method, args, dlg) {
	frappe.call({
		method: dcs_method(method),
		args: args,
		freeze: true,
		freeze_message: __('Applying...'),
		callback: function (r) {
			var m = (r && r.message) || {};
			if (m.ok !== 1 || m.error) {
				frappe.msgprint({ title: __('Action not recorded'), message: dcs_esc(m.error || 'The action could not be verified. Refresh and retry.'), indicator: 'red' });
				return;
			}
			if (dlg) { dlg.hide(); }
			if (m.no_change) {
                frappe.show_alert({message:__('No change — no revision recorded'),indicator:'blue'});
            } else if (m.idempotent_replay) {
				frappe.show_alert({ message: __('Already recorded - nothing changed again'), indicator: 'blue' });
			} else {
				frappe.show_alert({ message: __('Recorded'), indicator: 'green' });
			}
			frm.reload_doc();
			if (m.quotation_note) { frappe.msgprint({title:__('Quotation review'),message:dcs_esc(m.quotation_note),indicator:'blue'}); }
		}
	});
}

function dcs_dialog(frm, title, fields, primary_label, handler) {
	var d = new frappe.ui.Dialog({
		title: __(title),
		fields: fields,
		primary_action_label: __(primary_label),
		primary_action: function (v) { handler(v, d); }
	});
	d.show();
}

function dcs_buttons(frm, s3, s4, s5) {
    dcs_obligation_buttons(frm);
	// Cancelled sheets are commercially dead - suppress all mutating actions.
	if (frm.doc.docstatus === 2) { return; }
	var cap = s3.capability || {}, auth = s5.authority || {}, st = s5.states || {}, lv = s5.living || {};
	var N = __('More actions'), A = N, W = N, H = N;
    var available = {};
    var route=((frm.__dcs || {}).s2 || {}).manager_route || ((frm.__dcs || {}).s4 || {}).manager_route || {};
    if (route.changed_by === ((frappe.session || {}).user) && route.approval_routing_error) {
        available['Refresh Manager Routing']=function(){dcs_run(frm,'dcs_refresh_manager_route',{dcs:frm.doc.name});};
        frm.add_custom_button(__('Route to my manager'),available['Refresh Manager Routing'],__('More actions'));
    }
    var add = function(label,handler,group) { available[label]=handler; return frm.add_custom_button(__(label === 'BOQ Revision' ? 'Revise BOQ' : label),handler,label === 'BOQ Revision' ? undefined : group); };


    var revision = function (side) {
        var isCust=side === 'Customer', position=dcs_effective_position(frm,s5), dialog;
        var preview=function() {
            if(!dialog) return;
            var cost=isCust ? position.cost : Number(dialog.get_value('new_total_cost'));
            var sell=isCust ? Number(dialog.get_value('new_total_selling')) : position.selling;
            var margin=sell > 0 ? 100*(sell-cost)/sell : null;
            dialog.fields_dict.preview.$wrapper.html('<div class="alert alert-info">Current buying ' + dcs_money(frm,position.cost) + ' · Selling ' + dcs_money(frm,position.selling)
                + '<br>Proposed buying <b>' + dcs_money(frm,cost) + '</b> · Selling <b>' + dcs_money(frm,sell) + '</b> · GP <b>' + dcs_money(frm,sell-cost)
                + '</b> · Margin ' + (margin === null ? 'Not priced' : dcs_pct(margin)) + '<br>Approval is recalculated on the server. Rejected revisions stay in history.</div>');
        };
        dialog=new frappe.ui.Dialog({
            title:__(isCust ? 'Customer Revision' : 'Vendor Revision'),
            fields:[
                {fieldtype:'Currency',fieldname:'new_total_selling',label:__('New Total Selling'),default:position.selling,hidden:!isCust,onchange:preview},
                {fieldtype:'Currency',fieldname:'new_total_cost',label:__('New Total Cost'),default:position.cost,hidden:isCust,onchange:preview},
                {fieldtype:'HTML',fieldname:'preview'},
                {fieldtype:'Small Text',fieldname:'reason',label:__('Reason'),reqd:1},
                {fieldtype:'Small Text',fieldname:'technical_impact',label:__('Technical Impact')}
            ],
            primary_action_label:__('Record Revision'),
            primary_action:function(v) {
                var args={dcs:frm.doc.name,source:side,reason:v.reason,technical_impact:v.technical_impact};
                if(isCust) args.new_total_selling=v.new_total_selling; else args.new_total_cost=v.new_total_cost;
                dcs_run(frm,'dcs_apply_revision',args,dialog);
            }
        });
        dialog.show();preview();
    };

    if (cap.can_negotiate && !dcs_effective_position(frm,s5).revision_no && dcs_effective_position(frm,s5).selling > 0) {
        add('Evaluate submitted BOQ',function(){dcs_run(frm,'dcs_apply_revision',{dcs:frm.doc.name,source:'Internal',reason:'Evaluate the submitted BOQ baseline without changing its totals.'});},N);
    }
	if (cap.can_customer_side && !s3.boq_managed) { add('Customer Revision', function () { revision('Customer'); }, N); }
	if (cap.can_vendor_side && !s3.boq_managed) { add('Vendor Revision', function () { revision('Vendor'); }, N); }
	if (frm.doc.docstatus === 1 && cap.can_negotiate && st.customer_award !== 'Awarded' && st.delivery_release !== 'Released' && st.delivery_release !== 'Released with MD Override') {
		add('BOQ Revision', function () { dcs_boq_revision_dialog(frm, cap); }, N);
	}
	if (!cap.can_negotiate && cap.denial_reason) {
		add('Why can I not negotiate?', function () {
			frappe.msgprint({ title: __('Negotiation authority'), message: dcs_esc(cap.denial_reason), indicator: 'orange' });
		}, N);
	}


    var decide=function(action) {
        var item=(s4.actions || []).filter(function(x){return x.key === action;})[0];
        if(!item) return;
        var consequence={Approve:'approved',Endorse:'endorsed','Return for Rework':'returned',Reject:'rejected'};
        dcs_dialog(frm,item.label || action,[
            {fieldtype:'Small Text',fieldname:'reason',label:__('Reason'),reqd:item.needs_reason ? 1 : 0},
            {fieldtype:'HTML',fieldname:'why',options:'<div class="text-muted small">' + dcs_esc((s4.consequences || {})[consequence[action]] || item.note || '') + '</div>'}
        ],item.label || action,function(v,d){dcs_run(frm,'dcs_approval_decision',{dcs:frm.doc.name,action:action,reason:v.reason},d);});
    };
    (s4.ok === 1 ? s4.actions || [] : []).forEach(function(item) {
        if(lv.approval_required && lv.approval_required !== 'None') add(item.key,function(){decide(item.key);},A);
    });

	var record_award = function (relabel) {
		dcs_dialog(frm, relabel || 'Record Award', [
			{ fieldtype: 'Data', fieldname: 'award_reference', label: __('Award Reference'), reqd: 1 },
			{ fieldtype: 'Select', fieldname: 'evidence_type', label: __('Evidence Type'), options: 'Customer PO\nLetter of Award\nEmail Confirmation\nVerbal - Not Evidenced\nNot Provided', reqd: 1 },
			{ fieldtype: 'Small Text', fieldname: 'notes', label: __('Notes') },
			{ fieldtype: 'HTML', fieldname: 'note', options: '<div class="text-muted small">Recording an award freezes the commercial baseline at the current living position. It does not release delivery.</div>' }
		], relabel || 'Record Award', function (v, d) {
			dcs_run(frm, 'dcs_record_award', { dcs: frm.doc.name, award_reference: v.award_reference, evidence_type: v.evidence_type, notes: v.notes }, d);
		});
	};
	if (auth.can_record_award && lv.authorised_position === 1 && st.customer_award !== 'Awarded') { add('Record Award', function () { record_award(); }, W); }
	if (st.customer_award === 'Awarded' && auth.can_override) {
		add('Reverse Award', function () {
			dcs_dialog(frm, 'Reverse Award', [
				{ fieldtype: 'Small Text', fieldname: 'reason', label: __('Reversal Reason'), reqd: 1 },
				{ fieldtype: 'Data', fieldname: 'evidence_reference', label: __('Evidence Reference') },
				{ fieldtype: 'Check', fieldname: 'acknowledge', label: __('I acknowledge that delivery release is stopped, the original award event remains immutable in history, and delivery already performed is not rolled back automatically'), reqd: 1 }
			], 'Reverse Award', function (v, d) {
				dcs_run(frm, 'dcs_award_reversal', { dcs: frm.doc.name, reason: v.reason, evidence_reference: v.evidence_reference, acknowledge: v.acknowledge ? 1 : 0, mode: 'reverse' }, d);
			});
		}, W);
	}
	if (st.award_reversal_state === 'Reversed' && auth.can_record_award && lv.authorised_position === 1) { add('Re-award', function () { record_award('Re-award'); }, W); }

	if (st.customer_award === 'Awarded' && auth.can_reconcile_po) add('Reconcile Customer PO', function () {
		var po = s5.po || {};
		dcs_dialog(frm, 'Reconcile Customer PO', [
			{ fieldtype: 'Data', fieldname: 'po_reference', label: __('PO Reference'), default: po.reference, reqd: 1 },
			{ fieldtype: 'Currency', fieldname: 'po_value', label: __('PO Value'), default: po.value, reqd: 1 },
			{ fieldtype: 'Data', fieldname: 'po_scope_revision', label: __('PO Scope Revision'), default: (s5.deal || {}).revision_reference, reqd: 1, description: __('Cite the full revision reference, for example DCS-Example-001-R4.') },
			{ fieldtype: 'Small Text', fieldname: 'po_payment_terms', label: __('PO Payment Terms'), default: po.payment_terms },
			{ fieldtype: 'Check', fieldname: 'payment_terms_accepted', label: __('Payment terms accepted by the commercial owner') }
		], 'Reconcile', function (v, d) {
			dcs_run(frm, 'dcs_po_reconcile', { dcs: frm.doc.name, po_reference: v.po_reference, po_value: v.po_value, po_scope_revision: v.po_scope_revision, po_payment_terms: v.po_payment_terms, payment_terms_accepted: v.payment_terms_accepted ? 1 : 0 }, d);
		});
	}, H);

	if (st.customer_award === 'Awarded' && auth.can_set_delivery_owner) add('Set Delivery Owner', function () {
		dcs_dialog(frm, 'Set Delivery Owner', [
			{ fieldtype: 'Link', fieldname: 'delivery_owner', label: __('Delivery Owner'), options: 'User', default: st.delivery_owner, reqd: 1 }
		], 'Set', function (v, d) { dcs_run(frm, 'dcs_set_delivery_owner', { dcs: frm.doc.name, delivery_owner: v.delivery_owner }, d); });
	}, H);

	var open_conds = (s5.projection === 'technical' ? s5.technical_conditions || [] : ((s5.conditions || {}).blockers || []).concat(((s5.conditions || {}).watch_items || []))).filter(function (x) {
        return x.state === 'Open' && (x.domain === 'Technical' ? auth.can_clear_technical : auth.can_clear_commercial);
    });
	if (open_conds.length) {
		add('Action a Condition', function () {
			dcs_dialog(frm, 'Handover Condition', [
				{ fieldtype: 'Select', fieldname: 'condition', label: __('Condition'), options: open_conds.map(function (x) { return x.name; }).join('\n'), reqd: 1 },
				{ fieldtype: 'Select', fieldname: 'action', label: __('Action'), options: auth.can_override ? 'Clear\nAssign\nAccept Risk' : 'Clear\nAssign', reqd: 1 },
				{ fieldtype: 'Small Text', fieldname: 'note', label: __('Note'), reqd: 1 },
				{ fieldtype: 'Link', fieldname: 'assign_to', label: __('Assign To'), options: 'User' },
				{ fieldtype: 'Check', fieldname: 'acknowledged', label: __('Acknowledged (required to accept a risk)') }
			], 'Apply', function (v, d) {
				dcs_run(frm, 'dcs_handover_action', { condition: v.condition, action: v.action, note: v.note, assign_to: v.assign_to, acknowledged: v.acknowledged ? 1 : 0 }, d);
			});
		}, H);
	}

	if (auth.can_release && st.customer_award === 'Awarded' && (st.delivery_release || '').indexOf('Released') !== 0) {
		add('Release to Delivery', function () {
			dcs_dialog(frm, 'Release to Delivery', [
				{ fieldtype: 'Check', fieldname: 'override', label: __('Exceptional Managing Director override'), hidden: !auth.can_override },
				{ fieldtype: 'Small Text', fieldname: 'reason', label: __('Override Reason'), depends_on: 'override' },
				{ fieldtype: 'Check', fieldname: 'acknowledged', label: __('I acknowledge each overridden blocker remains unresolved and is carried as an accepted risk'), depends_on: 'override' },
				{ fieldtype: 'Small Text', fieldname: 'note', label: __('Release Note') }
			], 'Release', function (v, d) {
				dcs_run(frm, 'dcs_delivery_release', { dcs: frm.doc.name, override: v.override ? 1 : 0, reason: v.reason, acknowledged: v.acknowledged ? 1 : 0, note: v.note }, d);
			});
		}, H);
	}

	// Governed Actions - NAVIGATION ONLY. These buttons carry no authority whatsoever.
	// They open the governed surface with this Deal Cost Sheet preselected; the server
	// service alone decides what may actually be done there. Presentation reuses the
	// projections already returned above so a user is not sent to a surface that will
	// refuse them outright. No permission rule is reimplemented on the client.
	var G = __('More actions');
	var dcs_portal = function (path) { window.open(path + '?dcs=' + encodeURIComponent(frm.doc.name), '_blank'); };
	add('Working View', function () { dcs_portal('/living-dcs'); }, G);
	if (s3 && s3.ok) { add('Negotiation & Revision', function () { dcs_portal('/negotiation-workspace'); }, G); }
	if (s4 && s4.ok) { add('Approval', function () { dcs_portal('/approval-workspace'); }, G); }
	if (s5 && s5.ok) { add('Award & Handover (PO, Delivery, Reversal)', function () { dcs_portal('/award-handover'); }, G); }
	add('DCS Governance Workspace', function () { frappe.set_route('dcs-governance'); }, G);


	// Governed Documents - NAVIGATION ONLY, exactly like the group above.
	// dcs_print_document decides the audience server-side and builds the technical pack from a
	// non-commercial allowlist, so a wrong turn here produces a refusal, never a leak.
	// Presentation follows the projection already returned; it is not a permission rule.
	var D = __('More actions');
	var dcs_doc_out = function (kind) {
		window.open('/dcs-document?dcs=' + encodeURIComponent(frm.doc.name) + '&kind=' + kind, '_blank');
	};
	var dproj = (s5 && s5.projection) || (s4 && s4.projection) || (s3 && s3.projection) || '';
	if (dproj !== 'technical' && dproj !== 'reduced') {
		add('Commercial Deal Cost Sheet', function () { dcs_doc_out('commercial'); }, D);
		add('Award & Reversal Evidence', function () { dcs_doc_out('award'); }, D);
	}
	add('Technical / Operations Handover', function () { dcs_doc_out('handover'); }, D);

    var next=dcs_next_step(frm,s3,s4,s5);
    if(frm.doc.docstatus === 1 && !frm.is_dirty() && next.key && available[next.key]) {
        frm.page.set_primary_action(__(next.label),available[next.key]);
    }
}


// DCS Items Grid - Description Clarity Hint
// Purpose: Clarify that the "Description" column in the Items grid is the
// editable text used for the Quotation output, distinguishing it from the
// Item Code column (which auto-displays the linked Item's name).
// This script ONLY changes label/tooltip text - it does NOT alter any data,
// fetch logic, or the value used for the Quotation.
frappe.ui.form.on('Deal Cost Sheet', {
    refresh: function(frm) {
        if (!frm.fields_dict.items || !frm.fields_dict.items.grid) return;
        var grid = frm.fields_dict.items.grid;
        try {
            grid.update_docfield_property('description', 'label', 'Description (for Quotation)');
            grid.update_docfield_property('description', 'description', 'Defaults to Item Code + Name. Edit this text as needed - it is what appears on the Quotation.');
        } catch (e) {
            console.error('DCS Items Grid Description Hint error:', e);
        }
    }
});



// Governed submitted BOQ editor. The ordinary form remains locked.
function dcs_boq_revision_dialog(frm, cap) {
    var both = cap.can_customer_side && cap.can_vendor_side;
    var d;
    var preview = function () {
        if (!d) return;
        var items = d.get_value('boq_items') || [], labour = d.get_value('boq_resources') || [];
        var totals=dcs_boq_totals(items,labour,frm.doc.addtional_charges);
        var cost=totals.cost, sell=totals.selling;
        if (!cap.can_customer_side) {
            d.fields_dict.preview.$wrapper.html('<div class="alert alert-info">Derived cost: <b>' + format_currency(cost, frm.doc.currency,dcs_money_precision(frm)) + '</b>. Selling is preserved and margin is re-evaluated on the server.</div>');
            return;
        }
        d.fields_dict.preview.$wrapper.html('<div class="alert alert-info">Derived cost: <b>' + format_currency(cost, frm.doc.currency,dcs_money_precision(frm)) + '</b> · Selling: <b>' + format_currency(sell, frm.doc.currency,dcs_money_precision(frm)) + '</b> · GP: <b>' + format_currency(sell-cost, frm.doc.currency,dcs_money_precision(frm)) + '</b> · Margin: ' + (totals.margin === null ? 'Not priced' : totals.margin.toFixed(2) + '%') + '</div>');
    };
    var f = function (type, name, label, options, readonly) {
        return {fieldtype:type, fieldname:name, label:__(label), options:options, in_list_view:1, read_only:readonly ? 1 : 0, onchange:preview};
    };
    var itemFields = [
        {fieldtype:'Data',fieldname:'row_name',hidden:1},
        f('Link','item_code','Item','Item',!both), f('Text Editor','description','Description',null,!both),
        f('Float','qty','Qty',null,!both), f('Currency','cost_rate','Cost Rate',null,!cap.can_vendor_side),
        f('Currency','selling_rate','Selling Rate',null,!cap.can_customer_side)
    ];
    var resourceFields = [
        {fieldtype:'Data',fieldname:'row_name',hidden:1},
        f('Select','resource_type','Type','Internal\nOutsourced',!cap.can_vendor_side),
        f('Data','role','Role',null,!cap.can_vendor_side),
        f('Float','no_of_persons','Persons',null,!cap.can_vendor_side),
        f('Float','no_of_days','Days',null,!cap.can_vendor_side),
        f('Float','hours','Total hours (if days not used)',null,!cap.can_vendor_side),
        f('Currency','cost_rate','Cost Rate',null,!cap.can_vendor_side),
        f('Small Text','remarks','Remarks',null,!cap.can_vendor_side)
    ];
    itemFields.filter(function (field) { return field.fieldname === 'selling_rate'; }).forEach(function (field) { field.hidden = !cap.can_customer_side; });
    var fields = function (rows, names) {
        return (rows || []).map(function (r) {
            var v={row_name:r.name}; names.forEach(function (key) { v[key]=r[key]; }); return v;
        });
    };
    var itemKeys=['item_code','description','qty','cost_rate','selling_rate'];
    var resourceKeys=['resource_type','role','no_of_persons','no_of_days','hours','cost_rate','remarks'];
    var gapCost = flt(frm.doc.custom_working_total_cost)-flt(frm.doc.total_cost);
    var gapSell = flt(frm.doc.custom_working_total_selling)-flt(frm.doc.total_selling);
    var gap = cint(frm.doc.custom_dcs_revision_no)>0 && (Math.abs(gapCost)>0.005 || Math.abs(gapSell)>0.005);
    d = new frappe.ui.Dialog({
        title:__('BOQ Revision'), size:'extra-large',
        fields:[
            {fieldtype:'HTML',fieldname:'notice',options:'<p>Revise items and labour on this submitted sheet. Totals are derived from the rows. Approval and margin gates are re-evaluated; this does not award or release delivery. Additional charges remain unchanged. Labour uses persons × days × rate; when persons/days are not supplied, it uses total hours × rate.</p>' + (gap ? '<div class="alert alert-warning">Earlier totals-only adjustments differ from these rows: cost ' + format_currency(gapCost,frm.doc.currency,dcs_money_precision(frm)) + ', selling ' + format_currency(gapSell,frm.doc.currency,dcs_money_precision(frm)) + '. MD reconciliation is required.</div>' : '')},
            {fieldtype:'Select',fieldname:'source',label:__('Source'),options:'Vendor\nCustomer\nTechnical\nInternal',reqd:1},
            {fieldtype:'Small Text',fieldname:'reason',label:__('Reason'),reqd:1},
            {fieldtype:'Small Text',fieldname:'technical_impact',label:__('Technical Impact')},
            {fieldtype:'Table',fieldname:'boq_items',label:__('Items'),fields:itemFields,data:fields(frm.doc.items,itemKeys),cannot_add_rows:!both,cannot_delete_rows:!both,onchange:preview},
            {fieldtype:'Table',fieldname:'boq_resources',label:__('Labour / Resources'),fields:resourceFields,data:fields(frm.doc.resources,resourceKeys),cannot_add_rows:!cap.can_vendor_side,cannot_delete_rows:!cap.can_vendor_side,onchange:preview},
            {fieldtype:'HTML',fieldname:'preview'},
            {fieldtype:'Check',fieldname:'reconcile_header_adjustments',label:__('Replace earlier totals-only adjustments with this complete BOQ'),hidden:!gap || !frappe.user.has_role('Managing Director'),description:__('No hidden adjustment is carried forward. Ensure every intended cost and selling change is represented above.')},
            {fieldtype:'Check',fieldname:'update_quotation',label:__('Update the linked Draft Quotation from this BOQ'),description:__('Requires Quotation write permission. Only this sheet’s verified Draft Quotation may be updated; otherwise the entire revision is refused.')},
            {fieldtype:'Check',fieldname:'acknowledge_quote_review',label:__('Keep the existing quotation for separate review'),description:__('Required if quoted scope/selling changes and you are not updating the Draft Quotation. The sheet will return from Quoted to Submitted to Sales; Won/Lost outcomes are preserved.'),hidden:!frm.doc.custom_quotation}
        ],
        primary_action_label:__('Record BOQ Revision'),
        primary_action:function (v) {
            var clean=function(rows,keys,isItem){return rows.map(function(r){
                var out={row_name:r.row_name || ''}; keys.forEach(function(k){
                    if (isItem && ((k==='cost_rate' && !cap.can_vendor_side) || (k==='selling_rate' && !cap.can_customer_side))) return;
                    if (!isItem && k==='cost_rate' && !cap.can_vendor_side) return;
                    out[k]=r[k];
                }); return out;
            });};
            dcs_run(frm,'dcs_apply_boq_revision',{
                dcs:frm.doc.name,expected_modified:frm.doc.modified,source:v.source,reason:v.reason,
                technical_impact:v.technical_impact,items:clean(v.boq_items || [],itemKeys,true),
                resources:clean(v.boq_resources || [],resourceKeys,false),
                reconcile_header_adjustments:v.reconcile_header_adjustments || 0,update_quotation:v.update_quotation || 0,
                acknowledge_quote_review:v.acknowledge_quote_review || 0
            },d);
        }
    });
    d.show(); preview();
}
function dcs_refresh_draft(frm) {
    if (dcs_is_draft(frm)) render_summary_dashboard(frm);
}
frappe.ui.form.on('Deal Cost Sheet', {
    organisation_name: dcs_refresh_draft, customer: dcs_refresh_draft,
    subject: dcs_refresh_draft, items_remove: dcs_refresh_draft,
    resources_remove: dcs_refresh_draft, addtional_charges_remove: dcs_refresh_draft
});
frappe.ui.form.on('Deal Cost Item', {
    qty: dcs_refresh_draft, cost_rate: dcs_refresh_draft, selling_rate: dcs_refresh_draft
});
frappe.ui.form.on('Deal Cost Resource', {
    no_of_persons: dcs_refresh_draft, no_of_days: dcs_refresh_draft,
    hours: dcs_refresh_draft, cost_rate: dcs_refresh_draft
});
frappe.ui.form.on('Additional Charges Item', {
    amount: dcs_refresh_draft, selling_amount: dcs_refresh_draft
});

function dcs_account_labels(frm) {
    var label = frm.doc.party_type === 'Customer' ? __('Customer')
        : frm.doc.party_type === 'Lead' ? __('Lead') : __('Account');
    frm.set_df_property('party', 'label', label);
    // Older sheets can have a Customer link without the newer account fields.
    // Show that native read-only link until a complete primary account is present.
    var has_account = !!frm.doc.party && ['Lead','Customer'].includes(frm.doc.party_type);
    frm.toggle_display('customer', !!frm.doc.customer && !has_account);
}

function dcs_fetch_party_details(frm) {
    if (frm.doc.docstatus !== 0 || !frm.doc.party || !['Lead','Customer'].includes(frm.doc.party_type)) return;
    var type=frm.doc.party_type, party=frm.doc.party;
    var fields=type === 'Customer' ? ['customer_name','territory'] : ['company_name','lead_name','territory'];
    return frappe.db.get_value(type, party, fields).then(function(r) {
        if (frm.doc.party_type !== type || frm.doc.party !== party || !r.message) return;
        var data=r.message;
        return frm.set_value({
            organisation_name: type === 'Customer' ? (data.customer_name || party) : (data.company_name || data.lead_name || party),
            customer:type === 'Customer' ? party : '',
            territory:frm.doc.territory || data.territory || ''
        });
    });
}
frappe.ui.form.on('Deal Cost Sheet', {
    refresh:dcs_account_labels,
    customer:dcs_account_labels,
    party:function(frm) {
        dcs_account_labels(frm);
        return dcs_fetch_party_details(frm);
    },
    party_type:function(frm) {
        dcs_account_labels(frm);
        if (frm.doc.docstatus !== 0) return;
        frm.set_value({customer:'', organisation_name:''});
        dcs_fetch_party_details(frm);
    }
});
function dcs_company_selection(frm, info) {
    frm.toggle_display('company', false);
    if (frm.doc.docstatus === 0 && !info.hide_company &&
            frm.fields_dict.company && !frm.fields_dict.company.df.read_only) {
        frm.add_custom_button(__('Change company'), function() {
            frm.toggle_display('company', true);
            if (frm.scroll_to_field) frm.scroll_to_field('company');
        }, __('More actions'));
    }
}
function dcs_company_identity(frm) {
    if (!frm.page || !frm.page.get_title_area) return;
    var company = frm.doc.company || '';
    var cache = frm.__dcs_company_identity;
    if (cache && cache.company === company) {
        if (cache.info) dcs_company_selection(frm, cache.info);
        return cache.promise;
    }
    // Retain the selector until the selected company's identity is confirmed.
    frm.toggle_display('company', true);
    var area = frm.page.get_title_area();
    area.find('.dcs-country-badge').remove();
    var entry = {company:company};
    frm.__dcs_company_identity = entry;
    entry.promise = frappe.call({
        method:'bsgroup.api.dcs.presentation.company_context', args:{company:company || null}
    }).then(function(r) {
        if (frm.__dcs_company_identity !== entry || (frm.doc.company || '') !== company) return;
        var info = r.message || {};
        if (!info.company) return;
        if (!company && frm.is_new()) {
            return frm.set_value('company', info.company);
        }
        if (info.company !== frm.doc.company) return;
        entry.info = info;
        dcs_company_selection(frm, info);
        var label = ['Bits Secure', info.country_label, info.base_currency].filter(Boolean).join(' · ');
        var badge = $('<span class="dcs-country-badge" role="status"></span>');
        badge.text(label).attr('title', info.company + ' · Base currency: ' + info.base_currency);
        badge.toggleClass('dcs-country-oman', info.country === 'Oman');
        area.append(badge);
    }).catch(function() {
        if (frm.__dcs_company_identity === entry) {
            frm.__dcs_company_identity = null;
            frm.toggle_display('company', true);
        }
    });
    return entry.promise;
}
frappe.ui.form.on('Deal Cost Sheet', {
    refresh:dcs_company_identity,
    company:dcs_company_identity
});

// Phase C. Server projection controls whether these controls exist at all.
function dcs_obligation_call(method, args) {
    return frappe.call({method:'bsgroup.dcs.obligation.'+method,args:args}).then(function(r){return r.message;});
}
function dcs_obligation_render(frm) {
    var s=frm.__obligation;
    if(!s || !s.financials) return;
    var field=frm.fields_dict.custom_deal_summary_dashboard;
    // Locate the existing Overview panel without adding a DocField or permanent tab.
    var parent=$(frm.wrapper).find('.dcs-overview').first();
    $(frm.wrapper).find('.dcs-confidential').remove();
    if(!field) return;
    if(!parent.length) parent=field.$wrapper;
    var f=s.financials, esc=dcs_esc, money=function(v){return esc(f.currency)+' '+format_number(v,null,f.currency==='OMR'?3:2);};
    var rows=[['Customer selling',f.selling],['Delivery buying cost',f.delivery_cost],
        ['Delivery contribution',f.delivery_contribution],['Forecast obligations',f.forecast_obligations],
        ['Approved commitments',f.approved_commitments],['Approved net contribution',f.approved_net_contribution],['Forecast net contribution',f.forecast_net_contribution]];
    var html='<section class="dcs-confidential" style="border-top:1px solid var(--border-color);margin-top:24px;padding-top:20px">'
      +'<div class="dcs-eyebrow">RESTRICTED · FINANCE &amp; COMMERCIAL GOVERNANCE</div><h3>Commercial obligations</h3>'
      +'<p>Review status: '+(s.obligations || []).map(function(o){return esc(o.status==='Approved'&&!o.current?'Review required':o.status);}).join(' · ')+'</p>'
      +'<p class="text-muted small">Saved commercial position. Forecast is not an approved payment commitment.</p>'
      +'<table class="table table-bordered"><tbody>'+rows.map(function(r){return '<tr><th>'+r[0]+'</th><td class="text-right">'+money(r[1])+'</td></tr>';}).join('')
      +'<tr><th>Forecast net margin</th><td class="text-right">'+(f.forecast_net_margin===null?'Not priced':f.forecast_net_margin.toFixed(2)+'%')+'</td></tr></tbody></table>'
      +'<button type="button" class="btn btn-default btn-sm">View Commercial Obligation</button></section>';
    var section=$(html);section.find('button').on('click',function(){dcs_obligation_list(frm);});parent.append(section);
}
function dcs_obligation_refresh(frm) {
    frm.__obligation=null;
    $(frm.wrapper).find('.dcs-confidential').remove();
    if(frm.is_new()) return Promise.resolve();
    var name=frm.doc.name, token={};frm.__obligation_request=token;
    return dcs_obligation_call('overview',{dcs:name}).then(function(s){
        if(frm.doc.name!==name || frm.__obligation_request!==token) return;
        frm.__obligation=s;dcs_obligation_render(frm);dcs_obligation_buttons(frm);
    });
}
function dcs_obligation_buttons(frm) {
    if(!frm.__obligation || !frm.__obligation.can_record) return;
    frm.add_custom_button(__('Record Commercial Obligation'),function(){dcs_obligation_edit(frm);},__('Actions'));
    if((frm.__obligation.obligations || []).length) {
        frm.add_custom_button(__('View Commercial Obligation'),function(){dcs_obligation_list(frm);},__('Actions'));
    }
}
function dcs_obligation_edit(frm, doc) {
    doc=doc || {};
    var fields=[
        {fieldname:'obligation_type',fieldtype:'Select',label:'Obligation type',options:'Consulting\nPartner Fee\nOther',reqd:1,default:doc.obligation_type || 'Consulting'},
        {fieldname:'payee',fieldtype:'Data',label:'Payee',reqd:1,default:doc.payee},
        {fieldname:'agreement_reference',fieldtype:'Data',label:'Agreement reference',reqd:1,default:doc.agreement_reference},
        {fieldname:'calculation_method',fieldtype:'Select',label:'Calculation method',options:'Fixed amount\nPercentage of customer selling',default:doc.calculation_method || 'Fixed amount',reqd:1},
        {fieldname:'fixed_amount',fieldtype:'Currency',label:'Fixed amount ('+frm.doc.currency+')',precision:dcs_money_precision(frm),default:doc.fixed_amount},
        {fieldname:'percentage',fieldtype:'Float',label:'Percentage of customer selling',precision:6,default:doc.percentage},
        {fieldname:'payment_conditions',fieldtype:'Small Text',label:'Payment conditions',default:doc.payment_conditions},
        {fieldname:'reason',fieldtype:'Small Text',label:'Reason for this revision',reqd:1}
    ];
    var d=new frappe.ui.Dialog({title:doc.name?'Revise commercial obligation':'Record commercial obligation',
        fields:fields,primary_action_label:'Save forecast draft',primary_action:function(v){
            d.disable_primary_action();
            dcs_obligation_call('save_proposal',{dcs:frm.doc.name,name:doc.name,expected_revision:doc.revision,values:JSON.stringify(v)})
            .then(function(r){d.hide();return dcs_obligation_refresh(frm).then(function(){dcs_obligation_detail(frm,r.name);});})
            .finally(function(){d.enable_primary_action();});
        }});
    d.show();
}
function dcs_obligation_list(frm) {
    dcs_obligation_refresh(frm).then(function(){
        var rows=(frm.__obligation || {}).obligations || [], esc=dcs_esc;
        if(!rows.length) return;
        var d=new frappe.ui.Dialog({title:'Commercial obligations · Restricted',fields:[{fieldname:'list',fieldtype:'HTML'}]});
        var box=d.fields_dict.list.$wrapper;
        box.html('<table class="table"><thead><tr><th>Payee</th><th>Status</th><th>Forecast</th><th>Approved</th><th></th></tr></thead><tbody>'
            +rows.map(function(r,i){return '<tr><td>'+esc(r.payee)+'</td><td>'+esc(r.status)+(r.status==='Approved'&&!r.current?' · Review required':'')
            +'</td><td>'+dcs_money(frm,r.amount)+'</td><td>'+dcs_money(frm,r.approved_amount)+'</td><td><button class="btn btn-default btn-xs" data-index="'+i+'">Open</button></td></tr>';}).join('')+'</tbody></table>');
        box.find('button').on('click',function(){var row=rows[Number($(this).attr('data-index'))];d.hide();dcs_obligation_detail(frm,row.name);});
        d.show();
    });
}
function dcs_obligation_detail(frm, name) {
    dcs_obligation_call('detail',{name:name}).then(function(r){
        var o=r.obligation, esc=dcs_esc, f=r.financials;
        var d=new frappe.ui.Dialog({title:'Commercial obligation · '+o.status,size:'large',fields:[
            {fieldname:'details',fieldtype:'HTML'},{fieldname:'history',fieldtype:'HTML'}]});
        d.fields_dict.details.$wrapper.html('<p><b>'+esc(o.payee)+'</b> · '+esc(o.obligation_type)+' · '+esc(o.agreement_reference)+'</p>'
          +'<p>'+esc(o.payment_conditions || '')+'</p><p>Forecast net contribution: <b>'+dcs_money(frm,f.forecast_net_contribution)+'</b> · Net margin: '
          +(f.forecast_net_margin===null?'Not priced':f.forecast_net_margin.toFixed(2)+'%')+'</p>'
          +'<p>Approved commitment: '+dcs_money(frm,o.approved_amount)+' · Revision '+o.revision+'</p>'
          +(o.approved_snapshot?'<details><summary>Approved terms</summary><pre>'+esc(JSON.stringify(JSON.parse(o.approved_snapshot),null,2))+'</pre></details>':'')
          +(o.status==='Approved'&&!r.current?'<p class="text-danger">Commercial position changed. A new approval is required.</p>':''));
        d.fields_dict.history.$wrapper.html('<h4>Private approval history</h4><table class="table"><tbody>'
          +r.history.map(function(e){return '<tr><td>R'+e.revision+'</td><td>'+esc(e.action)+'</td><td>'+esc(e.actor)+'</td><td>'+esc(e.reason)+'</td><td>'+esc(e.occurred_on)+'</td></tr>';}).join('')+'</tbody></table>');
        $('<p>').text('Recorded accrued: '+dcs_money(frm,o.accrued_amount || 0)+' · Recorded paid: '+dcs_money(frm,o.paid_amount || 0)+' · Balance: '+dcs_money(frm,(o.approved_amount || 0)-(o.paid_amount || 0))).appendTo(d.fields_dict.details.$wrapper);
        if(r.can_settle && o.status==='Approved' && r.current) {
            d.add_custom_action('Record settlement evidence',function(){
                frappe.prompt([{fieldname:'accrued_amount',fieldtype:'Currency',label:'Cumulative accrued',default:o.accrued_amount,reqd:1},
                  {fieldname:'paid_amount',fieldtype:'Currency',label:'Cumulative paid',default:o.paid_amount || 0,reqd:1},
                  {fieldname:'reference',fieldtype:'Data',label:'Evidence reference',reqd:1}],function(v){
                    dcs_obligation_call('record_settlement',Object.assign({name:name,expected_revision:o.revision},v)).then(function(){d.hide();dcs_obligation_detail(frm,name);});
                },'Record settlement evidence · Does not execute payment','Record');
            });
        }
        var act=function(action){frappe.prompt([{fieldname:'reason',fieldtype:'Small Text',label:'Decision reason',reqd:1}],function(v){
            dcs_obligation_call('transition',{name:name,action:action,expected_revision:o.revision,reason:v.reason})
            .then(function(){d.hide();dcs_obligation_refresh(frm);dcs_obligation_detail(frm,name);});
        },action,action);};
        d.add_custom_action('Revise proposal',function(){d.hide();dcs_obligation_edit(frm,o);});
        if(o.status==='Draft') d.set_primary_action('Submit for approval',function(){act('Submit');});
        if(o.status==='Pending Finance'&&r.can_finance) d.set_primary_action('Finance approve',function(){act('Finance Approve');});
        if(o.status==='Pending MD'&&r.can_md) d.set_primary_action('MD approve',function(){act('MD Approve');});
        if((o.status==='Pending Finance'&&r.can_finance)||(o.status==='Pending MD'&&r.can_md)) {
            d.add_custom_action('Reject',function(){act('Reject');});
        }
        var files=r.files || [];
        var filebox=$('<div>').appendTo(d.fields_dict.details.$wrapper);
        files.forEach(function(file){$('<p>').append($('<a target="_blank" rel="noopener">').attr('href',file.file_url).text(file.file_name+' · Private')).appendTo(filebox);});
        var upload=$('<input type="file" aria-label="Private supporting document">').appendTo(filebox);
        upload.on('change',function(){
            var file=this.files[0];if(!file) return;
            if(file.size>10000000) {frappe.msgprint('Choose a supporting file up to 10 MB.');return;}
            var reader=new FileReader();reader.onload=function(){
                dcs_obligation_call('upload_support',{name:name,filename:file.name,content:String(reader.result).split(',')[1]})
                .then(function(){d.hide();dcs_obligation_detail(frm,name);});
            };reader.readAsDataURL(file);
        });
        d.show();
    });
}
frappe.ui.form.on('Deal Cost Sheet',{refresh:function(frm){dcs_obligation_refresh(frm);}});
