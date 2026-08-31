// Project Command Centre - persistent auto-loader
// Artifact version : 2026-08-08-frozen.11
// Artifact SHA-256 : 363d044c…e6a6e628  (full hash recorded in change log)
// Scope            : Desk only, Project List route only (Client Script dt=Project view=List)
// Duplicate guards : artifact self-guards + launcher presence check below
// Visibility gate  : launcher + overlay shown only to Projects Manager or System Manager.
//                    UI-level only - it grants nothing and changes no permission record.
//                    Underlying Project/Task read permissions are unchanged.
// Rollback         : set enabled = 0 on this Client Script, or delete it.
//                    No other record, field, setting or document is modified.
window.__pcc_loader_ran = (window.__pcc_loader_ran || 0) + 1;
function __pccRunArtifact() {
/* ===== BEGIN ARTIFACT 2026-08-08-frozen.11 (verbatim) ===== */

/* ============================================================================
 * Bits Secure - Project Command Centre  (self-contained runtime build)
 * version: 2026-08-08-frozen.11        READ-ONLY. No Project/Task/Employee writes.
 * Paste into the console of an authenticated ERPNext Desk session.
 * ==========================================================================*/
(function () {
'use strict';
var VERSION = '2026-08-08-frozen.11';
var OVERLAY_ID = 'project-command-centre-overlay';
var STYLE_ID = 'pcc-style';
var LAUNCH_CLS = 'pcc-launcher-btn';

/* ---- idempotency: neutralise any previous instance ---- */
var prev = window.bits_pmo_command_centre_build;
if (prev && typeof prev.destroy === 'function') { try { prev.destroy(); } catch (e) {} }

/* ================= configuration (FROZEN) ================= */
var RAG_CFG = { critical_overdue: 10, amber_overdue_min: 3, material_behind: 25, moderate_behind: 10, due_soon_days: 14 };
var AMC_TYPES = ['Remote AMC', 'PPM AMC', 'Adhoc AMC'];
var AMC_RE = /(^|[^a-z0-9])amc([^a-z0-9]|$)|\bmaintenance\b/i;
var AMC_EXCL_RE = /non[\s\-_]*amc/i;
var TASK_CLOSED = ['Completed', 'Cancelled'];
var S_PM = '__unassigned__', S_CUST = '__no_customer__', S_TYPE = '__no_type__';
var L_PM = 'Unassigned', L_CUST = 'No Customer';
var L_TYPE = { projects: 'No Project Type', amc: 'No AMC Type' };
var DASH = '\u2014';

/* ================= helpers ================= */
function today() { return frappe.datetime.get_today(); }
function dt(v) { if (!v) return null; var s = String(v).trim().replace(' ', 'T'); if (s.length <= 10) s += 'T00:00:00'; var d = new Date(s); return isNaN(d) ? null : d; }
function daysTo(s) { if (!s) return null; var a = dt(s), b = dt(today()); return Math.round((a - b) / 86400000); }
function isBlank(v) { return v === null || v === undefined || String(v).trim() === ''; }
function num(v) { var n = parseFloat(v); return isNaN(n) ? 0 : n; }
function esc(s) { return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) { return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]; }); }
var MON = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
function fmtDate(s) { var d = dt(s); if (!d || isNaN(d)) return DASH; return String(d.getDate()).padStart(2, '0') + ' ' + MON[d.getMonth()] + ' ' + String(d.getFullYear()).slice(2); }

/* ================= data layer ================= */
var D = {};
D.RAG_CFG = RAG_CFG;
D.isBlankCustomer = function (r) { return isBlank(r && r.customer); };
D.isBlankProjectType = function (r) { return isBlank(r && r.project_type); };
D.isBlankPm = function (r) { return isBlank(r && r.project_manager); };
D.isTypedAmc = function (r) { return AMC_TYPES.indexOf(r.project_type) !== -1; };
D.isLegacyNameAmc = function (name) {
  var s = String(name || '');
  if (AMC_EXCL_RE.test(s)) return false;
  return AMC_RE.test(s);
};
/* single partition predicate: used for AMC inclusion AND Open-Project exclusion */
D.isAmc = function (r) { return D.isTypedAmc(r) || D.isLegacyNameAmc(r.project_name || r.name); };
D.isOpenProject = function (r) {
  if (D.isAmc(r)) return false;
  var st = String(r.status || '').toLowerCase();
  return st === 'open' || st === 'on hold';
};
D.isAmcContract = function (r) {
  if (!D.isAmc(r)) return false;
  return String(r.status || '').toLowerCase() !== 'cancelled';
};
D.elapsedPct = function (r) {
  var s = r.expected_start_date, e = r.expected_end_date;
  if (!s || !e) return null;
  var a = dt(s), b = dt(e), n = dt(today());
  var span = (b - a) / 86400000; if (span <= 0) return null;
  var gone = (n - a) / 86400000;
  return Math.max(0, Math.min(100, (gone / span) * 100));
};
D.scheduleVariance = function (r) {
  var el = D.elapsedPct(r); if (el === null) return null;
  return num(r.percent_complete) - el;
};
D.expiryBucket = function (days) {
  if (days === null || days === undefined) return 'missing';
  if (days < 0) return 'expired';
  if (days <= 30) return '0_30';
  if (days <= 60) return '31_60';
  return 'gt_60';
};
D.expiryLabel = function (days) {
  if (days === null || days === undefined) return DASH;
  if (days < 0) return 'Renewal Overdue ' + Math.abs(days) + 'd';
  return 'Renewal in ' + days + 'd';
};
/* ---- delivery RAG (FROZEN semantics + evaluation order) ---- */
D.deliveryRag = function (r) {
  var c = RAG_CFG, reasons = [], pc = num(r.percent_complete);
  var end = r.expected_end_date, days = end ? daysTo(end) : null;
  var v = D.scheduleVariance(r), ov = num(r.overdue_tasks);
  /* RED - material delivery failure */
  if (end && days < 0 && pc < 100) return { rag: 'red', reasons: ['Past due by ' + Math.abs(days) + 'd at ' + Math.round(pc) + '%'] };
  if (ov > c.critical_overdue) return { rag: 'red', reasons: [ov + ' overdue tasks'] };
  if (v !== null && v <= -c.material_behind) return { rag: 'red', reasons: [Math.abs(v).toFixed(1) + ' pts behind elapsed schedule'] };
  /* AMBER - attention, incl. ownership gaps */
  if (end && days >= 0 && days <= c.due_soon_days && pc < 100) reasons.push('Due in ' + days + 'd at ' + Math.round(pc) + '%');
  if (ov >= c.amber_overdue_min) reasons.push(ov + ' overdue tasks');
  if (D.isBlankPm(r)) reasons.push('No project manager');
  if (v !== null && v <= -c.moderate_behind) reasons.push(Math.abs(v).toFixed(1) + ' pts behind elapsed schedule');
  if (reasons.length) return { rag: 'amber', reasons: reasons };
  /* GREY - missing baseline only, no stronger exception */
  if (!end) return { rag: 'grey', reasons: ['No expected end date'] };
  /* GREEN - no material delivery exception (not "zero overdue tasks") */
  return { rag: 'green', reasons: [] };
};
D.deliverySort = function (a, b) {
  var order = { red: 0, amber: 1, grey: 2, green: 3 };
  var d = order[a.rag] - order[b.rag]; if (d) return d;
  var da = a.days_remaining === null || a.days_remaining === undefined ? Infinity : a.days_remaining;
  var db = b.days_remaining === null || b.days_remaining === undefined ? Infinity : b.days_remaining;
  if (da !== db) return da - db;
  return num(b.overdue_tasks) - num(a.overdue_tasks);
};
D.nextMilestone = function (tasks) {
  var open = tasks.filter(function (t) { return TASK_CLOSED.indexOf(t.status) === -1; });
  if (!open.length) return { task: null, due: null, overdue: false };
  var dated = open.filter(function (t) { return !!t.exp_end_date; })
                  .sort(function (x, y) { return dt(x.exp_end_date) - dt(y.exp_end_date); });
  var pick = dated.length ? dated[0] : open[0];   /* fallback: undated open task */
  return { task: pick.subject, due: pick.exp_end_date || null, overdue: pick.status === 'Overdue' };
};
D.fetchProjects = function () {
  return frappe.call({ method: 'frappe.client.get_list', args: { doctype: 'Project',
    fields: ['name','project_name','customer','project_type','status','percent_complete','expected_start_date','expected_end_date','custom_project_manager'],
    limit_page_length: 0, order_by: 'modified desc' } }).then(function (r) { return r.message || []; });
};
D.fetchTasks = function () {
  return frappe.call({ method: 'frappe.client.get_list', args: { doctype: 'Task',
    fields: ['name','subject','project','status','exp_end_date','priority'],
    limit_page_length: 0, order_by: 'modified desc' } }).then(function (r) { return r.message || []; });
};
D.employeeNames = function () {
  return frappe.call({ method: 'frappe.client.get_list', args: { doctype: 'Employee',
    fields: ['name','employee_name'], limit_page_length: 0 } }).then(function (r) {
    var m = {}; (r.message || []).forEach(function (e) { m[e.name] = e.employee_name || e.name; }); return m; });
};
D.taskRollup = function (tasks) {
  var by = {};
  tasks.forEach(function (t) {
    if (!t.project) return;
    var b = by[t.project] || (by[t.project] = { open: 0, overdue: 0, completed: 0, list: [] });
    var closed = TASK_CLOSED.indexOf(t.status) !== -1;
    if (!closed) b.open++;
    if (t.status === 'Overdue') b.overdue++;
    if (t.status === 'Completed') b.completed++;
    b.list.push(t);
  });
  return by;
};

