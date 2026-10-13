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