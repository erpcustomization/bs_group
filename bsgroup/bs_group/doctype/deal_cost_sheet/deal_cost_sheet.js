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
	const prod_margin_pct = prod_sell ? (prod_margin / prod_sell) * 100 : 0;

	const svc_cost        = flt(doc.services_cost_total);
	const svc_sell        = flt(doc.services_selling_total);
	const svc_margin      = svc_sell - svc_cost;
	const svc_margin_pct  = svc_sell ? (svc_margin / svc_sell) * 100 : 0;

	let charges_total = 0;
	(doc.addtional_charges || []).forEach(row => {
		charges_total += flt(row.amount);
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
const AED_TO_OMR = 0.1023;

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
        }, __('<img src="data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAxMDAgMTAwIiB3aWR0aD0iMTYiIGhlaWdodD0iMTYiPjxkZWZzPjxyYWRpYWxHcmFkaWVudCBpZD0iYWlyYWciIGN4PSI1MCUiIGN5PSI2MCUiIHI9IjU1JSIgZng9IjUwJSIgZnk9IjcwJSI+PHN0b3Agb2Zmc2V0PSIwJSIgc3RvcC1jb2xvcj0iIzAwZTVjYyIvPjxzdG9wIG9mZnNldD0iNTAlIiBzdG9wLWNvbG9yPSIjM2I2ZWY4Ii8+PHN0b3Agb2Zmc2V0PSIxMDAlIiBzdG9wLWNvbG9yPSIjN2IzZmU0Ii8+PC9yYWRpYWxHcmFkaWVudD48L2RlZnM+PGNpcmNsZSBjeD0iNTAiIGN5PSI1MCIgcj0iNDgiIGZpbGw9InVybCgjYWlyYWcpIi8+PHBhdGggZD0iTTI1IDc1IEw1MCAyNSBMNzUgNzUiIHN0cm9rZT0id2hpdGUiIHN0cm9rZS13aWR0aD0iMTAiIHN0cm9rZS1saW5lY2FwPSJyb3VuZCIgc3Ryb2tlLWxpbmVqb2luPSJyb3VuZCIgZmlsbD0ibm9uZSIvPjxwb2x5Z29uIHBvaW50cz0iNTAsNTIgNTMsNTggNTksNTggNTQsNjIgNTYsNjggNTAsNjQgNDQsNjggNDYsNjIgNDEsNTggNDcsNTgiIGZpbGw9IndoaXRlIiBvcGFjaXR5PSIwLjkiLz48L3N2Zz4=" style="width:16px;height:16px;vertical-align:middle;margin-right:4px;border-radius:50%"> AIRA'));

        frm.add_custom_button(__('💰 Price Suggestions'), () => {
            dcs_ai_price_suggestions(frm);
        }, __('<img src="data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAxMDAgMTAwIiB3aWR0aD0iMTYiIGhlaWdodD0iMTYiPjxkZWZzPjxyYWRpYWxHcmFkaWVudCBpZD0iYWlyYWciIGN4PSI1MCUiIGN5PSI2MCUiIHI9IjU1JSIgZng9IjUwJSIgZnk9IjcwJSI+PHN0b3Agb2Zmc2V0PSIwJSIgc3RvcC1jb2xvcj0iIzAwZTVjYyIvPjxzdG9wIG9mZnNldD0iNTAlIiBzdG9wLWNvbG9yPSIjM2I2ZWY4Ii8+PHN0b3Agb2Zmc2V0PSIxMDAlIiBzdG9wLWNvbG9yPSIjN2IzZmU0Ii8+PC9yYWRpYWxHcmFkaWVudD48L2RlZnM+PGNpcmNsZSBjeD0iNTAiIGN5PSI1MCIgcj0iNDgiIGZpbGw9InVybCgjYWlyYWcpIi8+PHBhdGggZD0iTTI1IDc1IEw1MCAyNSBMNzUgNzUiIHN0cm9rZT0id2hpdGUiIHN0cm9rZS13aWR0aD0iMTAiIHN0cm9rZS1saW5lY2FwPSJyb3VuZCIgc3Ryb2tlLWxpbmVqb2luPSJyb3VuZCIgZmlsbD0ibm9uZSIvPjxwb2x5Z29uIHBvaW50cz0iNTAsNTIgNTMsNTggNTksNTggNTQsNjIgNTYsNjggNTAsNjQgNDQsNjggNDYsNjIgNDEsNTggNDcsNTgiIGZpbGw9IndoaXRlIiBvcGFjaXR5PSIwLjkiLz48L3N2Zz4=" style="width:16px;height:16px;vertical-align:middle;margin-right:4px;border-radius:50%"> AIRA'));

        frm.add_custom_button(__('📊 Compare Proposals'), () => {
            dcs_ai_compare_proposals(frm);
        }, __('<img src="data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAxMDAgMTAwIiB3aWR0aD0iMTYiIGhlaWdodD0iMTYiPjxkZWZzPjxyYWRpYWxHcmFkaWVudCBpZD0iYWlyYWciIGN4PSI1MCUiIGN5PSI2MCUiIHI9IjU1JSIgZng9IjUwJSIgZnk9IjcwJSI+PHN0b3Agb2Zmc2V0PSIwJSIgc3RvcC1jb2xvcj0iIzAwZTVjYyIvPjxzdG9wIG9mZnNldD0iNTAlIiBzdG9wLWNvbG9yPSIjM2I2ZWY4Ii8+PHN0b3Agb2Zmc2V0PSIxMDAlIiBzdG9wLWNvbG9yPSIjN2IzZmU0Ii8+PC9yYWRpYWxHcmFkaWVudD48L2RlZnM+PGNpcmNsZSBjeD0iNTAiIGN5PSI1MCIgcj0iNDgiIGZpbGw9InVybCgjYWlyYWcpIi8+PHBhdGggZD0iTTI1IDc1IEw1MCAyNSBMNzUgNzUiIHN0cm9rZT0id2hpdGUiIHN0cm9rZS13aWR0aD0iMTAiIHN0cm9rZS1saW5lY2FwPSJyb3VuZCIgc3Ryb2tlLWxpbmVqb2luPSJyb3VuZCIgZmlsbD0ibm9uZSIvPjxwb2x5Z29uIHBvaW50cz0iNTAsNTIgNTMsNTggNTksNTggNTQsNjIgNTYsNjggNTAsNjQgNDQsNjggNDYsNjIgNDEsNTggNDcsNTgiIGZpbGw9IndoaXRlIiBvcGFjaXR5PSIwLjkiLz48L3N2Zz4=" style="width:16px;height:16px;vertical-align:middle;margin-right:4px;border-radius:50%"> AIRA'));

        frm.add_custom_button(__('➕ Quick Add Item'), () => { dcs_quick_add_item(frm); }, __('<img src="data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIHZpZXdCb3g9IjAgMCAxMDAgMTAwIiB3aWR0aD0iMTYiIGhlaWdodD0iMTYiPjxkZWZzPjxyYWRpYWxHcmFkaWVudCBpZD0iYWlyYWciIGN4PSI1MCUiIGN5PSI2MCUiIHI9IjU1JSIgZng9IjUwJSIgZnk9IjcwJSI+PHN0b3Agb2Zmc2V0PSIwJSIgc3RvcC1jb2xvcj0iIzAwZTVjYyIvPjxzdG9wIG9mZnNldD0iNTAlIiBzdG9wLWNvbG9yPSIjM2I2ZWY4Ii8+PHN0b3Agb2Zmc2V0PSIxMDAlIiBzdG9wLWNvbG9yPSIjN2IzZmU0Ii8+PC9yYWRpYWxHcmFkaWVudD48L2RlZnM+PGNpcmNsZSBjeD0iNTAiIGN5PSI1MCIgcj0iNDgiIGZpbGw9InVybCgjYWlyYWcpIi8+PHBhdGggZD0iTTI1IDc1IEw1MCAyNSBMNzUgNzUiIHN0cm9rZT0id2hpdGUiIHN0cm9rZS13aWR0aD0iMTAiIHN0cm9rZS1saW5lY2FwPSJyb3VuZCIgc3Ryb2tlLWxpbmVqb2luPSJyb3VuZCIgZmlsbD0ibm9uZSIvPjxwb2x5Z29uIHBvaW50cz0iNTAsNTIgNTMsNTggNTksNTggNTQsNjIgNTYsNjggNTAsNjQgNDQsNjggNDYsNjIgNDEsNTggNDcsNTgiIGZpbGw9IndoaXRlIiBvcGFjaXR5PSIwLjkiLz48L3N2Zz4=" style="width:16px;height:16px;vertical-align:middle;margin-right:4px;border-radius:50%"> AIRA'));

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
    const fxRate   = isOMR ? AED_TO_OMR : 1.0;

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
        const ref     = AI_PRICE_DB[key];
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
                issues.push('Row ' + rowNum + ' — <b>' + rowName + '</b>: Cost ' + myCost.toFixed(2) + ' deviates <b>' + dev.toFixed(1) + '%</b> from reference (' + refCost.toFixed(2) + ' ' + currency + ')');
            else if (dev > 15)
                warnings.push('Row ' + rowNum + ' — <b>' + rowName + '</b>: Cost ' + myCost.toFixed(2) + ' deviates ' + dev.toFixed(1) + '% from reference (' + refCost.toFixed(2) + ' ' + currency + ')');
            else
                passed.push('Row ' + rowNum + ' ' + rowName + ': Cost within 15% of reference (' + dev.toFixed(1) + '% deviation)');
        }

        // Selling below cost check
        if (mySell > 0 && mySell < refCost)
            issues.push('Row ' + rowNum + ' — <b>' + rowName + '</b>: Selling price (' + mySell.toFixed(2) + ') is BELOW reference cost (' + refCost.toFixed(2) + ') — <b>loss-making!</b>');
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
    const fxRate   = currency === 'OMR' ? AED_TO_OMR : 1.0;

    let html = '<div style="font-size:13px">';
    html += '<p style="color:#555;margin-bottom:10px">AI Reference Prices (converted to <b>' + currency + '</b>). Add items to the database for best results.</p>';

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
        const ref     = AI_PRICE_DB[key];
        const bg      = idx % 2 === 0 ? '#f4f6f7' : '#fff';
        const refCost = ref ? (ref.cost * fxRate).toFixed(2) : '—';
        const refSell = ref ? (ref.sell * fxRate).toFixed(2) : '—';
        const myCost  = (item.cost_rate  || 0).toFixed(2);
        const mySell  = (item.selling_rate || 0).toFixed(2);
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
    html += '<thead><tr style="background:#27ae60;color:white"><th style="padding:6px 8px;text-align:left">Item Code</th><th style="padding:6px 8px;text-align:right">Cost (AED)</th><th style="padding:6px 8px;text-align:right">Sell (AED)</th><th style="padding:6px 8px">Notes</th></tr></thead><tbody>';
    dbKeys.forEach((k, i) => {
        const v = AI_PRICE_DB[k];
        const bg = i % 2 === 0 ? '#f9f9f9' : '#fff';
        html += '<tr style="background:' + bg + '"><td style="padding:5px 8px">' + k + '</td><td style="padding:5px 8px;text-align:right">' + v.cost + '</td><td style="padding:5px 8px;text-align:right">' + v.sell + '</td><td style="padding:5px 8px;color:#777">' + (v.notes||'') + '</td></tr>';
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
                    html += '<td style="padding:8px;text-align:right">' + ((doc.total_cost || 0).toFixed(2)) + '</td>';
                    html += '<td style="padding:8px;text-align:right">' + ((doc.total_selling || 0).toFixed(2)) + '</td>';
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
                html += 'Cost: <b>' + ((frm.doc.total_cost || 0).toFixed(2)) + '</b> | ';
                html += 'Selling: <b>' + ((frm.doc.total_selling || 0).toFixed(2)) + '</b> | ';
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
        // Auto-fetch Customer & Deal Owner from selected Opportunity
        var opp = frm.doc.opportunity;
        if (!opp) return;
        frappe.db.get_value('Opportunity', opp, ['party_name', 'customer_name', 'opportunity_owner'], function(r) {
            if (!r) return;
            var cust = r.party_name || r.customer_name;
            if (cust && !frm.doc.customer) frm.set_value('customer', cust);
            if (r.opportunity_owner && !frm.doc.deal_owner) frm.set_value('deal_owner', r.opportunity_owner);
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

    // AI Provider Button - only for System Manager / Administrator
    if (!document.getElementById('dcs-ai-provider-btn')) {
        var isAdmin = frappe.user.has_role('System Manager') || frappe.user.has_role('Administrator');
        if (isAdmin) {
            var aiBtn = document.createElement('button');
            aiBtn.id = 'dcs-ai-provider-btn';
            aiBtn.innerHTML = '&#129302; AI Provider';
            aiBtn.onclick = function() { dcsOpenAISettings(); };
            document.body.appendChild(aiBtn);
        }
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
    
    var marginVal = totalSell - totalCost;
    var marginPct = totalSell > 0 ? (marginVal / totalSell * 100) : 0;
    
    // Commercial totals derived from the current item rows.
    // These are LOCAL display values. They are written back to the document ONLY on an
    var _calcFields = {
        products_cost_total: productsCost, products_selling_total: productsSell,
        services_cost_total: servicesCost, services_selling_total: servicesSell,
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
                '<div style="font-weight:600">Selling ' + format_currency(_lvSell, _lvCur) +
                ' &nbsp;&middot;&nbsp; Cost ' + format_currency(_lvCost, _lvCur) +
                ' &nbsp;&middot;&nbsp; Margin ' + _lvMpc.toFixed(3) + '%</div>' +
                '<div style="color:#777;margin-top:3px">Figures below are the item cost build-up and may differ from the negotiated position.</div>' +
                '</div>';
        }
        wrapper.innerHTML = '<div style="margin:8px 0">' +
            '<h6 style="font-weight:600;margin-bottom:8px">Commercial Summary</h6>' +
            _lvHead +
            '<table class="table table-bordered table-sm" style="font-size:13px">' +
            '<thead style="background:#f5f5f5"><tr>' +
            '<th>Category</th><th style="text-align:right">Cost (AED)</th>' +
            '<th style="text-align:right">Selling (AED)</th>' +
            '<th style="text-align:right">Margin (AED)</th>' +
            '<th style="text-align:right">Margin %</th></tr></thead>' +
            '<tbody>' + rows +
            '<tr style="font-weight:bold;background:#f5f5f5">' +
            '<td>' + (_lvRev > 0 ? 'Total (item build-up)' : 'Total') + '</td>' +
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
    // Cancelled sheets are commercially dead - suppress all mutating actions
    if (frm.doc.docstatus === 2) { return; }

    var btn = document.createElement('button');
    btn.id = 'dcs-quick-add-btn';
    btn.innerHTML = '&#9889; Quick Add Items';
    btn.onclick = function() { dcsOpenModal(); };
    var placed = false;
    frm.$wrapper.find('.frappe-control[data-fieldname="items"]').each(function() {
        if (!placed) { $(this).before(btn); placed = true; }
    });
    if (!placed) {
        frm.$wrapper.find('.form-section').each(function() {
            if (!placed && $(this).text().indexOf('Item Code') >= 0) { $(this).prepend(btn); placed = true; }
        });
    }
    if (!placed) frm.$wrapper.append(btn);
}


frappe.ui.form.on(cur_frm ? cur_frm.doctype : 'Deal Cost Sheet', {
  refresh() { window.__installLiteTheme && window.__installLiteTheme(); }
});

(function () {
  if (window.__liteThemeInstalled) { window.__installLiteTheme(); return; }
  window.__liteThemeInstalled = true;

  var CSS = `
  html.lite-theme { --lt-primary:#1e66f5; --lt-primary-soft:#eaf1ff; --lt-accent:#7c3aed; --lt-green:#16a34a; --lt-green-soft:#dcfce7; --lt-red:#dc2626; }
  html.lite-theme .navbar { background:linear-gradient(90deg,#1e66f5 0%,#7c3aed 100%)!important; border-bottom:none!important; }
  html.lite-theme .navbar .navbar-brand, html.lite-theme .navbar a, html.lite-theme .navbar .nav-link { color:#fff!important; }
  html.lite-theme .btn-primary, html.lite-theme .primary-action { background:var(--lt-primary)!important; border-color:var(--lt-primary)!important; color:#fff!important; }
  html.lite-theme .btn-primary:hover, html.lite-theme .primary-action:hover { filter:brightness(.93); }
  html.lite-theme .standard-sidebar-item.selected, html.lite-theme .sidebar-item-label.selected { background:var(--lt-primary-soft)!important; border-radius:6px; }
  html.lite-theme .desk-sidebar .standard-sidebar-item.selected a { color:var(--lt-primary)!important; }
  html.lite-theme .list-row:hover, html.lite-theme .list-row-container:hover { background:var(--lt-primary-soft)!important; box-shadow:inset 3px 0 0 var(--lt-primary); }
  html.lite-theme .indicator-pill.green { background:var(--lt-green-soft)!important; color:#15803d!important; }
  html.lite-theme .indicator-pill.red { background:#fee2e2!important; color:#b91c1c!important; }
  html.lite-theme .indicator-pill.orange { background:#ffedd5!important; color:#c2410c!important; }
  html.lite-theme .indicator-pill.blue { background:#dbeafe!important; color:#1d4ed8!important; }
  html.lite-theme .section-head, html.lite-theme .form-section .section-head { color:var(--lt-primary)!important; font-weight:600; }
  html.lite-theme .form-layout table thead th, html.lite-theme .form-layout table thead td { background:var(--lt-primary)!important; color:#fff!important; font-weight:600!important; border-color:var(--lt-primary)!important; }
  html.lite-theme .form-layout table tbody tr:hover { background:var(--lt-primary-soft)!important; }
  html.lite-theme .form-layout table tbody tr:last-child { background:var(--lt-primary-soft)!important; font-weight:700!important; }
  html.lite-theme .form-layout table tbody tr:last-child td { border-top:2px solid var(--lt-primary)!important; color:#0b3d91!important; }
  html.lite-theme .form-layout table { border-radius:8px; overflow:hidden; }
  html.lite-theme .form-grid .grid-heading-row, html.lite-theme .form-grid .grid-heading-row .col, html.lite-theme .form-grid .grid-heading-row .grid-static-col, html.lite-theme .form-grid .grid-heading-row .row-index, html.lite-theme .form-grid .grid-heading-row .row-check { background-color:#1e66f5!important; background-image:none!important; border-color:#1e66f5!important; }
  html.lite-theme .form-grid .grid-heading-row .col { border-right:1px solid rgba(255,255,255,.15)!important; border-bottom:none!important; }
  html.lite-theme .form-grid .grid-heading-row .col:last-child { border-right:none!important; }
  html.lite-theme .form-grid .grid-heading-row, html.lite-theme .form-grid .grid-heading-row .col, html.lite-theme .form-grid .grid-heading-row .static-area, html.lite-theme .form-grid .grid-heading-row .field-area, html.lite-theme .form-grid .grid-heading-row span, html.lite-theme .form-grid .grid-heading-row div, html.lite-theme .form-grid .grid-heading-row .reqd { color:#fff!important; -webkit-text-fill-color:#fff!important; opacity:1!important; font-weight:600!important; }
  html.lite-theme .form-grid .grid-heading-row .grid-row-check input { filter:brightness(0) invert(1); }
  html.lite-theme .form-grid .grid-body .grid-row:hover { background:var(--lt-primary-soft)!important; }
  html.lite-theme .form-grid .grid-body .grid-row:nth-child(even) { background:#f8fafd; }
  html.lite-theme .frappe-control[data-fieldname="customer"], html.lite-theme .frappe-control[data-fieldname="customer_name"], html.lite-theme .frappe-control[data-fieldname="party_name"], html.lite-theme .frappe-control[data-fieldname="status"], html.lite-theme .frappe-control[data-fieldname="workflow_state"], html.lite-theme .frappe-control[data-fieldname="custom_organization_name"], html.lite-theme .frappe-control[data-fieldname="organization_name"], html.lite-theme .frappe-control[data-fieldname="custom_contact_person_name"], html.lite-theme .frappe-control[data-fieldname="contact_person"], html.lite-theme .frappe-control[data-fieldname="contact_display"], html.lite-theme .frappe-control[data-fieldname="custom_sales_person"], html.lite-theme .frappe-control[data-fieldname="sales_person"] { background:var(--lt-primary-soft)!important; border-left:3px solid var(--lt-primary)!important; border-radius:8px!important; padding:8px 10px!important; margin-bottom:8px!important; box-shadow:0 1px 3px rgba(30,102,245,.10); }
  html.lite-theme .frappe-control[data-fieldname="customer"] .control-label, html.lite-theme .frappe-control[data-fieldname="customer_name"] .control-label, html.lite-theme .frappe-control[data-fieldname="party_name"] .control-label, html.lite-theme .frappe-control[data-fieldname="status"] .control-label, html.lite-theme .frappe-control[data-fieldname="workflow_state"] .control-label, html.lite-theme .frappe-control[data-fieldname="custom_organization_name"] .control-label, html.lite-theme .frappe-control[data-fieldname="organization_name"] .control-label, html.lite-theme .frappe-control[data-fieldname="custom_contact_person_name"] .control-label, html.lite-theme .frappe-control[data-fieldname="contact_person"] .control-label, html.lite-theme .frappe-control[data-fieldname="contact_display"] .control-label, html.lite-theme .frappe-control[data-fieldname="custom_sales_person"] .control-label, html.lite-theme .frappe-control[data-fieldname="sales_person"] .control-label { color:var(--lt-primary)!important; font-weight:700!important; text-transform:uppercase; letter-spacing:.3px; font-size:11px; }
  html.lite-theme .frappe-control[data-fieldname="customer"] .control-input input, html.lite-theme .frappe-control[data-fieldname="customer_name"] .control-input input, html.lite-theme .frappe-control[data-fieldname="party_name"] .control-input input { font-weight:700!important; color:#0b3d91!important; }
  html.lite-theme .frappe-control[data-fieldname="grand_total"], html.lite-theme .frappe-control[data-fieldname="rounded_total"], html.lite-theme .frappe-control[data-fieldname="base_grand_total"] { background:var(--lt-green-soft)!important; border-left:3px solid var(--lt-green)!important; border-radius:8px!important; padding:8px 10px!important; margin-bottom:8px!important; box-shadow:0 1px 4px rgba(22,163,74,.15); }
  html.lite-theme .frappe-control[data-fieldname="grand_total"] .control-label, html.lite-theme .frappe-control[data-fieldname="rounded_total"] .control-label, html.lite-theme .frappe-control[data-fieldname="base_grand_total"] .control-label { color:#15803d!important; font-weight:700!important; text-transform:uppercase; font-size:11px; }
  html.lite-theme .frappe-control[data-fieldname="grand_total"] .control-input input, html.lite-theme .frappe-control[data-fieldname="rounded_total"] .control-input input, html.lite-theme .frappe-control[data-fieldname="base_grand_total"] .control-input input { font-weight:800!important; color:#15803d!important; font-size:15px!important; }
  html.lite-theme .page-head .indicator-pill, html.lite-theme .title-area .indicator-pill { font-weight:700!important; padding:3px 12px!important; border-radius:14px!important; font-size:11px!important; text-transform:uppercase; letter-spacing:.4px; border:1.5px solid transparent!important; box-shadow:0 1px 4px rgba(0,0,0,.12); }
  html.lite-theme .page-head .indicator-pill.blue, html.lite-theme .title-area .indicator-pill.blue { background:#dbeafe!important; color:#1d4ed8!important; border-color:#93c5fd!important; }
  html.lite-theme .page-head .indicator-pill.green, html.lite-theme .title-area .indicator-pill.green { background:#dcfce7!important; color:#15803d!important; border-color:#86efac!important; }
  html.lite-theme .page-head .indicator-pill.red, html.lite-theme .title-area .indicator-pill.red { background:#fee2e2!important; color:#b91c1c!important; border-color:#fca5a5!important; }
  html.lite-theme .page-head .indicator-pill.orange, html.lite-theme .title-area .indicator-pill.orange { background:#ffedd5!important; color:#c2410c!important; border-color:#fdba74!important; }
  html.lite-theme .page-head .indicator-pill.gray, html.lite-theme .page-head .indicator-pill.grey { background:#f1f5f9!important; color:#475569!important; border-color:#cbd5e1!important; }
    .form-grid .grid-body .data-row .col[data-fieldname="item_code"] { height:auto !important; max-height:none !important; }
      .form-grid .grid-body .data-row .col[data-fieldname="item_code"] .static-area,
        .form-grid .grid-body .data-row .col[data-fieldname="item_code"] .ellipsis,
          .form-grid .grid-body .data-row .col[data-fieldname="item_code"] .control-value,
            .form-grid .grid-body .data-row .col[data-fieldname="item_code"] .grid-static-col { height:auto !important; max-height:none !important; overflow:visible !important; white-space:normal !important; -webkit-line-clamp:unset !important; display:block !important; }
            `;

  function colorize() {
    if (!document.documentElement.classList.contains('lite-theme')) return;
    document.querySelectorAll('.form-layout table').forEach(function (tbl) {
      var heads = Array.from(tbl.querySelectorAll('thead th, thead td')).map(function (h) { return h.innerText.toLowerCase().trim(); });
      var cols = []; heads.forEach(function (h, i) { if (h.indexOf('margin') > -1) cols.push(i); });
      if (!cols.length) return;
      tbl.querySelectorAll('tbody tr').forEach(function (tr) {
        cols.forEach(function (ci) {
          var c = tr.children[ci]; if (!c) return;
          var n = parseFloat(c.innerText.replace(/[^\d.\-]/g, '')); if (isNaN(n)) return;
          c.style.fontWeight = '700';
          c.style.color = n > 0 ? '#15803d' : (n < 0 ? '#dc2626' : '#92400e');
        });
      });
    });
    var profit = ['gp_value', 'gp_percent', 'margin', 'margin_amount', 'margin_percent'];
    document.querySelectorAll('.form-grid .grid-body .grid-row .col[data-fieldname]').forEach(function (cell) {
      var df = cell.getAttribute('data-fieldname');
      var t = cell.querySelector('.static-area') || cell;
      if (profit.indexOf(df) > -1) {
        var n = parseFloat((t.innerText || '').replace(/[^\d.\-]/g, ''));
        if (isNaN(n)) { t.style.color = ''; t.style.fontWeight = ''; return; }
        t.style.fontWeight = '700';
        t.style.color = n > 0 ? '#15803d' : (n < 0 ? '#dc2626' : '#92400e');
      } else if (df === 'amount' || df === 'cost_amount' || df === 'selling_amount') {
        t.style.fontWeight = '600';
      }
    });
  }

  function buildToggle() {
    if (document.getElementById('lite-theme-toggle')) return;
    var w = document.createElement('div'); w.id = 'lite-theme-toggle';
    w.style.cssText = 'position:fixed;bottom:20px;right:20px;z-index:99999;display:flex;align-items:center;gap:8px;background:#fff;border:1px solid #e2e2e2;border-radius:20px;padding:6px 13px;box-shadow:0 3px 10px rgba(0,0,0,.15);font-size:12px;font-family:inherit;cursor:pointer;user-select:none;';
    function render() {
      var on = document.documentElement.classList.contains('lite-theme');
      w.innerHTML = '<span style="font-weight:600;color:#444;">Color Theme</span>' +
        '<span style="position:relative;width:34px;height:18px;border-radius:10px;transition:.2s;background:' + (on ? '#1e66f5' : '#ccc') + ';display:inline-block;">' +
        '<span style="position:absolute;top:2px;left:' + (on ? '18px' : '2px') + ';width:14px;height:14px;border-radius:50%;background:#fff;transition:.2s;"></span></span>' +
        '<span style="color:' + (on ? '#1e66f5' : '#999') + ';font-weight:600;">' + (on ? 'ON' : 'OFF') + '</span>';
    }
    w.onclick = function () {
      var on = document.documentElement.classList.toggle('lite-theme');
      localStorage.setItem('lite_theme_on', on ? '1' : '0'); render();
    };
    render(); document.body.appendChild(w);
  }

  window.__installLiteTheme = function () {
    if (!document.getElementById('lite-theme-style')) {
      var s = document.createElement('style'); s.id = 'lite-theme-style'; s.textContent = CSS; document.head.appendChild(s);
    }
    if (localStorage.getItem('lite_theme_on') !== '0') document.documentElement.classList.add('lite-theme');
    buildToggle();
  };

  window.__installLiteTheme();
  setInterval(function () {
    window.__installLiteTheme();
    if (document.documentElement.classList.contains('lite-theme')) colorize();
  }, 1500);
})();


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
    if (!frm.fields_dict.custom_deal_summary_dashboard) return;
    var d = frm.doc;

    function fmt(v) {
        var n = format_number(v || 0, null, 2);
        return (d.currency || '') + ' ' + n;
    }

    function badge(icon, color) {
        return '<span style="display:inline-flex; align-items:center; justify-content:center; width:26px; height:26px; border-radius:50%; background:' + color + '1f; color:' + color + '; font-size:13px; flex:none;">' + icon + '</span>';
    }

    function row(label, value, color) {
        var style = color ? ('color:' + color + '; font-weight:700;') : 'color:var(--text-color);';
        return '<div style="display:flex; justify-content:space-between; align-items:center; gap:12px; padding:6px 0; font-size:13px; border-bottom:1px dashed rgba(140,140,140,0.18);">' +
            '<span style="color:var(--text-muted);">' + label + '</span>' +
            '<span style="text-align:right; ' + style + '">' + (value !== undefined && value !== null && value !== '' ? value : '-') + '</span>' +
            '</div>';
    }

    function link_row(label, route, name) {
        if (!name) return row(label, '-');
        var value = '<a href="/app/' + route + '/' + encodeURIComponent(name) + '" target="_blank" style="font-weight:600;">' + name + '</a>';
        return row(label, value);
    }

    function quick_link(label, route, name, color) {
        if (!name) return '';
        return '<div style="padding:7px 0; font-size:13px; display:flex; align-items:center; gap:8px;">' +
            badge('&#8594;', color) +
            '<a href="/app/' + route + '/' + encodeURIComponent(name) + '" target="_blank" style="color:' + color + '; font-weight:600;">View ' + label + '</a></div>';
    }

    function col(icon, title, accent, body, flex) {
        return '<div style="flex:' + (flex || 1) + '; min-width:230px; border-radius:12px; padding:16px 18px; margin:6px; ' +
            'background:var(--card-bg, #fff); border:1px solid var(--border-color); border-top:3px solid ' + accent + '; ' +
            'box-shadow:0 2px 10px rgba(0,0,0,0.06);">' +
            '<div style="font-weight:600; font-size:13.5px; color:var(--text-color); letter-spacing:.01em; margin-bottom:14px; display:flex; align-items:center; gap:10px;">' +
            badge(icon, accent) + '<span>' + title + '</span></div>' +
            body + '</div>';
    }

    function stat_box(label, value, color, icon) {
        return '<div style="flex:1; min-width:47%; border-radius:10px; padding:10px 12px 10px 14px; background:var(--card-bg, #fff); ' +
            'border-left:4px solid ' + color + '; box-shadow:0 1px 4px rgba(0,0,0,0.06);">' +
            '<div style="display:flex; align-items:center; gap:6px; font-size:10.5px; color:var(--text-muted); text-transform:uppercase; letter-spacing:.04em; font-weight:700; margin-bottom:4px;">' +
            '<span>' + icon + '</span><span>' + label + '</span></div>' +
            '<div style="font-size:18px; font-weight:700; color:' + color + '; line-height:1.2;">' + value + '</div>' +
            '</div>';
    }

    var state = d.workflow_state || 'Draft';
    var color_map = {'Draft': 'gray', 'Pending': 'orange', 'Approved': 'green', 'Returned for Rework': 'red'};
    var color = color_map[state] || 'gray';
    var workflow_badge = '<span class="indicator-pill ' + color + '" style="font-weight:600; font-size:12.5px;">' + state + '</span>';

    var green = '#059669';
    var blue = '#2563eb';
    var purple = '#7c3aed';
    var teal = '#0891b2';
    var indigo = '#4f46e5';
    var amber = '#b45309';

    var margin_color = d.margin_value > 0 ? green : '#dc2626';
    var margin_pct = d.margin_percent ? d.margin_percent.toFixed(2) + '%' : '0.00%';

    var opp_body = link_row('Opportunity', 'opportunity', d.opportunity) +
        link_row('Presales Request', 'presales-request', d.presales_request) +
        link_row('Project', 'project', d.project) +
        row('Territory', d.territory) +
        row('Currency', d.currency) +
        row('Deal Owner', d.deal_owner) +
        row('Prepared By', d.owner);

    var comm_body = '<div style="display:flex; flex-wrap:wrap; gap:10px;">' +
        stat_box('Total Cost', fmt(d.total_cost), blue, '&#128181;') +
        stat_box('Total Selling', fmt(d.total_selling), indigo, '&#128181;') +
        stat_box('Gross Profit', '&#128176; ' + fmt(d.margin_value), margin_color, '&#128200;') +
        stat_box('Margin %', margin_pct, amber, '&#127919;') +
        '</div>';

    var status_body = row('Workflow', workflow_badge) +
        row('Items', d.items ? d.items.length : 0) +
        row('Resources', d.resources ? d.resources.length : 0) +
        row('Responsibilities', d.responsibilities ? d.responsibilities.length : 0) +
        row('Last Updated', frappe.datetime.comment_when(d.modified));

    var quick_body = quick_link('Opportunity', 'opportunity', d.opportunity, teal) +
        quick_link('Presales Request', 'presales-request', d.presales_request, teal) +
        quick_link('Project', 'project', d.project, teal);

    if (!quick_body) {
        quick_body = '<div style="font-size:13px; color:var(--text-muted);">No linked records yet</div>';
    }

    var section_title = '<div style="display:flex; align-items:center; justify-content:space-between; margin:2px 8px 12px 8px;">' +
        '<div style="display:flex; align-items:center; gap:10px;">' +
        '<span style="display:inline-flex; align-items:center; justify-content:center; width:30px; height:30px; border-radius:50%; background:linear-gradient(135deg,#7c3aed,#2563eb); color:#fff; font-size:14px;">&#128203;</span>' +
        '<span style="font-size:16px; font-weight:700; letter-spacing:.01em; color:var(--text-color);">Decision Board</span>' +
        '</div>' +
        '<span style="font-size:11.5px; color:var(--text-muted); letter-spacing:.02em;">Deal snapshot &amp; key metrics</span>' +
        '</div>';

    var html = '<div style="border:1px solid var(--border-color); border-radius:16px; padding:14px; ' +
        'background:linear-gradient(180deg, rgba(124,58,237,0.03), rgba(37,99,235,0.02)); box-shadow:0 3px 14px rgba(0,0,0,0.05);">' +
        section_title +
        '<div style="display:flex; flex-wrap:wrap; margin:0 -6px;">' +
        col('&#127970;', 'Opportunity', blue, opp_body, 1) +
        col('&#128176;', 'Commercial Summary', green, comm_body, 1.5) +
        col('&#128202;', 'Status', purple, status_body, 1) +
        col('&#128279;', 'Quick Links', teal, quick_body, 1) +
        '</div></div>';

    frm.fields_dict.custom_deal_summary_dashboard.$wrapper.html(html);
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

function dcs_cur(frm) { return frm.doc.currency || frappe.defaults.get_default('currency'); }

function dcs_money(frm, v) {
	if (v === null || v === undefined || v === '') { return '&mdash;'; }
	return format_currency(v, dcs_cur(frm));
}

function dcs_pct(v) {
	if (v === null || v === undefined || v === '') { return '&mdash;'; }
	return flt(v, 3) + '%';
}

function dcs_when(v) { return v ? frappe.datetime.str_to_user(v) : '&mdash;'; }

function dcs_panel(title, body, note) {
	var n = note ? '<div class="text-muted small" style="margin-top:6px">' + dcs_esc(note) + '</div>' : '';
	return '<div style="margin-top:4px"><div class="text-muted" style="font-weight:600;letter-spacing:.4px;text-transform:uppercase;font-size:11px;margin-bottom:8px">'
		+ dcs_esc(title) + '</div>' + body + n + '</div>';
}

function dcs_empty(msg) {
	return '<div class="text-muted" style="padding:12px 0">' + dcs_esc(msg) + '</div>';
}

function dcs_set_html(frm, field, html) {
	var f = frm.get_field(field);
	if (f && f.$wrapper) { f.$wrapper.html(html); }
}

function dcs_call(method, args) {
	return new Promise(function (resolve) {
		frappe.call({ method: method, args: args, callback: function (r) { resolve((r && r.message) || {}); }, error: function () { resolve({}); } });
	});
}

function dcs_load(frm) {
	var n = frm.doc.name;
	Promise.all([
		dcs_call('dcs_screen3', { dcs: n }),
		dcs_call('dcs_screen4', { dcs: n }),
		dcs_call('dcs_screen5', { dcs: n })
	]).then(function (res) {
		var s3 = res[0] || {}, s4 = res[1] || {}, s5 = res[2] || {};
		frm.__dcs = { s3: s3, s4: s4, s5: s5 };
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
	if (!s5.living) { return; }
	var lv = s5.living, fz = s5.frozen_baseline || {};
	var dcs_hasrev = (lv && lv.revision_no) ? 1 : 0;
	if (!dcs_hasrev) {
		lv = {
			revision_no: 0,
			total_cost: (frm.doc.total_cost || 0),
			total_selling: (frm.doc.total_selling || 0),
			margin_percent: (frm.doc.margin_percent || 0),
			approval_state: lv ? lv.approval_state : null,
			approval_required: lv ? lv.approval_required : null,
			margin_gate: lv ? lv.margin_gate : null
		};
	}
	var cell = function (label, value, sub) {
		return '<div style="display:inline-block;min-width:150px;margin-right:26px;vertical-align:top">'
			+ '<div class="text-muted" style="font-size:11px;text-transform:uppercase;letter-spacing:.4px">' + dcs_esc(label) + '</div>'
			+ '<div style="font-size:15px;font-weight:600">' + value + '</div>'
			+ (sub ? '<div class="text-muted" style="font-size:11px">' + sub + '</div>' : '') + '</div>';
	};
	var h = cell((dcs_hasrev ? 'Living position' : 'Baseline position'), dcs_money(frm, lv.total_selling), 'Cost ' + (dcs_money(frm, lv.total_cost) + (dcs_hasrev ? '' : ' · GP ' + dcs_money(frm, (frm.doc.margin_value || 0)))))
		+ cell((dcs_hasrev ? 'Living margin' : 'Baseline margin'), dcs_pct(lv.margin_percent), (dcs_hasrev ? 'Revision ' : 'No negotiation revisions yet') + (dcs_hasrev ? dcs_esc(lv.revision_no) : ''))
		+ (fz.frozen ? cell('Frozen baseline', dcs_money(frm, fz.total_selling), 'Awarded at revision ' + dcs_esc(fz.revision_no))
			: cell('Frozen baseline', '<span class="text-muted">Not frozen</span>', 'Set when the award is recorded'))
		+ cell('Approval', dcs_esc(lv.approval_state || 'Not started'), lv.approval_required && lv.approval_required !== 'None' ? 'Requires ' + dcs_esc(lv.approval_required) : 'No sign-off required');
	var rr = s5.release_readiness || {};
	if (rr.note) {
		h += '<div class="text-muted" style="margin-top:10px;padding-top:8px;border-top:1px solid var(--border-color)">' + dcs_esc(rr.note) + '</div>';
	}
	frm.dashboard.set_headline(h);
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
	var ob = cond.open_blockers || 0;
	add(ob === 0 ? 'No open blockers' : ob + ' open blocker(s)', ob === 0 ? 'green' : 'red');
	add('Delivery: ' + (st.delivery_release || 'Not Applicable'), (st.delivery_release || '').indexOf('Released') === 0 ? 'blue' : 'gray');
}

function dcs_render_negotiation(frm, s3) {
	var revs = (s3.revisions || []).slice().sort(function (a, b) { return b.revision_no - a.revision_no; });
	var pol = s3.policy || {};
	var body;
	if (!revs.length) {
		body = dcs_empty('No revisions yet. The first revision initialises the living commercial position from the sheet totals.');
	} else {
		var rows = revs.map(function (r) {
			var gp = r.gp_movement || 0;
			var gpTxt = (gp > 0 ? '+' : '') + format_currency(gp, dcs_cur(frm));
			var gpCls = gp > 0 ? 'text-success' : (gp < 0 ? 'text-danger' : 'text-muted');
			var req = (r.approval_requirement && r.approval_requirement !== 'None') ? '<span class="indicator-pill orange">' + dcs_esc(r.approval_requirement) + '</span>' : '<span class="text-muted">None</span>';
			return '<tr>'
				+ '<td style="white-space:nowrap"><a href="' + frappe.utils.get_form_link('DCS Revision', r.name) + '">R' + dcs_esc(r.revision_no) + '</a></td>'
				+ '<td>' + dcs_esc(r.source) + '</td>'
				+ '<td class="text-right">' + dcs_money(frm, r.prev_total_cost) + ' &rarr; <b>' + dcs_money(frm, r.new_total_cost) + '</b></td>'
				+ '<td class="text-right">' + dcs_money(frm, r.prev_total_selling) + ' &rarr; <b>' + dcs_money(frm, r.new_total_selling) + '</b></td>'
				+ '<td class="text-right">' + dcs_pct(r.prev_margin_percent) + ' &rarr; <b>' + dcs_pct(r.new_margin_percent) + '</b></td>'
				+ '<td class="text-right ' + gpCls + '">' + gpTxt + '</td>'
				+ '<td>' + req + '</td>'
				+ '<td class="text-muted small">' + dcs_esc(r.changed_by) + '<br>' + dcs_when(r.changed_on) + '</td>'
				+ '</tr>'
				+ '<tr><td></td><td colspan="7" class="text-muted small" style="padding-bottom:10px">' + dcs_esc(r.reason)
				+ (r.technical_impact ? '<br><i>Technical impact:</i> ' + dcs_esc(r.technical_impact) : '') + '</td></tr>';
		}).join('');
		body = '<div class="table-responsive"><table class="table table-sm" style="font-size:12px">'
			+ '<thead><tr><th>Rev</th><th>Side</th><th class="text-right">Cost</th><th class="text-right">Selling</th>'
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
		+ '<tr><td class="text-muted">Evidence</td><td>' + dcs_esc(aw.evidence_type || '&mdash;') + ' ' + dcs_esc(aw.reference || '') + '</td></tr>'
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
	var all = (c.blockers || []).concat(c.watch_items || []).concat(c.accepted_risks || []);
	var body = '<div style="margin-bottom:10px">'
		+ '<span class="indicator-pill ' + (rr.commercially_aligned ? 'green' : 'red') + '">' + (rr.commercially_aligned ? 'Commercially aligned' : 'Not commercially aligned') + '</span> '
		+ '<span class="indicator-pill ' + ((c.open_blockers || 0) === 0 ? 'green' : 'red') + '">' + (c.open_blockers || 0) + ' open blocker(s)</span> '
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
	dcs_set_html(frm, 'custom_handover_html', dcs_panel('Handover conditions and delivery readiness', body, rr.basis || ''));
}

function dcs_run(frm, method, args, dlg) {
	frappe.call({
		method: method,
		args: args,
		freeze: true,
		freeze_message: __('Applying...'),
		callback: function (r) {
			var m = (r && r.message) || {};
			if (m.error) {
				frappe.msgprint({ title: __('Not permitted'), message: dcs_esc(m.error), indicator: 'red' });
				return;
			}
			if (dlg) { dlg.hide(); }
			frappe.show_alert({ message: __('Recorded'), indicator: 'green' });
			frm.reload_doc();
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
	// Cancelled sheets are commercially dead - suppress all mutating actions.
	if (frm.doc.docstatus === 2) { return; }
	var cap = s3.capability || {}, auth = s5.authority || {}, st = s5.states || {}, lv = s5.living || {};
	var N = __('Negotiation'), A = __('Approval'), W = __('Award'), H = __('Handover');

	var revision = function (side) {
		var isCust = side === 'Customer';
		dcs_dialog(frm, isCust ? 'Customer Revision' : 'Vendor Revision', [
			{ fieldtype: 'Currency', fieldname: 'new_total_selling', label: __('New Total Selling'), default: lv.total_selling, hidden: isCust ? 0 : 1 },
			{ fieldtype: 'Currency', fieldname: 'new_total_cost', label: __('New Total Cost'), default: lv.total_cost, hidden: isCust ? 1 : 0 },
			{ fieldtype: 'Small Text', fieldname: 'reason', label: __('Reason'), reqd: 1 },
			{ fieldtype: 'Small Text', fieldname: 'technical_impact', label: __('Technical Impact') }
		], 'Apply Revision', function (v, d) {
			var args = { dcs: frm.doc.name, source: side, reason: v.reason, technical_impact: v.technical_impact };
			if (isCust) { args.new_total_selling = v.new_total_selling; } else { args.new_total_cost = v.new_total_cost; }
			dcs_run(frm, 'dcs_apply_revision', args, d);
		});
	};
	if (cap.can_customer_side) { frm.add_custom_button(__('Customer Revision'), function () { revision('Customer'); }, N); }
	if (cap.can_vendor_side) { frm.add_custom_button(__('Vendor Revision'), function () { revision('Vendor'); }, N); }
	if (!cap.can_negotiate && cap.denial_reason) {
		frm.add_custom_button(__('Why can I not negotiate?'), function () {
			frappe.msgprint({ title: __('Negotiation authority'), message: dcs_esc(cap.denial_reason), indicator: 'orange' });
		}, N);
	}

	var decide = function (action) {
		dcs_dialog(frm, action, [
			{ fieldtype: 'Small Text', fieldname: 'reason', label: __('Reason'), reqd: 1 },
			{ fieldtype: 'HTML', fieldname: 'why', options: '<div class="text-muted small">' + dcs_esc(((s4.consequences || {})[action.toLowerCase().split(' ')[0] + 'ed'] || '')) + '</div>' }
		], action, function (v, d) {
			dcs_run(frm, 'dcs_approval_decision', { dcs: frm.doc.name, action: action, reason: v.reason }, d);
		});
	};
	if (lv.approval_required && lv.approval_required !== 'None' && lv.approval_state !== 'Approved') {
		['Endorse', 'Approve', 'Return for Rework', 'Reject'].forEach(function (a) {
			frm.add_custom_button(__(a), function () { decide(a); }, A);
		});
	}

	var record_award = function (relabel) {
		dcs_dialog(frm, relabel || 'Record Award', [
			{ fieldtype: 'Data', fieldname: 'award_reference', label: __('Award Reference'), reqd: 1 },
			{ fieldtype: 'Select', fieldname: 'evidence_type', label: __('Evidence Type'), options: 'Customer PO\nSigned Quotation\nEmail Confirmation\nLetter of Award', reqd: 1 },
			{ fieldtype: 'Small Text', fieldname: 'notes', label: __('Notes') },
			{ fieldtype: 'HTML', fieldname: 'note', options: '<div class="text-muted small">Recording an award freezes the commercial baseline at the current living position. It does not release delivery.</div>' }
		], relabel || 'Record Award', function (v, d) {
			dcs_run(frm, 'dcs_record_award', { dcs: frm.doc.name, award_reference: v.award_reference, evidence_type: v.evidence_type, notes: v.notes }, d);
		});
	};
	if (st.customer_award !== 'Awarded') { frm.add_custom_button(__('Record Award'), function () { record_award(); }, W); }
	if (st.customer_award === 'Awarded') {
		frm.add_custom_button(__('Reverse Award'), function () {
			dcs_dialog(frm, 'Reverse Award', [
				{ fieldtype: 'Small Text', fieldname: 'reason', label: __('Reversal Reason'), reqd: 1 },
				{ fieldtype: 'Data', fieldname: 'evidence_reference', label: __('Evidence Reference') },
				{ fieldtype: 'Check', fieldname: 'acknowledge', label: __('I acknowledge that delivery release is stopped, the original award event remains immutable in history, and delivery already performed is not rolled back automatically'), reqd: 1 }
			], 'Reverse Award', function (v, d) {
				dcs_run(frm, 'dcs_award_reversal', { dcs: frm.doc.name, reason: v.reason, evidence_reference: v.evidence_reference, acknowledge: v.acknowledge ? 1 : 0, mode: 'reverse' }, d);
			});
		}, W);
	}
	if (st.award_reversal_state === 'Reversed') { frm.add_custom_button(__('Re-award'), function () { record_award('Re-award'); }, W); }

	frm.add_custom_button(__('Reconcile Customer PO'), function () {
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

	frm.add_custom_button(__('Set Delivery Owner'), function () {
		dcs_dialog(frm, 'Set Delivery Owner', [
			{ fieldtype: 'Link', fieldname: 'delivery_owner', label: __('Delivery Owner'), options: 'User', default: st.delivery_owner, reqd: 1 }
		], 'Set', function (v, d) { dcs_run(frm, 'dcs_set_delivery_owner', { dcs: frm.doc.name, delivery_owner: v.delivery_owner }, d); });
	}, H);

	var open_conds = ((s5.conditions || {}).blockers || []).concat(((s5.conditions || {}).watch_items || [])).filter(function (x) { return x.state === 'Open'; });
	if (open_conds.length) {
		frm.add_custom_button(__('Action a Condition'), function () {
			dcs_dialog(frm, 'Handover Condition', [
				{ fieldtype: 'Select', fieldname: 'condition', label: __('Condition'), options: open_conds.map(function (x) { return x.name; }).join('\n'), reqd: 1 },
				{ fieldtype: 'Select', fieldname: 'action', label: __('Action'), options: 'Clear\nAssign\nAccept Risk', reqd: 1 },
				{ fieldtype: 'Small Text', fieldname: 'note', label: __('Note'), reqd: 1 },
				{ fieldtype: 'Link', fieldname: 'assign_to', label: __('Assign To'), options: 'User' },
				{ fieldtype: 'Check', fieldname: 'acknowledged', label: __('Acknowledged (required to accept a risk)') }
			], 'Apply', function (v, d) {
				dcs_run(frm, 'dcs_handover_action', { condition: v.condition, action: v.action, note: v.note, assign_to: v.assign_to, acknowledged: v.acknowledged ? 1 : 0 }, d);
			});
		}, H);
	}

	if (st.customer_award === 'Awarded' && (st.delivery_release || '').indexOf('Released') !== 0) {
		frm.add_custom_button(__('Release to Delivery'), function () {
			dcs_dialog(frm, 'Release to Delivery', [
				{ fieldtype: 'Check', fieldname: 'override', label: __('Exceptional Managing Director override') },
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
	var G = __('Governed Actions');
	var dcs_portal = function (path) { window.open(path + '?dcs=' + encodeURIComponent(frm.doc.name), '_blank'); };
	frm.add_custom_button(__('Working View'), function () { dcs_portal('/living-dcs'); }, G);
	if (s3 && s3.ok) { frm.add_custom_button(__('Negotiation & Revision'), function () { dcs_portal('/negotiation-workspace'); }, G); }
	if (s4 && s4.ok) { frm.add_custom_button(__('Approval'), function () { dcs_portal('/approval-workspace'); }, G); }
	if (s5 && s5.ok) { frm.add_custom_button(__('Award & Handover (PO, Delivery, Reversal)'), function () { dcs_portal('/award-handover'); }, G); }
	frm.add_custom_button(__('DCS Governance Workspace'), function () { frappe.set_route('dcs-governance'); }, G);


	// Governed Documents - NAVIGATION ONLY, exactly like the group above.
	// dcs_print_document decides the audience server-side and builds the technical pack from a
	// non-commercial allowlist, so a wrong turn here produces a refusal, never a leak.
	// Presentation follows the projection already returned; it is not a permission rule.
	var D = __('Documents');
	var dcs_doc_out = function (kind) {
		window.open('/dcs-document?dcs=' + encodeURIComponent(frm.doc.name) + '&kind=' + kind, '_blank');
	};
	var dproj = (s5 && s5.projection) || (s4 && s4.projection) || (s3 && s3.projection) || '';
	if (dproj !== 'technical' && dproj !== 'reduced') {
		frm.add_custom_button(__('Commercial Deal Cost Sheet'), function () { dcs_doc_out('commercial'); }, D);
		frm.add_custom_button(__('Award & Reversal Evidence'), function () { dcs_doc_out('award'); }, D);
	}
	frm.add_custom_button(__('Technical / Operations Handover'), function () { dcs_doc_out('handover'); }, D);

	frm.page.set_inner_btn_group_as_primary(H);
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