/* ================= model layer ================= */
var M = { _cache: null };
M.clear = function () { M._cache = null; };
M._build = function () {
  return Promise.all([D.fetchProjects(), D.fetchTasks(), D.employeeNames()]).then(function (res) {
    var projects = res[0], tasks = res[1], emp = res[2];
    var roll = D.taskRollup(tasks);
    var mk = function (p) {
      var b = roll[p.name] || { open: 0, overdue: 0, completed: 0, list: [] };
      var nm = D.nextMilestone(b.list);
      var pmId = p.custom_project_manager;
      return {
        name: p.name, project_name: p.project_name || p.name, customer: p.customer,
        project_type: p.project_type, status: p.status,
        project_manager: pmId ? (emp[pmId] || pmId) : null,
        percent_complete: num(p.percent_complete),
        expected_start_date: p.expected_start_date, expected_end_date: p.expected_end_date,
        days_remaining: p.expected_end_date ? daysTo(p.expected_end_date) : null,
        running_days: p.expected_start_date ? -daysTo(p.expected_start_date) : null,
        on_hold: String(p.status || '').toLowerCase() === 'on hold',
        open_tasks: b.open, overdue_tasks: b.overdue, completed_tasks: b.completed,
        tasks: b.list, next_task: nm.task, next_due: nm.due, next_overdue: nm.overdue,
        schedule_variance: null, rag: null, rag_reasons: []
      };
    };
    var delivery = projects.filter(D.isOpenProject).map(mk);
    delivery.forEach(function (r) {
      r.schedule_variance = D.scheduleVariance(r);
      var g = D.deliveryRag(r); r.rag = g.rag; r.rag_reasons = g.reasons;
    });
    delivery.sort(D.deliverySort);
    var amc = projects.filter(D.isAmcContract).map(mk);
    amc.forEach(function (r) {
      r.contract_start = r.expected_start_date;          /* no dedicated AMC fields exist */
      r.contract_expiry = r.expected_end_date;
      r.days_to_expiry = r.contract_expiry ? daysTo(r.contract_expiry) : null;
      r.expiry_bucket = D.expiryBucket(r.days_to_expiry);
    });
    amc.sort(function (a, b) {
      var da = a.days_to_expiry === null ? Infinity : a.days_to_expiry;
      var db = b.days_to_expiry === null ? Infinity : b.days_to_expiry;
      return da - db;
    });
    M._cache = { projects: delivery, amc: amc, as_of: today() };
    return M._cache;
  });
};
M._data = function () { return M._cache ? Promise.resolve(M._cache) : M._build(); };
/* skipDim => that dimension is NOT cut, which is what keeps facets non-dead-ending */
M._apply = function (rows, f, skipDim) {
  f = f || {};
  return rows.filter(function (r) {
    if (skipDim !== 'pm' && f.pm) {
      if (f.pm === S_PM) { if (!D.isBlankPm(r)) return false; }
      else if (r.project_manager !== f.pm) return false;
    }
    if (skipDim !== 'customer' && f.customer) {
      if (f.customer === S_CUST) { if (!D.isBlankCustomer(r)) return false; }
      else if (r.customer !== f.customer) return false;
    }
    if (skipDim !== 'type' && f.type) {
      if (f.type === S_TYPE) { if (!D.isBlankProjectType(r)) return false; }
      else if (r.project_type !== f.type) return false;
    }
    if (skipDim !== 'bucket' && f.bucket) { if (r.expiry_bucket !== f.bucket) return false; }
    return true;
  });
};
M._uniq = function (rows, key) {
  var seen = {}, out = [];
  rows.forEach(function (r) { var v = r[key]; if (isBlank(v) || seen[v]) return; seen[v] = 1; out.push(v); });
  return out.sort(function (a, b) { return String(a).localeCompare(String(b)); });
};
M._facets = function (rows, f, view) {
  f = f || {};
  var res = {
    pm: M._uniq(M._apply(rows, f, 'pm'), 'project_manager').map(function (v) { return [v, v]; }),
    customer: M._uniq(M._apply(rows, f, 'customer'), 'customer').map(function (v) { return [v, v]; }),
    type: M._uniq(M._apply(rows, f, 'type'), 'project_type').map(function (v) { return [v, v]; })
  };
  var specs = [
    { dim: 'pm', sentinel: S_PM, label: L_PM, pred: D.isBlankPm },
    { dim: 'customer', sentinel: S_CUST, label: L_CUST, pred: D.isBlankCustomer },
    { dim: 'type', sentinel: S_TYPE, label: (L_TYPE[view] || L_TYPE.projects), pred: D.isBlankProjectType }
  ];
  specs.forEach(function (s) {
    if (view === 'amc' && s.dim === 'pm') return;   /* AMC In-Charge has no sentinel (out of approved scope) */
    var scoped = M._apply(rows, Object.assign({}, f, (function () { var o = {}; o[s.dim] = ''; return o; })()), s.dim);
    var need = scoped.some(s.pred) || f[s.dim] === s.sentinel;
    if (need && !res[s.dim].some(function (p) { return p[0] === s.sentinel; })) res[s.dim].unshift([s.sentinel, s.label]);
  });
  return res;
};
M.projectKpis = function (rows) {
  var k = { total: rows.length, on_track: 0, attention: 0, overdue: 0, open_tasks: 0, overdue_tasks: 0 };
  rows.forEach(function (r) {
    if (r.rag === 'green') k.on_track++;
    else if (r.rag === 'amber') k.attention++;
    else if (r.rag === 'red') k.overdue++;
    k.open_tasks += num(r.open_tasks); k.overdue_tasks += num(r.overdue_tasks);
  });
  return k;
};
M.amcKpis = function (rows) {
  var k = { total: rows.length, expiring_30: 0, expiring_60: 0, expired: 0, no_expiry: 0, overdue_tasks: 0 };
  rows.forEach(function (r) {
    if (r.expiry_bucket === '0_30') k.expiring_30++;
    else if (r.expiry_bucket === '31_60') k.expiring_60++;
    else if (r.expiry_bucket === 'expired') k.expired++;
    else if (r.expiry_bucket === 'missing') k.no_expiry++;
    k.overdue_tasks += num(r.overdue_tasks);
  });
  return k;
};
/* KPIs computed on the scoped set BEFORE the At Risk cut */
M.query = function (view, f) {
  return M._data().then(function (c) {
    var all = view === 'amc' ? c.amc : c.projects;
    var facets = M._facets(all, f, view);
    var scoped = M._apply(all, f);
    var kpis = view === 'amc' ? M.amcKpis(scoped) : M.projectKpis(scoped);
    var total_before_risk = scoped.length;
    var rows = scoped;
    if (f && f.risk) {
      rows = view === 'amc'
        ? scoped.filter(function (r) { return r.expiry_bucket === 'expired' || r.expiry_bucket === '0_30'; })
        : scoped.filter(function (r) { return r.rag === 'red' || r.rag === 'amber'; });
    }
    return { rows: rows, kpis: kpis, facets: facets, as_of: c.as_of, total_before_risk: total_before_risk };
  });
};

