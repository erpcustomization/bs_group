// Copyright (c) 2026, Tridots Tech and contributors
// For license information, please see license.txt

frappe.ui.form.on('Sales Target GP Entry', {
	refresh(frm) {
		stgp_recalc(frm);
	},
	onload_post_render(frm) {
		frappe.call({
			method: 'bsgroup.bs_group.doctype.sales_target_gp_entry.sales_target_gp_entry.stgp_allowed_sales_persons',
			callback: function(r) {
				var allowed = (r && r.message) ? r.message : [];
				frm.set_query('salesperson', function() {
					return { filters: [['Sales Person', 'name', 'in', allowed]] };
				});
			}
		});
	}
});

frappe.ui.form.on('Sales Target GP Month', {
	invoiced_sales_revenue(frm, cdt, cdn) { stgp_row(frm, cdt, cdn); },
	invoiced_sales_gp(frm, cdt, cdn) { stgp_row(frm, cdt, cdn); },
	booked_sales_revenue(frm, cdt, cdn) { stgp_row(frm, cdt, cdn); },
	booked_sales_gp(frm, cdt, cdn) { stgp_row(frm, cdt, cdn); },
	monthly_data_remove(frm) { stgp_recalc(frm); }
});

function stgp_row(frm, cdt, cdn) {
	const row = locals[cdt][cdn];
	const inv_rev = flt(row.invoiced_sales_revenue);
	const inv_gp = flt(row.invoiced_sales_gp);
	const bkd_rev = flt(row.booked_sales_revenue);
	const bkd_gp = flt(row.booked_sales_gp);

	// Live validation feedback: GP must not exceed Revenue
	if (inv_gp > inv_rev) {
		frappe.show_alert({message: __('Invoiced GP exceeds Invoiced Revenue for {0}', [row.month || '(row)']), indicator: 'orange'});
	}
	if (bkd_gp > bkd_rev) {
		frappe.show_alert({message: __('Booked GP exceeds Booked Revenue for {0}', [row.month || '(row)']), indicator: 'orange'});
	}

	row.invoiced_gp_pct = inv_rev ? (inv_gp / inv_rev * 100) : 0;
	row.booked_gp_pct = bkd_rev ? (bkd_gp / bkd_rev * 100) : 0;

	if (!row.status || row.status === 'Not Entered') {
		row.status = (inv_rev || inv_gp || bkd_rev || bkd_gp) ? 'Draft' : 'Not Entered';
	}
	frm.refresh_field('monthly_data');
	stgp_recalc(frm);
}

function stgp_recalc(frm) {
	let tir = 0, tig = 0, tbr = 0, tbg = 0;
	(frm.doc.monthly_data || []).forEach(function(r) {
		tir += flt(r.invoiced_sales_revenue);
		tig += flt(r.invoiced_sales_gp);
		tbr += flt(r.booked_sales_revenue);
		tbg += flt(r.booked_sales_gp);
	});
	frm.set_value('total_invoiced_revenue', tir);
	frm.set_value('total_invoiced_gp', tig);
	frm.set_value('total_booked_revenue', tbr);
	frm.set_value('total_booked_gp', tbg);
}
