const _cr = {
    selected_user:       null,
    user_label:          "All Users",
    from_date:           null,
    to_date:             null,
    selected_status:     null,
    status_label:        "All Status",
    selected_department: null,
    department_label:    "All Departments",
};

frappe.pages["cheque-request-das"].on_page_load = function (wrapper) {
    const page = frappe.ui.make_app_page({
        parent: wrapper,
        title: "Cheque Request Dashboard",
        single_column: true,
    });

    // ── CSS ──────────────────────────────────────────────────────────────────
    if (!document.getElementById("crd-styles")) {
        const s = document.createElement("style");
        s.id = "crd-styles";
        s.textContent = `
            /* ── Mild Blue Theme Variables ── */
            .crd-root{
                --bg:#eef3fb;
                --bg-soft:#e2eaf6;
                --panel:#ffffff;
                --panel-2:#f4f8ff;
                --border:#cdd9ee;
                --border-soft:#dde6f5;
                --text:#1a2e4a;
                --muted:#5a7499;
                --title:#0f2040;
                --accent:#2563eb;
                --accent-light:#dbeafe;
                --green:#16a34a;
                --green-light:#dcfce7;
                --warn:#d97706;
                --warn-light:#fef3c7;
                --danger:#dc2626;
                --danger-light:#fee2e2;
                --info:#0284c7;
                --info-light:#e0f2fe;
                --purple:#7c3aed;
                --shadow:0 4px 20px rgba(37,99,235,0.08),0 1px 4px rgba(15,32,64,0.06);
                --shadow-md:0 8px 28px rgba(37,99,235,0.12),0 2px 8px rgba(15,32,64,0.08);
                --radius:16px;
            }
            /* ── Root wrapper ── */
            .crd-root{
                min-height:100vh;
                padding:16px;
                background:linear-gradient(160deg,#e8f0fd 0%,#eef3fb 50%,#e4edf9 100%);
                color:var(--text);
                font-family:Inter,ui-sans-serif,system-ui,sans-serif;
            }
            /* ── Topbar ── */
            .crd-topbar{
                display:flex;justify-content:space-between;align-items:center;
                gap:12px;flex-wrap:wrap;margin-bottom:16px;
                padding:16px 22px;
                background:linear-gradient(135deg,#1a3570 0%,#2054c8 55%,#3b82f6 100%);
                border-radius:20px;
                box-shadow:0 6px 24px rgba(37,99,235,0.3),0 2px 6px rgba(15,32,64,0.15);
                position:relative;z-index:10;
            }
            .crd-brand{display:flex;align-items:center;gap:13px;}
            .crd-badge{
                width:44px;height:44px;border-radius:12px;
                background:rgba(255,255,255,0.18);
                border:1.5px solid rgba(255,255,255,0.3);
                display:flex;align-items:center;justify-content:center;
                font-size:16px;font-weight:800;color:#fff;flex-shrink:0;
                box-shadow:0 3px 10px rgba(0,0,0,0.15);
            }
            .crd-brand h1{margin:0;font-size:20px;font-weight:800;color:#fff;letter-spacing:-.3px;}
            .crd-brand p{margin:4px 0 0;font-size:12px;color:rgba(255,255,255,0.75);}
            .crd-topbar-actions{display:flex;gap:7px;align-items:center;flex-wrap:wrap;}
            /* ── Topbar buttons ── */
            .crd-btn{
                border:none;outline:none;cursor:pointer;
                padding:8px 14px;border-radius:10px;
                font-weight:600;font-size:12px;transition:.18s ease;
                white-space:nowrap;position:relative;
            }
            .crd-btn-outline{
                color:rgba(255,255,255,0.92);
                background:rgba(255,255,255,0.13);
                border:1px solid rgba(255,255,255,0.26);
            }
            .crd-btn-outline:hover{background:rgba(255,255,255,0.24);border-color:rgba(255,255,255,0.5);}
            .crd-btn-outline.active{background:rgba(255,255,255,0.3);border-color:#fff;color:#fff;}
            .crd-btn-primary{
                color:var(--accent);
                background:#fff;
                font-size:13px;
                box-shadow:0 3px 10px rgba(0,0,0,0.14);
                border:1px solid transparent;
            }
            .crd-btn-primary:hover{transform:translateY(-1px);box-shadow:0 5px 14px rgba(0,0,0,0.18);}
            /* ── Dropdown ── */
            .crd-dd{
                position:absolute;
                top:calc(100% + 6px);
                left:0;
                background:#fff;
                border:1px solid var(--border);
                border-radius:12px;
                box-shadow:0 8px 30px rgba(37,99,235,0.18),0 2px 8px rgba(15,32,64,0.1);
                min-width:200px;z-index:9999;overflow:hidden;
            }
            .crd-dd-header{padding:8px 14px 4px;font-size:10px;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.07em;}
            .crd-dd-item{padding:9px 14px;font-size:13px;cursor:pointer;transition:background .12s;color:var(--text);}
            .crd-dd-item:hover{background:var(--accent-light);color:var(--accent);}
            .crd-dd-item.selected{color:var(--accent);font-weight:700;background:var(--accent-light);}
            .crd-dd-divider{border-top:1px solid var(--border-soft);margin:3px 0;}
            /* ── Layout ── */
            .crd-layout{display:grid;grid-template-columns:1.55fr .9fr;gap:14px;}
            .crd-left,.crd-right{display:flex;flex-direction:column;gap:14px;}
            /* ── Panel ── */
            .crd-panel{
                background:var(--panel);
                border:1px solid var(--border-soft);
                border-radius:var(--radius);
                box-shadow:var(--shadow);
            }
            .crd-ph{display:flex;justify-content:space-between;align-items:center;gap:12px;padding:16px 18px 0;}
            .crd-ph h2{margin:0;font-size:15px;font-weight:700;color:var(--title);}
            .crd-ph p{margin:3px 0 0;color:var(--muted);font-size:12px;}
            .crd-ph a.crd-btn{color:var(--accent);background:var(--accent-light);border:1px solid #bfdbfe;font-size:12px;}
            .crd-ph a.crd-btn:hover{background:#bfdbfe;}
            /* ── KPIs ── */
            .crd-kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;padding:14px 16px 18px;}
            .crd-kpi{
                background:var(--panel-2);
                border:1px solid var(--border-soft);
                border-radius:14px;padding:16px 14px;
                position:relative;overflow:hidden;
                transition:box-shadow .2s,transform .2s;
            }
            .crd-kpi:hover{box-shadow:var(--shadow-md);transform:translateY(-2px);}
            .crd-kpi::before{
                content:"";position:absolute;top:0;left:0;right:0;height:3px;
                border-radius:14px 14px 0 0;
                background:linear-gradient(90deg,var(--accent),#60a5fa);
            }
            .crd-kpi-label{font-size:12px;color:var(--muted);margin-bottom:10px;display:flex;justify-content:space-between;align-items:center;gap:6px;font-weight:500;}
            .crd-kpi-value{font-size:28px;font-weight:800;line-height:1;color:var(--title);margin-bottom:6px;}
            .crd-kpi-foot{font-size:12px;color:var(--muted);}
            .trend-up  {color:var(--green);font-weight:700;}
            .trend-warn{color:var(--warn);font-weight:700;}
            .trend-down{color:var(--danger);font-weight:700;}
            .trend-info{color:var(--info);font-weight:700;}
            /* ── Table ── */
            .crd-table-wrap{padding:12px 18px 18px;overflow:auto;}
            .crd-table{width:100%;border-collapse:collapse;min-width:500px;font-size:14px;}
            .crd-table th{
                text-align:left;font-size:11px;letter-spacing:.5px;text-transform:uppercase;
                color:var(--muted);padding:12px 12px;
                border-bottom:2px solid var(--border-soft);
                background:var(--panel-2);font-weight:700;
            }
            .crd-table td{padding:14px 12px;border-bottom:1px solid var(--border-soft);color:var(--text);font-size:14px;}
            .crd-table tr:last-child td{border-bottom:none;}
            .crd-table tr:hover td{background:#f0f6ff;}
            .crd-doc-id{font-weight:700;color:var(--title);}
            .crd-amount{font-weight:700;}
            .crd-footer-note{
                padding:10px 20px 14px;color:var(--muted);font-size:12px;
                border-top:1px solid var(--border-soft);
                background:var(--panel-2);border-radius:0 0 var(--radius) var(--radius);
            }
            /* ── Status tags ── */
            .crd-tag{
                display:inline-flex;align-items:center;
                padding:5px 12px;border-radius:999px;
                font-size:12px;font-weight:700;border:1px solid transparent;
            }
            .tag-draft       {color:#64748b;background:#f1f5f9;border-color:#e2e8f0;}
            .tag-pending     {color:#92400e;background:#fef3c7;border-color:#fde68a;}
            .tag-preapproved {color:#1d4ed8;background:#dbeafe;border-color:#bfdbfe;}
            .tag-prepared    {color:#0369a1;background:#e0f2fe;border-color:#bae6fd;}
            .tag-signing     {color:#6d28d9;background:#ede9fe;border-color:#ddd6fe;}
            .tag-signed      {color:#15803d;background:#dcfce7;border-color:#bbf7d0;}
            .tag-issued      {color:#166534;background:#bbf7d0;border-color:#86efac;}
            .tag-rejected    {color:#991b1b;background:#fee2e2;border-color:#fecaca;}
            .tag-cancelled   {color:#64748b;background:#f1f5f9;border-color:#e2e8f0;}
            .tag-overdue     {color:#991b1b;background:#fee2e2;border-color:#fca5a5;}
            /* ── Right col ── */
            .crd-side-content{padding:12px 14px 14px;display:flex;flex-direction:column;gap:8px;}
            .crd-mini{
                background:var(--panel-2);
                border:1px solid var(--border-soft);
                border-radius:10px;padding:11px 13px;
                border-left:3px solid var(--accent);
            }
            .crd-mini h3{margin:0 0 3px;font-size:12px;color:var(--title);font-weight:700;}
            .crd-mini .mv{font-size:20px;font-weight:800;margin-bottom:3px;}
            .crd-mini p{margin:0;font-size:12px;color:var(--muted);}
            /* ── Progress bars ── */
            .crd-prog-wrap{padding:14px 16px 16px;}
            .crd-prog-item{margin-bottom:13px;}
            .crd-prog-item:last-child{margin-bottom:0;}
            .crd-prog-top{display:flex;justify-content:space-between;font-size:12px;margin-bottom:6px;}
            .crd-prog-top span:first-child{color:var(--text);font-weight:600;}
            .crd-prog-top span:last-child{color:var(--muted);}
            .crd-bar{height:9px;border-radius:999px;background:#dbeafe;overflow:hidden;}
            .crd-fill{height:100%;border-radius:999px;background:linear-gradient(90deg,var(--accent),#60a5fa);}
            .crd-fill.green{background:linear-gradient(90deg,#16a34a,#4ade80);}
            .crd-fill.orange{background:linear-gradient(90deg,#d97706,#fbbf24);}
            .crd-fill.red{background:linear-gradient(90deg,#dc2626,#fb7185);}
            /* ── Doc link ── */
            .crd-doc-link{color:var(--accent);text-decoration:none;font-weight:600;}
            .crd-doc-link:hover{text-decoration:underline;}
            /* ── Loading ── */
            .crd-loading{text-align:center;padding:60px;color:var(--muted);font-size:15px;}
            /* ── Responsive ── */
            @media(max-width:1500px){
                .crd-kpis{grid-template-columns:repeat(2,1fr);}
            }
            @media(max-width:1400px){
                .crd-layout{grid-template-columns:1fr;}
                .crd-kpis{grid-template-columns:repeat(4,1fr);}
            }
            @media(max-width:1100px){
                .crd-kpis{grid-template-columns:repeat(2,1fr);}
            }
            @media(max-width:700px){
                .crd-root{padding:10px;}
                .crd-topbar{flex-direction:column;align-items:flex-start;}
                .crd-kpis{grid-template-columns:1fr;}
            }
        `;
        document.head.appendChild(s);
    }

    // ── Shell ────────────────────────────────────────────────────────────────
    $(page.body).html(`<div class="crd-root" id="crd-root">
        <div class="crd-topbar">
            <div class="crd-brand">
                <div class="crd-badge">CR</div>
                <div>
                    <h1>Cheque Request Dashboard</h1>
                    <p id="crd-subtitle">BS Group · Finance · Loading…</p>
                </div>
            </div>
            <div class="crd-topbar-actions">
                <!-- User filter -->
                <div style="position:relative">
                    <button class="crd-btn crd-btn-outline" id="crd-user-btn">👤 All Users</button>
                    <div class="crd-dd" id="crd-user-dd" style="display:none"></div>
                </div>
                <!-- Status filter -->
                <div style="position:relative">
                    <button class="crd-btn crd-btn-outline" id="crd-status-btn">📋 All Status</button>
                    <div class="crd-dd" id="crd-status-dd" style="display:none">
                        <div class="crd-dd-header">Filter by Status</div>
                        <div class="crd-dd-item selected" data-val="">All Status</div>
                        <div class="crd-dd-divider"></div>
                        <div class="crd-dd-item" data-val="Draft">Draft</div>
                        <div class="crd-dd-item" data-val="Pending Pre-Approval">Pending Pre-Approval</div>
                        <div class="crd-dd-item" data-val="Pre-Approved">Pre-Approved</div>
                        <div class="crd-dd-item" data-val="Prepared">Prepared</div>
                        <div class="crd-dd-item" data-val="Pending Signature">Pending Signature</div>
                        <div class="crd-dd-item" data-val="Signed">Signed</div>
                        <div class="crd-dd-item" data-val="Issued">Issued</div>
                        <div class="crd-dd-item" data-val="Rejected">Rejected</div>
                        <div class="crd-dd-item" data-val="Cancelled">Cancelled</div>
                    </div>
                </div>
                <!-- Department filter -->
                <div style="position:relative">
                    <button class="crd-btn crd-btn-outline" id="crd-dept-btn">🏢 All Departments</button>
                    <div class="crd-dd" id="crd-dept-dd" style="display:none"></div>
                </div>
                <!-- Date -->
                <button class="crd-btn crd-btn-outline" id="crd-date-btn">📅 This Month</button>
                <!-- Refresh -->
                <button class="crd-btn crd-btn-primary" id="crd-refresh">⟳ Refresh</button>
            </div>
        </div>
        <div id="crd-body"><div class="crd-loading">Loading cheque request data…</div></div>
    </div>`);


    // ── User dropdown ─────────────────────────────────────────────────────────
    $("#crd-user-btn").on("click", function (e) {
        e.stopPropagation();
        const $dd = $("#crd-user-dd");
        if ($dd.is(":visible")) { $dd.hide(); return; }
        $dd.html('<div class="crd-dd-item" style="color:var(--muted)">Loading…</div>').show();
        frappe.call({
            method: "bsgroup.bs_group.page.cheque_request_das.cheque_request_das.get_cheque_users",
            callback: function (r) {
                const users = r.message || [];
                let html = '<div class="crd-dd-header">Filter by Requester</div>';
                html += `<div class="crd-dd-item${!_cr.selected_user ? " selected" : ""}" data-user="">All Users</div>`;
                html += '<div class="crd-dd-divider"></div>';
                users.forEach(u => {
                    const name  = u.user || "";
                    const label = name.split("@")[0].replace(/\./g, " ").replace(/\b\w/g, c => c.toUpperCase());
                    html += `<div class="crd-dd-item${_cr.selected_user === name ? " selected" : ""}" data-user="${name}">${label}</div>`;
                });
                $dd.html(html);
            },
        });
    });
    $(document).on("click", "#crd-user-dd .crd-dd-item", function () {
        _cr.selected_user = $(this).data("user") || null;
        _cr.user_label    = $(this).text().trim();
        $("#crd-user-btn").text("👤 " + _cr.user_label).toggleClass("active", !!_cr.selected_user);
        $("#crd-user-dd").hide();
        load_dashboard();
    });

    // ── Status dropdown ───────────────────────────────────────────────────────
    $("#crd-status-btn").on("click", function (e) {
        e.stopPropagation();
        const $dd = $("#crd-status-dd");
        $dd.is(":visible") ? $dd.hide() : $dd.show();
    });
    $(document).on("click", "#crd-status-dd .crd-dd-item", function () {
        _cr.selected_status = $(this).data("val") || null;
        _cr.status_label    = $(this).text().trim();
        $("#crd-status-dd .crd-dd-item").removeClass("selected");
        $(this).addClass("selected");
        $("#crd-status-btn").text("📋 " + _cr.status_label).toggleClass("active", !!_cr.selected_status);
        $("#crd-status-dd").hide();
        load_dashboard();
    });

    // ── Department dropdown ───────────────────────────────────────────────────
    $("#crd-dept-btn").on("click", function (e) {
        e.stopPropagation();
        const $dd = $("#crd-dept-dd");
        if ($dd.is(":visible")) { $dd.hide(); return; }
        $dd.html('<div class="crd-dd-item" style="color:var(--muted)">Loading…</div>').show();
        frappe.call({
            method: "bsgroup.bs_group.page.cheque_request_das.cheque_request_das.get_departments",
            callback: function (r) {
                const depts = r.message || [];
                let html = '<div class="crd-dd-header">Filter by Department</div>';
                html += `<div class="crd-dd-item${!_cr.selected_department ? " selected" : ""}" data-dept="">All Departments</div>`;
                html += '<div class="crd-dd-divider"></div>';
                depts.forEach(d => {
                    html += `<div class="crd-dd-item${_cr.selected_department === d.department ? " selected" : ""}" data-dept="${d.department}">${d.department}</div>`;
                });
                $dd.html(html);
            },
        });
    });
    $(document).on("click", "#crd-dept-dd .crd-dd-item", function () {
        _cr.selected_department = $(this).data("dept") || null;
        _cr.department_label    = $(this).text().trim();
        $("#crd-dept-btn").text("🏢 " + _cr.department_label).toggleClass("active", !!_cr.selected_department);
        $("#crd-dept-dd").hide();
        load_dashboard();
    });

    // ── Date filter ───────────────────────────────────────────────────────────
    $("#crd-date-btn").on("click", function () {
        frappe.prompt(
            [
                { fieldname: "from_date", label: "From Date", fieldtype: "Date", reqd: 1,
                  default: _cr.from_date || frappe.datetime.month_start() },
                { fieldname: "to_date",   label: "To Date",   fieldtype: "Date", reqd: 1,
                  default: _cr.to_date   || frappe.datetime.month_end() },
            ],
            function (v) {
                _cr.from_date = v.from_date;
                _cr.to_date   = v.to_date;
                const lbl = frappe.datetime.str_to_user(v.from_date) + " → " + frappe.datetime.str_to_user(v.to_date);
                $("#crd-date-btn").text("📅 " + lbl).addClass("active");
                load_dashboard();
            },
            "Select Date Range", "Apply"
        );
    });

    // ── Close dropdowns on outside click ─────────────────────────────────────
    $(document).on("click", function (e) {
        if (!$(e.target).closest("#crd-user-btn,#crd-user-dd").length)     $("#crd-user-dd").hide();
        if (!$(e.target).closest("#crd-status-btn,#crd-status-dd").length) $("#crd-status-dd").hide();
        if (!$(e.target).closest("#crd-dept-btn,#crd-dept-dd").length)     $("#crd-dept-dd").hide();
    });

    $("#crd-refresh").on("click", () => load_dashboard());
    load_dashboard();

    // ── TV mode (?tv=1) ──────────────────────────────────────────────────────
    if (new URLSearchParams(window.location.search).get("tv") === "1") {
        document.querySelector(".navbar-expand")
            ?.style.setProperty("display", "none", "important");
        document.querySelector(".layout-side-section")
            ?.style.setProperty("display", "none", "important");
        document.querySelector(".page-head")
            ?.style.setProperty("display", "none", "important");
        document.querySelector(".layout-main-section-wrapper")
            ?.style.setProperty("padding", "0", "important");

        if (!document.getElementById("crd-tv-styles")) {
            const tv = document.createElement("style");
            tv.id = "crd-tv-styles";
            tv.textContent = `
                .crd-root        { padding: 28px 36px !important; }
                .crd-topbar      { padding: 18px 28px !important; border-radius: 22px !important; }
                .crd-brand h1    { font-size: clamp(22px, 2.4vw, 36px) !important; }
                .crd-brand p     { font-size: 15px !important; }
                .crd-kpi-label   { font-size: 15px !important; margin-bottom: 12px !important; }
                .crd-kpi-value   { font-size: clamp(48px, 5vw, 80px) !important; margin-bottom: 12px !important; }
                .crd-kpi-foot    { font-size: 14px !important; }
                .crd-kpi         { padding: 22px 20px !important; }
                .crd-ph h2       { font-size: clamp(18px, 1.8vw, 26px) !important; }
                .crd-table       { font-size: 16px !important; }
                .crd-table th    { font-size: 12px !important; padding: 12px !important; }
                .crd-table td    { padding: 16px 12px !important; }
                .crd-mini h3     { font-size: 16px !important; }
                .crd-mini .mv    { font-size: 28px !important; }
                .crd-prog-top    { font-size: 15px !important; }
            `;
            document.head.appendChild(tv);
        }

        // Auto-refresh every 60 seconds
        setInterval(() => load_dashboard(), 60000);
    }
};