/* ================= ui layer ================= */
var CSS = [
'#project-command-centre-overlay{position:fixed;left:var(--pcc-left,0px);right:0;bottom:0;top:var(--pcc-top,50px);background:#fff;z-index:1010;overflow:auto;padding:10px 14px;font-size:12px;color:#333}',
'.pcc-hd{display:flex;align-items:flex-start;justify-content:space-between;margin-bottom:8px}',
'.pcc-t1{font-size:14px;font-weight:600;color:#1f272e}.pcc-t2{font-size:11px;color:#8d99a6}',
'.pcc-btns .btn{margin-left:4px}',
'.pcc-kpis{display:grid;grid-template-columns:repeat(6,1fr);gap:8px;margin-bottom:8px}',
'.pcc-kpi{border:1px solid #e8ebee;border-left:3px solid #b9c0c7;border-radius:4px;padding:6px 8px;background:#fff}',
'.pcc-kpi .v{font-size:16px;font-weight:600;line-height:1.1}.pcc-kpi .l{font-size:9px;letter-spacing:.4px;color:#8d99a6;text-transform:uppercase}',
'.pcc-kpi.g{border-left-color:#22c55e}.pcc-kpi.a{border-left-color:#f59e0b}.pcc-kpi.r{border-left-color:#ef4444}.pcc-kpi.n{border-left-color:#94a3b8}',
'.pcc-filters{display:flex;align-items:center;gap:6px;margin-bottom:6px;flex-wrap:wrap}',
'.pcc-filters select{font-size:11px;padding:2px 6px;border:1px solid #d7dde3;border-radius:4px;background:#fff;max-width:190px}',
'.pcc-chip{font-size:11px;padding:3px 8px;border:1px solid #d7dde3;border-radius:4px;background:#fff;cursor:pointer}',
'.pcc-chip.on{background:#111;color:#fff;border-color:#111}',
'.pcc-count{margin-left:auto;font-size:10px;color:#8d99a6}',
'.pcc-tbl{width:100%;border-collapse:collapse;table-layout:fixed}',
'.pcc-tbl th{font-size:9px;letter-spacing:.4px;text-transform:uppercase;color:#8d99a6;text-align:left;font-weight:500;padding:4px 6px;border-bottom:1px solid #e8ebee}',
'.pcc-tbl td{padding:4px 6px;border-bottom:1px solid #f2f4f6;vertical-align:middle;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}',
'.pcc-tbl tr td:first-child{border-left:3px solid transparent}',
'.pcc-tbl tr.r td:first-child{border-left-color:#ef4444}.pcc-tbl tr.a td:first-child{border-left-color:#f59e0b}',
'.pcc-tbl tr.g td:first-child{border-left-color:#22c55e}.pcc-tbl tr.n td:first-child{border-left-color:#cbd5e1}',
    // --- frozen first column (2026-08-08-frozen.11) ---
    '#project-command-centre-overlay .pcc-tbl th:first-child,#project-command-centre-overlay .pcc-tbl td:first-child{position:sticky;left:-14px;z-index:2;background:#fff}',
    '#project-command-centre-overlay .pcc-tbl th:first-child{z-index:3;box-shadow:1px 0 0 #e8ebee,inset 0 -1px 0 #e8ebee}',
    '#project-command-centre-overlay .pcc-tbl td:first-child{box-shadow:1px 0 0 #e8ebee,inset 0 -1px 0 #f2f4f6}',
    '#project-command-centre-overlay .pcc-tbl tr.r td:first-child{box-shadow:inset 3px 0 0 #ef4444,1px 0 0 #e8ebee,inset 0 -1px 0 #f2f4f6}',
    '#project-command-centre-overlay .pcc-tbl tr.a td:first-child{box-shadow:inset 3px 0 0 #f59e0b,1px 0 0 #e8ebee,inset 0 -1px 0 #f2f4f6}',
    '#project-command-centre-overlay .pcc-tbl tr.g td:first-child{box-shadow:inset 3px 0 0 #22c55e,1px 0 0 #e8ebee,inset 0 -1px 0 #f2f4f6}',
    '#project-command-centre-overlay .pcc-tbl tr.n td:first-child{box-shadow:inset 3px 0 0 #cbd5e1,1px 0 0 #e8ebee,inset 0 -1px 0 #f2f4f6}',
'.pcc-lnk{color:#1e3a8a;cursor:pointer}.pcc-lnk:hover{text-decoration:underline}',
// --- name legibility tier (2026-08-08-frozen.11) ---
'#project-command-centre-overlay .pcc-lnk{font-weight:500}',
'.pcc-mut{color:#b1b8bf}',
'.pcc-num{cursor:pointer;font-weight:500}.pcc-num.z{color:#b1b8bf;cursor:default;font-weight:400}.pcc-num.od{color:#ef4444}',
'.pcc-bar{display:inline-block;width:44px;height:4px;background:#eef1f4;border-radius:2px;vertical-align:middle;margin-right:5px;overflow:hidden}',
'.pcc-bar i{display:block;height:100%;background:#22c55e}',
'.pcc-badge{display:inline-block;font-size:9px;padding:1px 5px;border-radius:3px;font-weight:600;letter-spacing:.3px}',
'.pcc-badge.r{background:#fee2e2;color:#b91c1c}.pcc-badge.a{background:#fef3c7;color:#92400e}',
'.pcc-badge.g{background:#dcfce7;color:#166534}.pcc-badge.n{background:#eef1f4;color:#64748b}',
'.pcc-late{margin-left:4px;font-size:9px;color:#b91c1c;background:#fee2e2;padding:0 4px;border-radius:3px}',
'.pcc-foot{margin-top:8px;font-size:10px;color:#b1b8bf}',
'.pcc-leg{margin-top:3px;font-size:10px;color:#8d99a6}.pcc-leg i{display:inline-block;width:7px;height:7px;border-radius:2px;margin:0 3px 0 8px}',
'.pcc-dl td{padding:3px 0;font-size:12px}.pcc-dl td:first-child{width:180px;color:#8d99a6;padding-right:10px}',
// --- responsive css patch (2026-08-08-frozen.11) ---
'#project-command-centre-overlay .pcc-tbl{min-width:1230px}',
    '#project-command-centre-overlay .pcc-run{display:inline-block;padding:1px 6px;border-radius:9px;background:#f1f5f9;color:#334155;font-size:11px;font-weight:600;font-variant-numeric:tabular-nums}',
    // --- kpi label colour + running-days bands (2026-08-08-frozen.11) ---
    '#project-command-centre-overlay .pcc-kpi .l{color:#1e3a8a}',
    '#project-command-centre-overlay .pcc-run.rd1{background:#dcfce7;color:#15803d}',
    '#project-command-centre-overlay .pcc-run.rd2{background:#f3e8ff;color:#7e22ce}',
    '#project-command-centre-overlay .pcc-run.rd3{background:#fee2e2;color:#b91c1c}',
'#project-command-centre-overlay{scrollbar-width:thin;-webkit-overflow-scrolling:touch}',
'#project-command-centre-overlay::-webkit-scrollbar{height:11px;width:11px}',
'#project-command-centre-overlay::-webkit-scrollbar-track{background:rgba(0,0,0,.05);border-radius:6px}',
'#project-command-centre-overlay::-webkit-scrollbar-thumb{background:rgba(0,0,0,.30);border-radius:6px}',
'#project-command-centre-overlay::-webkit-scrollbar-thumb:hover{background:rgba(0,0,0,.45)}',
'#project-command-centre-overlay .pcc-hd,#project-command-centre-overlay .pcc-kpis,#project-command-centre-overlay .pcc-filters,#project-command-centre-overlay .pcc-foot,#project-command-centre-overlay .pcc-leg{position:sticky;left:0}',
'#project-command-centre-overlay .pcc-filters{flex-wrap:wrap}',
'@media (max-width:1017px){#project-command-centre-overlay .pcc-kpis{grid-template-columns:repeat(3,1fr)}}',
'@media (max-width:640px){#project-command-centre-overlay .pcc-kpis{grid-template-columns:repeat(2,1fr)}}',
// --- cosmetic css polish (2026-08-08-frozen.11) ---
'#project-command-centre-overlay .pcc-tbl thead th{text-transform:uppercase;letter-spacing:.04em;font-size:10px;font-weight:600;color:#64748b}',
'#project-command-centre-overlay .pcc-badge{display:inline-block;padding:2px 8px;border-radius:999px;font-size:11px;font-weight:600}',
'#project-command-centre-overlay .pcc-num{font-weight:600}',
'#project-command-centre-overlay .pcc-kpi{border-radius:8px}',
'#project-command-centre-overlay .pcc-tbl tbody tr:hover{background:#f8fafc}',
// --- launcher colour (2026-08-08-frozen.11) ---
'.btn.pcc-launcher-btn{background:#2563eb !important;border-color:#2563eb !important;color:#fff !important;font-weight:600}',
'.btn.pcc-launcher-btn:hover,.btn.pcc-launcher-btn:focus,.btn.pcc-launcher-btn:active{background:#1d4ed8 !important;border-color:#1d4ed8 !important;color:#fff !important;box-shadow:none}'
].join('\n');

