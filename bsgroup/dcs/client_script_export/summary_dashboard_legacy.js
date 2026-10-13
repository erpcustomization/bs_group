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