// ── Helpers ──────────────────────────────────────────────────────────────────
function _fmt(val) {
    val = parseFloat(val) || 0;
    if (val >= 1e6) return "AED " + (val / 1e6).toFixed(1) + "M";
    if (val >= 1e3) return "AED " + Math.round(val / 1000) + "K";
    return "AED " + val.toLocaleString("en-US", { maximumFractionDigits: 0 });
}

function _link(name) {
    return `<a class="crd-doc-link" href="/app/cheque-request/${encodeURIComponent(name)}" target="_blank">${name}</a>`;
}

function _badge(s) {
    const map = {
        "Draft":               "tag-draft",
        "Pending Pre-Approval":"tag-pending",
        "Pre-Approved":        "tag-preapproved",
        "Prepared":            "tag-prepared",
        "Pending Signature":   "tag-signing",
        "Signed":              "tag-signed",
        "Issued":              "tag-issued",
        "Rejected":            "tag-rejected",
        "Cancelled":           "tag-cancelled",
    };
    return `<span class="crd-tag ${map[s] || "tag-draft"}">${s || "—"}</span>`;
}

function _fill_class(pct) {
    if (pct >= 70) return "green";
    if (pct >= 40) return "orange";
    return "red";
}

// ── Main loader ───────────────────────────────────────────────────────────────
function load_dashboard() {
    $("#crd-refresh").prop("disabled", true).text("Loading…");
    $("#crd-body").html('<div class="crd-loading">Fetching data…</div>');

    frappe.call({
        method: "bsgroup.bs_group.page.cheque_request_das.cheque_request_das.get_dashboard_data",
        args: {
            selected_user:       _cr.selected_user       || null,
            from_date:           _cr.from_date           || null,
            to_date:             _cr.to_date             || null,
            selected_status:     _cr.selected_status     || null,
            selected_department: _cr.selected_department || null,
        },
        callback: function (r) {
            $("#crd-refresh").prop("disabled", false).text("⟳ Refresh");
            if (r.exc || !r.message) {
                $("#crd-body").html('<div class="crd-loading" style="color:var(--danger)">Failed to load. Check console.</div>');
                return;
            }
            render_dashboard(r.message);
        },
    });
}