function injectCss() {
  var el = document.getElementById(STYLE_ID);
  if (el) el.parentNode.removeChild(el);          /* idempotent: never duplicate styles */
  el = document.createElement('style'); el.id = STYLE_ID; el.textContent = CSS;
  document.head.appendChild(el);
}
var U = {};
U.S = { tab: 'projects', pm: '', customer: '', type: '', bucket: '', risk: false, last: null };
U.BUCKETS = [['expired', 'Renewal Overdue'], ['0_30', 'Within 30d'], ['31_60', '31-60d'], ['gt_60', 'Over 60d'], ['missing', 'Renewal Date Not Set']];
U.sel = function (key, value, opts, placeholder) {
  var h = '<select data-f="' + key + '"><option value="">' + esc(placeholder) + '</option>';
  opts.forEach(function (o) {
    var v = Array.isArray(o) ? o[0] : o, l = Array.isArray(o) ? o[1] : o;
    h += '<option value="' + esc(v) + '"' + (String(value) === String(v) ? ' selected' : '') + '>' + esc(l) + '</option>';
  });
  return h + '</select>';
};
U.kpiStrip = function (view, k) {
  var defs = view === 'amc'
    ? [['n', k.total, 'AMC Contracts'], ['a', k.expiring_30, 'Renewal Due ≤30 Days'], ['a', k.expiring_60, 'Renewal Due in 31–60 Days'],
       ['r', k.expired, 'Renewal Overdue'], ['n', k.no_expiry, 'Renewal Date Not Set'], ['r', k.overdue_tasks, 'Overdue Tasks']]
    : [['n', k.total, 'Open Projects'], ['g', k.on_track, 'On Track'], ['a', k.attention, 'Needs Attention'],
       ['r', k.overdue, 'Overdue'], ['n', k.open_tasks, 'Open Tasks'], ['r', k.overdue_tasks, 'Overdue Tasks']];
  return '<div class="pcc-kpis">' + defs.map(function (d) {
    return '<div class="pcc-kpi ' + d[0] + '"><div class="v">' + d[1] + '</div><div class="l">' + esc(d[2]) + '</div></div>';
  }).join('') + '</div>';
};
U.pct = function (v) {
  var n = Math.max(0, Math.min(100, Math.round(num(v))));
  return '<span class="pcc-bar"><i style="width:' + n + '%"></i></span>' + n + '%';
};
U.daysLabel = function (d) {
  if (d === null || d === undefined) return '<span class="pcc-mut">' + DASH + '</span>';
  if (d < 0) return '<span class="pcc-badge r">Overdue ' + Math.abs(d) + 'd</span>';
  if (d <= RAG_CFG.due_soon_days) return '<span class="pcc-badge a">' + d + 'd left</span>';
  return '<span class="pcc-badge g">' + d + 'd left</span>';
};
U.numCell = function (n, projectName, mode) {
  n = num(n);
  if (!n) return '<span class="pcc-num z">0</span>';
  return '<span class="pcc-num' + (mode === 'overdue' ? ' od' : '') + '" data-tasks="' + esc(projectName) + '" data-mode="' + mode + '">' + n + '</span>';
};
U.blank = function (v) { return isBlank(v) ? '<span class="pcc-mut">' + DASH + '</span>' : esc(v); };
U.firstName = function (v) { if (!v) return v; var s = String(v).trim().replace(/\s+/g, ' '); if (!s) return v; return s.split(' ')[0]; };
U.runDays = function (d) {
  if (d === null || d === undefined) return '<span class="pcc-mut">' + DASH + '</span>';
  if (d < 0) return '<span class="pcc-mut">Not started</span>';
  var band = d > 60 ? 'rd3' : (d > 30 ? 'rd2' : 'rd1');
    return '<span class="pcc-run ' + band + '">' + d + 'd</span>';
};
U.tt = function (v) { return isBlank(v) ? '' : ' title="' + esc(v) + '"'; };
U.pmCell = function (v) { return isBlank(v) ? '<span class="pcc-mut">' + L_PM + '</span>' : esc(v); };

