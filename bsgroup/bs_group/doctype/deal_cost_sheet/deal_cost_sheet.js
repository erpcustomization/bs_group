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
			}, "Create");
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
							'<td style="padding:4px 8px;border:1px solid #e0e0e0;text-align:right;">AED ' + parseFloat(v.total_cost || 0).toLocaleString() + '</td>' +
							'<td style="padding:4px 8px;border:1px solid #e0e0e0;text-align:right;">AED ' + parseFloat(v.total_selling || 0).toLocaleString() + '</td>' +
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
		set_item_category(frm, cdt, cdn).then(() => {
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
		frappe.db.get_value("Company", frm.doc.company, "default_currency").then(r => {
			const currency = (r.message && r.message.default_currency) || "AED";
			frm.doc.currency = currency;
			propagate_currency(frm, currency);
			render_summary(frm, currency);
		});
	} else {
		render_summary(frm, frm.doc.currency || "AED");
	}
}

function propagate_currency(frm, currency) {
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

	const fmt = (val) => format_currency(flt(val), currency);
	const pct = (val) => flt(val, 2).toFixed(2) + "%";

	const can_see_selling = frappe.user.has_role(["Sales Manager", "Sales User", "System Manager"]);

	const prod_cost       = flt(doc.products_cost_total);
	const prod_sell       = flt(doc.products_selling_total);
	const prod_margin     = prod_sell - prod_cost;
	const prod_margin_pct = prod_cost ? ((prod_sell / prod_cost) - 1) * 100 : 0;

	const svc_cost        = flt(doc.services_cost_total);
	const svc_sell        = flt(doc.services_selling_total);
	const svc_margin      = svc_sell - svc_cost;
	const svc_margin_pct  = svc_cost ? ((svc_sell / svc_cost) - 1) * 100 : 0;

	let charges_total = 0;
	(doc.addtional_charges || []).forEach(row => {
		charges_total += flt(row.amount);
	});

	let resource_cost_total = 0;
	(doc.resources || []).forEach(row => {
		resource_cost_total += flt(row.cost_amount);
	});

	const total_cost_calc    = prod_cost + svc_cost + charges_total + resource_cost_total;
	const total_selling_calc = prod_sell + svc_sell;
	const total_margin_calc  = total_selling_calc - total_cost_calc;
	const total_margin_pct   = total_cost_calc ? ((total_selling_calc / total_cost_calc) - 1) * 100 : 0;

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
				Commercial Summary
			</div>
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
						${can_see_selling ? td(pct(prod_margin_pct)) : ""}
					</tr>
					<tr style="border-bottom:1px solid #e2e8f0;">
						${td_label("Services")}
						${td(fmt(svc_cost))}
						${can_see_selling ? td(fmt(svc_sell)) : ""}
						${can_see_selling ? td(fmt(svc_margin)) : ""}
						${can_see_selling ? td(pct(svc_margin_pct)) : ""}
					</tr>
					<tr style="border-bottom:1px solid #e2e8f0;">
						${td_label("Additional Charges")}
						${td(fmt(charges_total))}
						${can_see_selling ? td("-") : ""}
						${can_see_selling ? td("-") : ""}
						${can_see_selling ? td("-") : ""}
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
						${can_see_selling ? td(pct(total_margin_pct), true) : ""}
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

	const r = await frappe.db.get_value("Item", row.item_code, "is_stock_item");
	const is_stock_item = r.message && r.message.is_stock_item;

	const category = is_stock_item ? "Products" : "Professional Services";
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
	const total_selling = products_selling_total + services_selling_total;
	const margin_value = total_selling - total_cost;
	const margin_percent = total_cost ? ((total_selling / total_cost) - 1) * 100 : 0;

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
                    frm.set_value("customer", res.message.custom_organization_name);
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