// ── Renderer ─────────────────────────────────────────────────────────────────
function render_dashboard(d) {
    const kpis    = d.kpis    || {};
    const filters = d.active_filters || {};

    if (!d.is_manager) $("#crd-user-btn").hide();

    const now      = new Date();
    const timeStr  = now.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit" });
    const monthStr = now.toLocaleString("en-US", { month: "long", year: "numeric" });
    const period   = filters.is_custom_date
        ? `${frappe.datetime.str_to_user(filters.from_date)} – ${frappe.datetime.str_to_user(filters.to_date)}`
        : monthStr;

    $("#crd-subtitle").text(`BS Group · Finance · ${d.generated_at || ""}`);

    // ── Approval rate ─────────────────────────────────────────────────────────
    const total_decided = (kpis.issued_count || 0) + (kpis.rejected_count || 0);
    const appr_rate     = total_decided > 0 ? Math.round(kpis.issued_count / total_decided * 100) : null;

    // ── KPI section ───────────────────────────────────────────────────────────
    const kpi_html = `
    <div class="crd-panel">
        <div class="crd-ph">
            <div><h2>Approval Overview</h2><p>Summary of active cheque requests · ${period}</p></div>
        </div>
        <div class="crd-kpis">
            <div class="crd-kpi">
                <div class="crd-kpi-label"><span>Pending Pre-Approval</span><span class="trend-warn">⏳</span></div>
                <div class="crd-kpi-value" style="color:var(--warn)">${kpis.pending_count}</div>
                <div class="crd-kpi-foot">${_fmt(kpis.pending_amount)} total value</div>
            </div>
            <div class="crd-kpi">
                <div class="crd-kpi-label"><span>Pre-Approved</span><span class="trend-info">✓</span></div>
                <div class="crd-kpi-value" style="color:var(--accent)">${kpis.pre_approved_count}</div>
                <div class="crd-kpi-foot">${_fmt(kpis.pre_approved_amount)} ready for preparation</div>
            </div>
            <div class="crd-kpi">
                <div class="crd-kpi-label"><span>In Progress</span><span class="trend-info">🔄</span></div>
                <div class="crd-kpi-value" style="color:var(--info)">${kpis.in_progress_count}</div>
                <div class="crd-kpi-foot">Prepared · Signing · Signed</div>
            </div>
            <div class="crd-kpi">
                <div class="crd-kpi-label"><span>Issued This Period</span><span class="trend-up">✅</span></div>
                <div class="crd-kpi-value" style="color:var(--green)">${kpis.issued_count}</div>
                <div class="crd-kpi-foot">${_fmt(kpis.issued_amount)} disbursed</div>
            </div>
        </div>
    </div>`;

    // ── Approval Queue table ──────────────────────────────────────────────────
    let queue_rows = "";
    (d.queue_list || []).forEach(row => {
        const age_cls = (row.age_days || 0) > 5 ? "trend-down" : "trend-up";
        queue_rows += `<tr>
            <td class="crd-doc-id">${_link(row.name)}</td>
            <td>${row.payee_name || "—"}</td>
            <td>${row.department || "—"}</td>
            <td style="color:var(--muted)">${row.requester_short || "—"}</td>
            <td class="crd-amount">${_fmt(row.amount)}</td>
            <td><span class="${age_cls}">${row.age_days || 0}d</span></td>
            <td>${_badge(row.status)}</td>
        </tr>`;
    });
    if (!queue_rows) queue_rows = `<tr><td colspan="7" style="color:var(--muted);text-align:center;padding:24px">✓ No active requests</td></tr>`;

    const queue_html = `
    <div class="crd-panel">
        <div class="crd-ph">
            <div><h2>Approval Queue</h2><p>Active cheque requests requiring action</p></div>
            <a class="crd-btn crd-btn-outline" href="/app/cheque-request" target="_blank" style="text-decoration:none;font-size:12px">View All</a>
        </div>
        <div class="crd-table-wrap">
            <table class="crd-table">
                <thead><tr><th>ID</th><th>Payee</th><th>Department</th><th>Requester</th><th>Amount</th><th>Age</th><th>Status</th></tr></thead>
                <tbody>${queue_rows}</tbody>
            </table>
        </div>
        <div class="crd-footer-note">Last synced · ${timeStr} · ${d.generated_at || ""}</div>
    </div>`;

    // ── Right: Today's Insights ───────────────────────────────────────────────
    const risk_items = (d.aging_data || []).filter(r => (r.avg_days || 0) > 5);
    const insights_html = `
    <div class="crd-panel">
        <div class="crd-ph"><div><h2>Today's Insights</h2><p>Priority indicators for management attention</p></div></div>
        <div class="crd-side-content">
            <div class="crd-mini">
                <h3>High Value Pending</h3>
                <div class="mv" style="color:var(--warn)">${_fmt(kpis.highval_pending_amount)}</div>
                <p>Across ${kpis.highval_pending_count} active requests</p>
            </div>
            <div class="crd-mini">
                <h3>Overdue Cheque Dates</h3>
                <div class="mv" style="color:${kpis.overdue_count > 0 ? "var(--danger)" : "var(--green)"}">${kpis.overdue_count}</div>
                <p>Cheque date passed, still not issued</p>
            </div>
            <div class="crd-mini">
                <h3>Rejected This Period</h3>
                <div class="mv" style="color:var(--danger)">${kpis.rejected_count}</div>
                <p>Approval rate: <strong>${appr_rate !== null ? appr_rate + "%" : "—"}</strong></p>
            </div>
            ${risk_items.length ? `<div class="crd-mini">
                <h3>⚠️ Risk Alert</h3>
                <div class="mv" style="color:var(--warn)">${risk_items.length} requesters</div>
                <p>Pending longer than 5-day SLA window</p>
            </div>` : ""}
        </div>
    </div>`;

    // ── Right: Dept workflow performance ──────────────────────────────────────
    let prog_html = "";
    (d.dept_perf || []).forEach(row => {
        const pct = row.pct || 0;
        prog_html += `
        <div class="crd-prog-item">
            <div class="crd-prog-top">
                <span>${row.department}</span>
                <span>${pct}% issued (${row.total} total)</span>
            </div>
            <div class="crd-bar"><div class="crd-fill ${_fill_class(pct)}" style="width:${pct}%"></div></div>
        </div>`;
    });
    if (!prog_html) prog_html = `<p style="color:var(--muted);font-size:13px">No department data</p>`;

    const perf_html = `
    <div class="crd-panel">
        <div class="crd-ph"><div><h2>Workflow Performance</h2><p>Department-wise completion rate</p></div></div>
        <div class="crd-prog-wrap">${prog_html}</div>
    </div>`;

    // ── Right: Recently Issued ────────────────────────────────────────────────
    let issued_rows = "";
    (d.issued_list || []).forEach(row => {
        issued_rows += `<tr>
            <td class="crd-doc-id">${_link(row.name)}</td>
            <td>${row.payee_name || "—"}</td>
            <td class="crd-amount" style="color:var(--green)">${_fmt(row.amount)}</td>
            <td style="color:var(--muted);font-size:12px">${row.issued_on_display || "—"}</td>
        </tr>`;
    });
    if (!issued_rows) issued_rows = `<tr><td colspan="4" style="color:var(--muted);text-align:center;padding:20px">No issues this period</td></tr>`;

    const issued_html = `
    <div class="crd-panel">
        <div class="crd-ph">
            <div><h2>Recently Issued</h2><p>Cheques disbursed this period</p></div>
            <a class="crd-btn crd-btn-outline" href="/app/cheque-request?status=Issued" target="_blank" style="text-decoration:none;font-size:12px">View All</a>
        </div>
        <div class="crd-table-wrap">
            <table class="crd-table">
                <thead><tr><th>ID</th><th>Payee</th><th>Amount</th><th>Issued On</th></tr></thead>
                <tbody>${issued_rows}</tbody>
            </table>
        </div>
    </div>`;

    // ── Assemble ──────────────────────────────────────────────────────────────
    $("#crd-body").html(`
        <div class="crd-layout">
            <div class="crd-left">
                ${kpi_html}
                ${queue_html}
            </div>
            <div class="crd-right">
                ${insights_html}
                ${perf_html}
                ${issued_html}
            </div>
        </div>
    `);

}