/* ---- frozen 10-column delivery table (NO Status column) ---- */
U.renderProjects = function (rows) {
  var cols = [['Project','21%'],['Customer','13%'],['PM','10%'],['% Complete','8%'],['Exp. Start','7%'],
              ['Exp. End','7%'],['Running Days','7%'],['Timeline','8%'],['Open Tasks','4%'],['Overdue Tasks','5%'],['Next Milestone / Task','10%']];
  var h = '<table class="pcc-tbl"><colgroup>' + cols.map(function (c) { return '<col style="width:' + c[1] + '">'; }).join('') + '</colgroup><thead><tr>' +
    cols.map(function (c) { return '<th>' + esc(c[0]) + '</th>'; }).join('') + '</tr></thead><tbody>';
  rows.forEach(function (r) {
    var cls = r.rag === 'red' ? 'r' : r.rag === 'amber' ? 'a' : r.rag === 'green' ? 'g' : 'n';
    var reason = (r.rag_reasons || []).join('; ');
    h += '<tr class="' + cls + '" title="' + esc(reason) + '">' +
      '<td title="' + esc(r.project_name) + '"><span class="pcc-lnk" data-detail="' + esc(r.name) + '">' + esc(r.project_name) + '</span>' +
        (r.on_hold ? ' <span class="pcc-badge n">ON HOLD</span>' : '') + '</td>' +
      '<td' + U.tt(r.customer) + '>' + U.blank(r.customer) + '</td>' +
      '<td' + U.tt(r.project_manager) + '>' + U.pmCell(U.firstName(r.project_manager)) + '</td>' +
      '<td>' + U.pct(r.percent_complete) + '</td>' +
      '<td>' + fmtDate(r.expected_start_date) + '</td>' +
      '<td>' + fmtDate(r.expected_end_date) + '</td>' +
          '<td>' + U.runDays(r.running_days) + '</td>' +
      '<td>' + U.daysLabel(r.days_remaining) + '</td>' +
      '<td>' + U.numCell(r.open_tasks, r.name, 'open') + '</td>' +
      '<td>' + U.numCell(r.overdue_tasks, r.name, 'overdue') + '</td>' +
      '<td' + U.tt(r.next_task) + '>' + (r.next_task ? esc(r.next_task) + (r.next_overdue ? '<span class="pcc-late">late</span>' : '') : '<span class="pcc-mut">' + DASH + '</span>') + '</td>' +
      '</tr>';
  });
  return h + '</tbody></table>';
};
/* ---- frozen 10-column AMC table (NO Status, NO % Complete) ---- */
U.renderAmc = function (rows) {
  var cols = [['AMC / Contract','19%'],['Customer','12%'],['AMC In-Charge','10%'],['AMC Type','7%'],['Contract Start','8%'],
              ['Renewal Due','8%'],['Running Days','7%'],['Days to Renewal','12%'],['Open Tasks','4%'],['Overdue Tasks','4%'],['Next Scheduled Visit','9%']];
  var h = '<table class="pcc-tbl"><colgroup>' + cols.map(function (c) { return '<col style="width:' + c[1] + '">'; }).join('') + '</colgroup><thead><tr>' +
    cols.map(function (c) { return '<th>' + esc(c[0]) + '</th>'; }).join('') + '</tr></thead><tbody>';
  rows.forEach(function (r) {
    var b = r.expiry_bucket;
    var cls = b === 'expired' ? 'r' : (b === '0_30' || b === '31_60') ? 'a' : b === 'missing' ? 'n' : 'g';
    h += '<tr class="' + cls + '">' +
      '<td title="' + esc(r.project_name) + '"><span class="pcc-lnk" data-project="' + esc(r.name) + '">' + esc(r.project_name) + '</span></td>' +
      '<td' + U.tt(r.customer) + '>' + U.blank(r.customer) + '</td>' +
      '<td' + U.tt(r.project_manager) + '>' + U.pmCell(U.firstName(r.project_manager)) + '</td>' +
      '<td>' + U.blank(r.project_type) + '</td>' +
      '<td>' + fmtDate(r.contract_start) + '</td>' +
      '<td>' + fmtDate(r.contract_expiry) + '</td>' +
          '<td>' + U.runDays(r.running_days) + '</td>' +
      '<td>' + (r.days_to_expiry === null ? '<span class="pcc-mut">' + DASH + '</span>'
              : '<span class="pcc-badge ' + (r.days_to_expiry < 0 ? 'r' : r.days_to_expiry <= 60 ? 'a' : 'g') + '">' + D.expiryLabel(r.days_to_expiry) + '</span>') + '</td>' +
      '<td>' + U.numCell(r.open_tasks, r.name, 'open') + '</td>' +
      '<td>' + U.numCell(r.overdue_tasks, r.name, 'overdue') + '</td>' +
      '<td' + U.tt(r.next_task) + '>' + (r.next_task ? esc(r.next_task) + (r.next_overdue ? '<span class="pcc-late">late</span>' : '') : '<span class="pcc-mut">' + DASH + '</span>') + '</td>' +
      '</tr>';
  });
  return h + '</tbody></table>';
};

