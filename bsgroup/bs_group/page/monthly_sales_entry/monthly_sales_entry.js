frappe.pages["monthly-sales-entry"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "Monthly Sales Performance Entry",
		single_column: true,
	});

	if (!document.getElementById("mspe-styles")) {
		const style = document.createElement("style");
		style.id = "mspe-styles";
		style.textContent = `
.mspe-root{max-width:1400px;margin:0 auto;padding:8px 4px 40px;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Inter,Roboto,sans-serif;color:#1f272e}
.mspe-head{display:flex;align-items:flex-start;gap:16px;margin-bottom:18px;flex-wrap:wrap}
.mspe-title{font-size:22px;font-weight:700;margin:0}
.mspe-sub{color:#8d99a6;font-size:13px;margin-top:4px}
.mspe-head-right{margin-left:auto;text-align:right;min-width:190px}
.mspe-prog-lbl{font-size:11px;color:#8d99a6;text-transform:uppercase;letter-spacing:.05em;margin-bottom:5px}
.mspe-prog{width:190px;height:8px;background:#e9edf0;border-radius:20px;overflow:hidden;display:inline-block}
.mspe-prog span{display:block;height:100%;width:0;background:#2490ef;border-radius:20px;transition:width .3s}
.mspe-prog-txt{font-size:12px;color:#42535f;font-weight:600;margin-top:5px}
.mspe-filters{display:flex;gap:30px;background:#fff;border:1px solid #e2e6e9;border-radius:12px;padding:16px 20px;margin-bottom:16px;flex-wrap:wrap}
.mspe-fld label{display:block;font-size:10px;letter-spacing:.05em;color:#8d99a6;text-transform:uppercase;margin-bottom:6px}
.mspe-select{border:1px solid #d1d8dd;border-radius:8px;height:34px;padding:0 12px;font-size:14px;min-width:200px;background:#fff;transition:border-color .15s}
.mspe-select:hover{border-color:#b7c0c8}
.mspe-select:focus{outline:none;border-color:#2490ef;box-shadow:0 0 0 2px rgba(36,144,239,.1)}
.mspe-select option[value="__all__"]{font-weight:700}
.mspe-ro{background:#f4f5f6;color:#8d99a6;border:1px solid #eef0f2;border-radius:8px;height:34px;min-width:180px;display:flex;align-items:center;padding:0 12px;font-size:14px}
.mspe-alert{border-radius:10px;padding:12px 16px;margin-bottom:16px;font-size:13px;font-weight:500}
.mspe-alert.err{background:#fdecec;border:1px solid #f5c2c2;color:#c0392b}
.mspe-alert.warn{background:#fff6e5;border:1px solid #f3dca6;color:#b9770e}
.mspe-cards{display:grid;grid-template-columns:repeat(4,1fr);gap:16px;margin-bottom:20px}
.mspe-card{background:#fff;border:1px solid #e2e6e9;border-radius:12px;padding:18px 20px;border-top:4px solid #2490ef}
.mspe-card.c-green{border-top-color:#1f9254}.mspe-card.c-purple{border-top-color:#7c4dff}.mspe-card.c-orange{border-top-color:#e8a33d}
.mspe-card .lbl{font-size:12px;color:#8d99a6;font-weight:600;margin-bottom:10px}
.mspe-card .val{font-size:26px;font-weight:700;line-height:1.1}
.mspe-card .cur{font-size:11px;color:#8d99a6;margin-top:4px}
.mspe-gridwrap{background:#fff;border:1px solid #e2e6e9;border-radius:12px;overflow:hidden;position:relative}
.mspe-grid-head{display:flex;align-items:center;justify-content:space-between;padding:14px 18px;border-bottom:1px solid #eef0f2}
.mspe-grid-head h3{font-size:15px;font-weight:700;margin:0}
.mspe-pill{background:#f4f5f6;border:1px solid #e2e6e9;border-radius:20px;padding:3px 11px;font-size:11px;color:#8d99a6}
.mspe-table-scroll{overflow-x:auto}
.mspe-table{width:100%;border-collapse:collapse;min-width:900px}
.mspe-table th,.mspe-table td{padding:8px 12px;font-size:13px}
.mspe-table tr.grp th{text-align:center;font-size:11px;text-transform:uppercase;letter-spacing:.04em;font-weight:700;color:#42535f;padding-bottom:4px;border-bottom:1px solid #f0f2f4}
.mspe-table tr.grp th.inv{color:#2490ef;border-bottom:2px solid #cbe3fb}
.mspe-table tr.grp th.bkd{color:#7c4dff;border-bottom:2px solid #ddd0fb}
.mspe-table tr.cols th{font-size:10px;text-transform:uppercase;letter-spacing:.03em;color:#8d99a6;font-weight:600;background:#fafbfc;text-align:right;border-bottom:1px solid #eef0f2}
.mspe-table tr.cols th.l{text-align:left}.mspe-table tr.cols th.c{text-align:center}
.mspe-table td.num,.mspe-table th.num{text-align:right}
.mspe-table td.l{text-align:left}.mspe-table td.c{text-align:center}
.mspe-table td.comments-cell{max-width:280px;white-space:normal;word-break:break-word;vertical-align:top}
.mspe-comments{display:flex;flex-direction:column;gap:4px}
.mspe-comment-item{line-height:1.4}
.mspe-comment-item .who{font-weight:700;color:#42535f}
.mspe-table tbody td{border-bottom:1px solid #f2f4f6}
.mspe-table tbody tr:hover td{background:#fafbfc}
.mspe-table td.month{font-weight:600}
.inv-first,.bkd-first{border-left:1px solid #f2f4f6}
.sticky-col{position:sticky;left:0;background:#fff;z-index:2}
tr.cols .sticky-col{background:#fafbfc}
.mspe-table tfoot td{font-weight:700;background:#fafbfc;border-top:2px solid #e2e6e9;font-size:13px}
.gp-chip{font-size:11px;font-weight:700;color:#1f9254}.gp-chip.lo{color:#e8703a}
.sdot{display:inline-flex;align-items:center;gap:6px;font-size:12px;color:#42535f}
.sdot i{width:10px;height:10px;border-radius:50%;display:inline-block}
.sdot.saved i{background:#1f9254}.sdot.draft i{background:#e8a33d}.sdot.empty i{background:#cdd6dd}
.ro-cell{color:#1f272e}
.mspe-state{padding:40px;text-align:center;color:#8d99a6;font-size:13px}
.spinner{width:26px;height:26px;border:3px solid #e2e6e9;border-top-color:#2490ef;border-radius:50%;margin:0 auto 12px;animation:mspespin .8s linear infinite}
@keyframes mspespin{to{transform:rotate(360deg)}}
.mspe-footnote{color:#a6b0ba;font-size:11px;margin-top:12px;text-align:center}
@media(max-width:1024px){.mspe-cards{grid-template-columns:repeat(2,1fr)}.mspe-head-right{min-width:0}}
@media(max-width:640px){.mspe-cards{grid-template-columns:1fr}.mspe-filters{gap:14px}.mspe-select,.mspe-ro{min-width:140px}}
		`;
		document.head.appendChild(style);
	}

	$(page.body).html(`
<div id="mspe-root" class="mspe-root">
  <div class="mspe-head">
    <div class="mspe-head-left">
      <h1 class="mspe-title">Monthly Sales Performance Entry</h1>
      <div class="mspe-sub" id="mspe-sub">Loading&hellip;</div>
    </div>
    <div class="mspe-head-right">
      <div class="mspe-prog-lbl">Progress</div>
      <div class="mspe-prog"><span id="mspe-prog-bar"></span></div>
      <div class="mspe-prog-txt" id="mspe-prog-txt">&mdash;</div>
    </div>
  </div>

  <div class="mspe-filters">
    <div class="mspe-fld">
      <label>Fiscal Year</label>
      <select id="mspe-fy" class="mspe-select"></select>
    </div>
    <div class="mspe-fld">
      <label>Salesperson</label>
      <select id="mspe-sp" class="mspe-select"></select>
    </div>
    <div class="mspe-fld">
      <label>Data Basis</label>
      <div class="mspe-ro" id="mspe-basis">Sales Data</div>
    </div>
  </div>

  <div id="mspe-alert" class="mspe-alert" style="display:none"></div>

  <div class="mspe-cards">
    <div class="mspe-card c-blue"><div class="lbl">Invoiced Revenue</div><div class="val" id="kpi-ir">&mdash;</div><div class="cur">AED</div></div>
    <div class="mspe-card c-green"><div class="lbl">Invoiced GP</div><div class="val" id="kpi-ig">&mdash;</div><div class="cur">AED</div></div>
    <div class="mspe-card c-purple"><div class="lbl">Booked Revenue</div><div class="val" id="kpi-br">&mdash;</div><div class="cur">AED</div></div>
    <div class="mspe-card c-orange"><div class="lbl">Booked GP</div><div class="val" id="kpi-bg">&mdash;</div><div class="cur">AED</div></div>
  </div>

  <div class="mspe-gridwrap">
    <div class="mspe-grid-head">
      <h3>Monthly Data Entry</h3>
      <span class="mspe-pill">Currency: AED &middot; Read-only preview</span>
    </div>
    <div class="mspe-table-scroll">
      <table class="mspe-table">
        <thead>
          <tr class="grp">
            <th class="sticky-col"></th>
            <th class="inv" colspan="3">Invoiced Sales</th>
            <th class="bkd" colspan="3">Booked Sales</th>
            <th></th><th></th>
          </tr>
          <tr class="cols">
            <th class="sticky-col l">Month</th>
            <th class="inv-first num">Revenue</th><th class="num">GP</th><th class="num">GP %</th>
            <th class="bkd-first num">Revenue</th><th class="num">GP</th><th class="num">GP %</th>
            <th class="l">Comments</th><th class="c">Status</th>
          </tr>
        </thead>
        <tbody id="mspe-tbody"></tbody>
        <tfoot>
          <tr class="tot">
            <td class="sticky-col l">Total</td>
            <td class="inv-first num" id="tot-ir">0.00</td><td class="num" id="tot-ig">0.00</td><td class="num"></td>
            <td class="bkd-first num" id="tot-br">0.00</td><td class="num" id="tot-bg">0.00</td><td class="num"></td>
            <td colspan="2"></td>
          </tr>
        </tfoot>
      </table>
    </div>
    <div id="mspe-loading" class="mspe-state"><div class="spinner"></div><div>Loading data&hellip;</div></div>
    <div id="mspe-empty" class="mspe-state" style="display:none">No data entered yet for this selection. All twelve months are ready for entry.</div>
  </div>

  <div class="mspe-footnote">Read-only preview &middot; Figures, GP %, totals and status are calculated by the ERPNext backend.</div>
</div>
	`);

	const MSPE_METHOD = {
		allowed_sales_persons: "bsgroup.bs_group.page.monthly_sales_entry.monthly_sales_entry.stgp_allowed_sales_persons",
		load_entry: "bsgroup.bs_group.page.monthly_sales_entry.monthly_sales_entry.stgp_load_entry",
	};

	function $id(id) {
		return wrapper.querySelector("#" + id);
	}
	function money(n) {
		n = Number(n) || 0;
		return n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
	}
	function money0(n) {
		n = Number(n) || 0;
		return "AED " + n.toLocaleString("en-US", { maximumFractionDigits: 0 });
	}
	function pct(n) {
		return (Number(n) || 0).toFixed(1) + "%";
	}
	function esc(s) {
		const d = document.createElement("div");
		d.textContent = s == null ? "" : String(s);
		return d.innerHTML;
	}

	function showAlert(kind, msg) {
		const a = $id("mspe-alert");
		a.className = "mspe-alert " + kind;
		a.textContent = msg;
		a.style.display = "block";
	}
	function hideAlert() {
		const a = $id("mspe-alert");
		if (a) a.style.display = "none";
	}
	function setLoading(on) {
		const l = $id("mspe-loading");
		if (l) l.style.display = on ? "block" : "none";
	}
	function setEmpty(on) {
		const e = $id("mspe-empty");
		if (e) e.style.display = on ? "block" : "none";
	}

	function statusCell(st) {
		const cls = st === "Saved" ? "saved" : st === "Draft" ? "draft" : "empty";
		const lbl = st || "Not Entered";
		return '<span class="sdot ' + cls + '"><i></i>' + esc(lbl) + "</span>";
	}

	function commentsCell(m) {
		const list = m.comments_list;
		if (Array.isArray(list) && list.length) {
			return (
				'<div class="mspe-comments">' +
				list
					.map(
						(c) =>
							'<div class="mspe-comment-item"><span class="who">' +
							esc(c.salesperson) +
							":</span> " +
							esc(c.text) +
							"</div>"
					)
					.join("") +
				"</div>"
			);
		}
		return esc(m.comments || "");
	}

	function renderGrid(data) {
		const tb = $id("mspe-tbody");
		tb.innerHTML = "";
		const t = { ir: 0, ig: 0, br: 0, bg: 0 };
		let done = 0;
		(data.months || []).forEach((m) => {
			const ir = Number(m.invoiced_sales_revenue) || 0,
				ig = Number(m.invoiced_sales_gp) || 0;
			const br = Number(m.booked_sales_revenue) || 0,
				bg = Number(m.booked_sales_gp) || 0;
			t.ir += ir;
			t.ig += ig;
			t.br += br;
			t.bg += bg;
			if (ir || ig || br || bg) done++;
			const igp = Number(m.invoiced_gp_pct) || 0,
				bgp = Number(m.booked_gp_pct) || 0;
			const igpHtml = ir > 0 ? '<span class="gp-chip' + (igp < 30 ? " lo" : "") + '">' + pct(igp) + "</span>" : "";
			const bgpHtml = br > 0 ? '<span class="gp-chip' + (bgp < 30 ? " lo" : "") + '">' + pct(bgp) + "</span>" : "";
			const tr = document.createElement("tr");
			tr.innerHTML =
				'<td class="sticky-col month l">' + esc(m.month) + "</td>" +
				'<td class="inv-first num ro-cell">' + money(ir) + "</td>" +
				'<td class="num ro-cell">' + money(ig) + "</td>" +
				'<td class="num">' + igpHtml + "</td>" +
				'<td class="bkd-first num ro-cell">' + money(br) + "</td>" +
				'<td class="num ro-cell">' + money(bg) + "</td>" +
				'<td class="num">' + bgpHtml + "</td>" +
				'<td class="l ro-cell comments-cell">' + commentsCell(m) + "</td>" +
				'<td class="c">' + statusCell(m.status) + "</td>";
			tb.appendChild(tr);
		});

		const tot = data.totals || {};
		$id("tot-ir").textContent = money(tot.total_invoiced_revenue != null ? tot.total_invoiced_revenue : t.ir);
		$id("tot-ig").textContent = money(tot.total_invoiced_gp != null ? tot.total_invoiced_gp : t.ig);
		$id("tot-br").textContent = money(tot.total_booked_revenue != null ? tot.total_booked_revenue : t.br);
		$id("tot-bg").textContent = money(tot.total_booked_gp != null ? tot.total_booked_gp : t.bg);
		$id("kpi-ir").textContent = money0(tot.total_invoiced_revenue != null ? tot.total_invoiced_revenue : t.ir);
		$id("kpi-ig").textContent = money0(tot.total_invoiced_gp != null ? tot.total_invoiced_gp : t.ig);
		$id("kpi-br").textContent = money0(tot.total_booked_revenue != null ? tot.total_booked_revenue : t.br);
		$id("kpi-bg").textContent = money0(tot.total_booked_gp != null ? tot.total_booked_gp : t.bg);
		$id("mspe-prog-bar").style.width = (done / 12) * 100 + "%";
		$id("mspe-prog-txt").textContent = done + " of 12 months";
		setEmpty(done === 0);
	}

	function currentSelection() {
		return { sp: $id("mspe-sp").value, fy: $id("mspe-fy").value };
	}
	function updateSub() {
		const s = currentSelection();
		const spSel = $id("mspe-sp");
		const spText = spSel.options[spSel.selectedIndex];
		$id("mspe-sub").textContent = "FY " + (s.fy || "-") + "  ·  " + ((spText && spText.textContent) || "-") + "  ·  Sales Data";
	}

	function loadData() {
		const s = currentSelection();
		if (!s.sp || !s.fy) {
			setLoading(false);
			return;
		}
		hideAlert();
		setLoading(true);
		setEmpty(false);
		updateSub();
		frappe.call({
			method: MSPE_METHOD.load_entry,
			args: { salesperson: s.sp, fiscal_year: s.fy },
			callback: function (r) {
				setLoading(false);
				if (r && r.message) {
					$id("mspe-basis").textContent = r.message.data_basis || "Sales Data";
					renderGrid(r.message);
				}
			},
			error: function (err) {
				setLoading(false);
				let m = "Unable to load data.";
				try {
					const sm = JSON.parse((err && err._server_messages) || "[]");
					if (sm.length) m = JSON.parse(sm[0]).message;
				} catch (e) {}
				if (err && err.exc_type === "PermissionError") m = "You do not have permission to view this data.";
				showAlert("err", m);
			},
		});
	}

	function initFiscalYears() {
		return frappe
			.call({
				method: "frappe.client.get_list",
				args: { doctype: "Fiscal Year", fields: ["name"], order_by: "name desc", limit_page_length: 0 },
			})
			.then(function (r) {
				const sel = $id("mspe-fy");
				sel.innerHTML = "";
				(r.message || []).forEach((fy) => {
					const o = document.createElement("option");
					o.value = fy.name;
					o.textContent = fy.name;
					sel.appendChild(o);
				});
			});
	}
	const ALL_SALES_PERSONS = "__all__";

	function initSalespersons() {
		return frappe.call({ method: MSPE_METHOD.allowed_sales_persons }).then(function (r) {
			const sel = $id("mspe-sp");
			sel.innerHTML = "";
			const list = (r.message || []).slice().sort();
			if (!list.length) {
				const o = document.createElement("option");
				o.value = "";
				o.textContent = "No accessible salespersons";
				sel.appendChild(o);
				sel.disabled = true;
				return;
			}
			const allOpt = document.createElement("option");
			allOpt.value = ALL_SALES_PERSONS;
			allOpt.textContent = "All Salespersons";
			sel.appendChild(allOpt);
			list.forEach((sp) => {
				const o = document.createElement("option");
				o.value = sp;
				o.textContent = sp;
				sel.appendChild(o);
			});
			sel.value = ALL_SALES_PERSONS;
		});
	}

	function boot() {
		Promise.all([initFiscalYears(), initSalespersons()])
			.then(function () {
				$id("mspe-fy").addEventListener("change", loadData);
				$id("mspe-sp").addEventListener("change", loadData);
				loadData();
			})
			.catch(function () {
				setLoading(false);
				showAlert("err", "Failed to initialise the page filters.");
			});
	}

	boot();
};