/* ================= controller ================= */
var C = { data: D, model: M, ui: U, version: VERSION, alive: true };

C.paint = function () {
  var S = U.S, view = S.tab;
  var f = { pm: S.pm, customer: S.customer, type: S.type, bucket: S.bucket, risk: S.risk };
  return M.query(view, f).then(function (res) {
    S.last = res;
    var host = document.getElementById(OVERLAY_ID); if (!host) return res;
    var typePlaceholder = view === 'amc' ? 'AMC Type: All' : 'Project Type: All';
    var pmPlaceholder = view === 'amc' ? 'AMC In-Charge: All' : 'Project Manager: All';
    var h = '';
    h += '<div class="pcc-hd"><div><div class="pcc-t1">Project Command Centre</div>' +
         '<div class="pcc-t2">Bits Secure IT Infrastructure ' + DASH + ' ' + (view === 'amc' ? 'maintenance portfolio' : 'delivery portfolio') + ' overview</div></div>' +
         '<div class="pcc-btns">' +
         '<button class="btn btn-xs ' + (view === 'projects' ? 'btn-primary' : 'btn-default') + '" data-tab="projects">Open Projects</button>' +
         '<button class="btn btn-xs ' + (view === 'amc' ? 'btn-primary' : 'btn-default') + '" data-tab="amc">AMC / Maintenance</button>' +
         '<button class="btn btn-xs btn-default" data-act="refresh">Refresh</button>' +
         '<button class="btn btn-xs btn-default" data-act="export">Export</button>' +
         '<button class="btn btn-xs btn-default" data-act="close">Close</button>' +
         '</div></div>';
    h += U.kpiStrip(view, res.kpis);
    h += '<div class="pcc-filters">' +
         U.sel('pm', S.pm, res.facets.pm, pmPlaceholder) +
         U.sel('customer', S.customer, res.facets.customer, 'Customer: All') +
         U.sel('type', S.type, res.facets.type, typePlaceholder) +
         (view === 'amc' ? U.sel('bucket', S.bucket, U.BUCKETS, 'Renewal Status: All') : '') +
         '<span class="pcc-chip' + (S.risk ? ' on' : '') + '" data-act="risk">' + (view === 'amc' ? 'Renewal Due / Overdue' : 'At Risk / Overdue') + '</span>' +
         '<span class="pcc-count">Showing ' + res.rows.length + ' of ' + res.total_before_risk + '</span>' +
         '</div>';
    h += (view === 'amc' ? U.renderAmc(res.rows) : U.renderProjects(res.rows));
    h += '<div class="pcc-foot">Source: Project + Task (live, read-only) ' + DASH + ' AMC = typed Project Type supplemented by legacy name match ' + DASH + ' as of ' + esc(res.as_of) + '</div>';
    h += '<div class="pcc-leg"><i style="background:#22c55e"></i>On Track<i style="background:#f59e0b"></i>Attention<i style="background:#ef4444"></i>Overdue<i style="background:#cbd5e1"></i>No Baseline</div>';
    host.innerHTML = h;
    return res;
  });
};
C.onClick = function (ev) {
  var t = ev.target.closest('[data-tab],[data-act],[data-detail],[data-project],[data-tasks]');
  if (!t || !document.getElementById(OVERLAY_ID)) return;
  var S = U.S;
  if (t.dataset.tab) { if (S.tab !== t.dataset.tab) { S.tab = t.dataset.tab; S.pm = S.customer = S.type = S.bucket = ''; S.risk = false; C.paint(); } return; }
  if (t.dataset.act === 'close') { C.unmount(); return; }
  if (t.dataset.act === 'refresh') { M.clear(); C.paint(); return; }
  if (t.dataset.act === 'export') { C.exportCsv(); return; }
  if (t.dataset.act === 'risk') { S.risk = !S.risk; C.paint(); return; }
  if (t.dataset.detail) { C.detail(t.dataset.detail); return; }
  if (t.dataset.project) { frappe.set_route('Form', 'Project', t.dataset.project); return; }
  if (t.dataset.tasks) { C.gotoTasks(t.dataset.tasks, t.dataset.mode); return; }
};
C.onChange = function (ev) {
  var s = ev.target; if (!s || s.tagName !== 'SELECT' || !s.dataset.f) return;
  if (!document.getElementById(OVERLAY_ID)) return;
  U.S[s.dataset.f] = s.value; C.paint();
};
C.gotoTasks = function (project, mode) {
  var f = { project: project };
  if (mode === 'overdue') f.status = 'Overdue';
  else f.status = ['not in', TASK_CLOSED];
  frappe.set_route('List', 'Task', f);
};

/* ---- delivery detail dialog (11 fields incl. Project Type) ---- */
C.detail = function (name) {
  var res = U.S.last; if (!res) return;
  var r = (res.rows || []).filter(function (x) { return x.name === name; })[0];
  if (!r) return;
  var row = function (l, v) { return '<tr><td>' + esc(l) + '</td><td>' + v + '</td></tr>'; };
  var sig = { red: 'r', amber: 'a', green: 'g', grey: 'n' }[r.rag] || 'n';
  var sv = r.schedule_variance;
  var svTxt = sv === null ? DASH + ' (no baseline)'
    : '<b style="color:' + (sv < 0 ? '#b91c1c' : '#166534') + '">' + (sv >= 0 ? '+' : '') + sv.toFixed(1) + ' pts</b> ' + (sv < 0 ? 'behind' : 'ahead of') + ' elapsed schedule';
  var open = (r.tasks || []).filter(function (t) { return TASK_CLOSED.indexOf(t.status) === -1; });
  var dated = open.filter(function (t) { return !!t.exp_end_date; }).sort(function (a, b) { return dt(a.exp_end_date) - dt(b.exp_end_date); });
  var undated = open.filter(function (t) { return !t.exp_end_date; });
  var next5 = dated.concat(undated).slice(0, 5);
  var h = '<table class="pcc-dl" style="width:100%">' +
    row('Project', '<b>' + esc(r.project_name) + '</b>') +
    row('Customer', U.blank(r.customer)) +
    row('Project Manager', U.pmCell(r.project_manager)) +
    row('Project Type', isBlank(r.project_type) ? '<span class="pcc-mut">' + DASH + '</span>' : esc(r.project_type)) +
    row('Delivery Signal', '<span class="pcc-badge ' + sig + '">' + String(r.rag).toUpperCase() + '</span>') +
    row('Risk Reasons', (r.rag_reasons && r.rag_reasons.length) ? esc(r.rag_reasons.join('; ')) : '<span class="pcc-mut">' + DASH + '</span>') +
    row('% Complete', U.pct(r.percent_complete)) +
    row('Schedule Variance', svTxt) +
    row('Expected Start', fmtDate(r.expected_start_date)) +
    row('Expected End', fmtDate(r.expected_end_date)) +
        row('Running Days', r.running_days === null || r.running_days === undefined ? '<span class="pcc-mut">' + DASH + '</span>' : (r.running_days < 0 ? '<span class="pcc-mut">Not started</span>' : '<b>' + r.running_days + 'd</b>')) +
    row('Days Remaining / Overdue', r.days_remaining === null ? '<span class="pcc-mut">' + DASH + '</span>'
        : (r.days_remaining < 0 ? '<b style="color:#b91c1c">' + Math.abs(r.days_remaining) + 'd overdue</b>' : '<b>' + r.days_remaining + 'd remaining</b>')) +
    '</table><hr style="margin:8px 0">' +
    '<div style="display:flex;gap:26px;margin-bottom:6px">' +
      '<div><div style="font-size:16px;font-weight:600">' + num(r.open_tasks) + '</div><div class="l" style="font-size:9px;color:#8d99a6;text-transform:uppercase">Open tasks</div></div>' +
      '<div><div style="font-size:16px;font-weight:600;color:#b91c1c">' + num(r.overdue_tasks) + '</div><div style="font-size:9px;color:#8d99a6;text-transform:uppercase">Overdue tasks</div></div>' +
      '<div><div style="font-size:16px;font-weight:600;color:#166534">' + num(r.completed_tasks) + '</div><div style="font-size:9px;color:#8d99a6;text-transform:uppercase">Completed tasks</div></div>' +
    '</div>' +
    '<div style="font-weight:600;margin-top:6px">Next Milestone / Task</div>' +
    '<div style="margin-bottom:6px">' + (r.next_task ? esc(r.next_task) + ' ' + DASH + ' <span class="pcc-mut">' + (r.next_due ? fmtDate(r.next_due) : 'no date') + '</span>' : '<span class="pcc-mut">' + DASH + '</span>') + '</div>' +
    '<div style="font-weight:600;margin-top:6px">Next 5 delivery activities</div><table style="width:100%">' +
    (next5.length ? next5.map(function (t) {
      return '<tr><td style="padding:2px 0">' + esc(t.subject) + '</td>' +
             '<td style="width:90px;color:#8d99a6">' + (t.exp_end_date ? fmtDate(t.exp_end_date) : 'no date') + '</td>' +
             '<td style="width:150px;color:#8d99a6">' + esc(t.status) + '</td></tr>'; }).join('')
      : '<tr><td class="pcc-mut">No open activities</td></tr>') + '</table>';
  var dlg = new frappe.ui.Dialog({ title: 'Delivery Detail', size: 'large' });
  dlg.$body.html(h);
  dlg.set_primary_action('Open Project', function () { dlg.hide(); frappe.set_route('Form', 'Project', r.name); });
  dlg.$wrapper.find('.modal-footer').prepend(
    '<button class="btn btn-default btn-sm" data-dact="open">View Open Tasks</button> ' +
    '<button class="btn btn-default btn-sm" data-dact="overdue">View Overdue Tasks</button> ');
  dlg.$wrapper.on('click', '[data-dact]', function () {
    var m = this.getAttribute('data-dact'); dlg.hide(); C.gotoTasks(r.name, m === 'overdue' ? 'overdue' : 'open');
  });
  dlg.show();
  return dlg;
};

/* ---- export: delivery 13 cols / AMC 10 cols, readable blank labels, never sentinels ---- */
function csvEscape(v) { return '"' + String(v == null ? '' : v).replace(/"/g, '""') + '"'; }
C.toCsv = function () {
  var S = U.S, res = S.last; if (!res) return '';
  var rows = res.rows || [], recs = [];
  if (S.tab === 'amc') {
    recs.push(['AMC / Contract','Customer','AMC In-Charge','AMC Type','Contract Start','Renewal Due','Running Days','Days to Renewal','Open Tasks','Overdue Tasks','Next Scheduled Visit']);
    rows.forEach(function (r) {
      recs.push([ r.project_name,
        D.isBlankCustomer(r) ? L_CUST : r.customer,
        D.isBlankPm(r) ? L_PM : r.project_manager,
        D.isBlankProjectType(r) ? L_TYPE.amc : r.project_type,
        r.contract_start || '', r.contract_expiry || '',
            r.running_days === null || r.running_days === undefined ? '' : r.running_days,
        r.days_to_expiry === null ? '' : r.days_to_expiry,
        num(r.open_tasks), num(r.overdue_tasks), r.next_task || '' ]);
    });
  } else {
    recs.push(['Project','Customer','Project Manager','Project Type','% Complete','Expected Start','Expected End','Running Days','Days Remaining','Open Tasks','Overdue Tasks','Next Milestone / Task','Delivery Signal','Risk Reasons']);
    rows.forEach(function (r) {
      recs.push([ r.project_name,
        D.isBlankCustomer(r) ? L_CUST : r.customer,
        D.isBlankPm(r) ? L_PM : r.project_manager,
        D.isBlankProjectType(r) ? L_TYPE.projects : r.project_type,
        Math.round(num(r.percent_complete)) + '%',
        r.expected_start_date || '', r.expected_end_date || '',
            r.running_days === null || r.running_days === undefined ? '' : r.running_days,
        r.days_remaining === null ? '' : r.days_remaining,
        num(r.open_tasks), num(r.overdue_tasks), r.next_task || '',
        String(r.rag).toUpperCase(), (r.rag_reasons || []).join('; ') ]);
    });
  }
  return recs.map(function (r) { return r.map(csvEscape).join(','); }).join('\r\n');
};
C.exportCsv = function () {
  var text = C.toCsv();
  var blob = new Blob([text], { type: 'text/csv;charset=utf-8;' });
  var url = URL.createObjectURL(blob);
  var a = document.createElement('a');
  a.href = url; a.download = 'bits-command-centre_' + U.S.tab + '_' + today() + '.csv';
  document.body.appendChild(a); a.click(); document.body.removeChild(a);
  setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
  return text;
};

/* ================= lifecycle ================= */
function routeIsProject() {
  var r = (frappe.get_route() || []);
  return r[0] === 'List' && r[1] === 'Project';
}
C.mount = function () {
  if (!C.alive) return Promise.resolve(null);
  if (document.getElementById(OVERLAY_ID)) return C.paint();   /* duplicate mount guard */
  injectCss();
  var main = document.querySelector('.layout-main') || document.querySelector('.layout-main-section');
  var head = document.querySelector('.page-head');
  var side = document.querySelector('.body-sidebar');
  var mr = main ? main.getBoundingClientRect() : null;
  var top = mr ? Math.round(mr.top) : (head ? Math.round(head.getBoundingClientRect().bottom) : 50);
  var left = mr ? Math.round(mr.left) : (side ? Math.round(side.getBoundingClientRect().width) : 0);
  var el = document.createElement('div');
  el.id = OVERLAY_ID;
  el.style.setProperty('--pcc-top', top + 'px');
  el.style.setProperty('--pcc-left', left + 'px');
  document.body.appendChild(el);
  el.addEventListener('click', C.onClick);
  el.addEventListener('change', C.onChange);
  return C.paint();
};
C.unmount = function () {
  var el = document.getElementById(OVERLAY_ID);
  if (el) { el.removeEventListener('click', C.onClick); el.removeEventListener('change', C.onChange); el.parentNode.removeChild(el); }
};
/* ---- launcher on the native Project List page ---- */
function addLauncher(listview) {
  try {
    if (!C.alive) return;
    var page = listview && listview.page; if (!page) return;
    var wrap = page.wrapper ? (page.wrapper.get ? page.wrapper.get(0) : page.wrapper) : null;
    if (wrap && wrap.querySelector('.' + LAUNCH_CLS)) return;                   /* no duplicate buttons */
    if (!wrap && document.querySelector('.' + LAUNCH_CLS)) return;
    var $btn = page.add_inner_button('Command Centre', function () { C.mount(); });
    if ($btn && $btn.addClass) $btn.addClass(LAUNCH_CLS);
    else if ($btn && $btn.classList) $btn.classList.add(LAUNCH_CLS);
  } catch (e) { console.warn('[PCC] launcher error', e); }
}
frappe.listview_settings = frappe.listview_settings || {};
frappe.listview_settings['Project'] = frappe.listview_settings['Project'] || {};
var prevOnload = frappe.listview_settings['Project'].__pcc_wrapped ? null : frappe.listview_settings['Project'].onload;
frappe.listview_settings['Project'].onload = function (listview) {
  if (prevOnload) { try { prevOnload(listview); } catch (e) {} }
  addLauncher(listview);
};
frappe.listview_settings['Project'].__pcc_wrapped = true;
/* if the Project list is already open, attach immediately */
(function attachNow() {
  try {
    if (!routeIsProject()) return;
    var lv = (typeof cur_list !== 'undefined' && cur_list) ? cur_list : null;
    if (!lv && frappe.get_list_view) { try { lv = frappe.get_list_view('Project'); } catch (e) {} }
    if (lv) addLauncher(lv);
  } catch (e) { console.warn('[PCC] attach error', e); }
})();
/* ---- route teardown; no auto-remount ---- */
function onRouteChange() {
  if (!C.alive) return;                       /* stale handler from a previous build */
  if (!routeIsProject()) { C.unmount(); return; }
  setTimeout(function () {
    try { if (routeIsProject() && cur_list) addLauncher(cur_list); } catch (e) {}
  }, 300);
}
if (frappe.router && frappe.router.on) frappe.router.on('change', onRouteChange);
$(document).on('page-change.pcc_' + Date.now(), onRouteChange);

/* ================= public api ================= */
C.destroy = function () {
  C.alive = false;
  try { C.unmount(); } catch (e) {}
  var st = document.getElementById(STYLE_ID); if (st) st.parentNode.removeChild(st);
  document.querySelectorAll('.' + LAUNCH_CLS).forEach(function (b) { try { b.remove(); } catch (e) {} });
  try { $(document).off('.pcc_' + ''); } catch (e) {}
};
window.bits_pmo = window.bits_pmo || {};
window.bits_pmo.command_centre = C;
injectCss(); // style present from load so the launcher is coloured before first open
window.bits_pmo_command_centre_build = {
  version: VERSION,
  mounted: function () { return !!document.getElementById(OVERLAY_ID); },
  config: RAG_CFG,
  sentinels: { pm: S_PM, customer: S_CUST, type: S_TYPE },
  api: C,
  destroy: C.destroy
};
console.log('%c[Bits Secure] Project Command Centre ' + VERSION + ' loaded (read-only).', 'color:#2490ef');
})();

/* ===== END ARTIFACT ===== */
}
(function () {
  var tries = 0;
  var PCC_ALLOWED_ROLES = ["Projects Manager", "System Manager"];
  function pccRoles() {
    var r = (window.frappe && frappe.boot && frappe.boot.user && frappe.boot.user.roles) || null;
    if ((!r || !r.length) && window.frappe && frappe.user_roles && frappe.user_roles.length) r = frappe.user_roles;
    return (r && r.length) ? r : null;
  }
  function pccRoleAllowed() {
    var r = pccRoles();
    if (!r) return null;
    for (var i = 0; i < PCC_ALLOWED_ROLES.length; i++) { if (r.indexOf(PCC_ALLOWED_ROLES[i]) !== -1) return true; }
    return false;
  }
  function onProjectList() {
    var r = (window.frappe && frappe.get_route) ? frappe.get_route() : null;
    return !!(r && r[0] === "List" && r[1] === "Project");
  }
  function boot() {
    if (!onProjectList()) return;
    var allowed = pccRoleAllowed();
    if (allowed === null) { if (tries++ < 80) setTimeout(boot, 250); return; }
    if (!allowed) { window.__pcc_role_blocked = 1; return; }
    if (document.querySelectorAll(".pcc-launcher-btn").length) return;
    try { __pccRunArtifact(); window.__pcc_boot_ok = (window.__pcc_boot_ok || 0) + 1; }
    catch (e) { window.__pcc_boot_err = String(e && e.message || e); console.error("PCC loader:", e); }
  }
  function wait() {
    if (onProjectList() && document.querySelector(".layout-main-section")) { boot(); return; }
    if (tries++ > 80) return;
    setTimeout(wait, 250);
  }
  wait();
  if (!window.__pcc_router_hooked && window.frappe && frappe.router && frappe.router.on) {
    window.__pcc_router_hooked = 1;
    frappe.router.on("change", function () { setTimeout(boot, 400); });
  }
})();
