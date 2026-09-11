frappe.ui.form.on("Lead", {
    refresh: function(frm) {
        setTimeout(() => {
            $('a[data-label="Customer"]').hide();
            $('a[data-label="Quotation"]').hide();
            $('a[data-label="Prospect"]').hide();
        }, 500);

        frm.page.remove_inner_button("Opportunity", "Create");

        frm.page.add_inner_button("Opportunity", function () {
            frappe.call({
                method: "erpnext.crm.doctype.lead.lead.make_opportunity",
                args: { source_name: frm.docname },
                freeze: true,
                callback: function(r) {
                    if (!r.exc && r.message) {
                        r.message.sales_stage = "Proposal";
                        r.message.custom_organization_name = frm.doc.company_name;
                        frappe.model.sync(r.message);
                        frappe.set_route("Form", r.message.doctype, r.message.name);
                    }
                }
            });
        }, "Create");
    }
});

// LEAD - ENTERPRISE GRADE UI ENHANCEMENT (Client Script Only)
// Theme adapts to ERPNext Company: AE -> corporate emerald, OM -> corporate crimson
frappe.ui.form.on('Lead', {
    onload: function(frm) { if (frm.doc.company) inject_enterprise_styles(frm); else inject_neutral_styles(); },
    refresh: function(frm) {
        if (frm.doc.company) { inject_enterprise_styles(frm); } else { inject_neutral_styles(); }
        hide_unused_fields(frm);
        setTimeout(function(){ relocate_company_field(frm); }, 100);
        decorate_status_indicator(frm);
        setTimeout(function(){ decorate_sections(frm); }, 300);
        setTimeout(function(){ add_dashboard_summary(frm); }, 350);
    },
    status: function(frm) { decorate_status_indicator(frm); },
    company: function(frm) {
        var el = document.getElementById('ent-lead-styles'); if (el) el.remove();
        // Reset section header styles so they re-decorate with new theme
        $(frm.wrapper).find('.section-head').each(function(){
            var $s = $(this); $s.removeData('ent-styled'); $s.find('.ent-section-icon').remove();
            $s.css({'border-left':'','padding-left':'','color':'','font-weight':'','letter-spacing':''});
        });
        if (frm.doc.company) inject_enterprise_styles(frm); else inject_neutral_styles();
        setTimeout(function(){ decorate_sections(frm); }, 50);
        setTimeout(function(){ add_dashboard_summary(frm); }, 80);
    }
});

function get_theme(frm) {
    var c = (frm && frm.doc && frm.doc.company) ? String(frm.doc.company) : '';
    if (/-\s*AE\s*$/i.test(c) || /UAE/i.test(c)) {
        return {
            key: 'UAE',
            primary: '#0E5E3A',     // deep emerald
            secondary: '#1F8A5A',   // muted green
            accent: '#0E5E3A',
            gradient: 'linear-gradient(135deg,#0E5E3A 0%,#1F8A5A 100%)',
            btnGradient: 'linear-gradient(135deg,#0E5E3A 0%,#1F8A5A 100%)',
            section_colors: { 'Contact Info':'#0E5E3A','Organization':'#1F8A5A','Address':'#0E5E3A','Notes':'#1F8A5A','Lead Details':'#0E5E3A' }
        };
    }
    if (/-\s*OM\s*$/i.test(c) || /Oman/i.test(c)) {
        return {
            key: 'OM',
            primary: '#7A1F2B',     // corporate crimson
            secondary: '#B23A48',   // softer red
            accent: '#7A1F2B',
            gradient: 'linear-gradient(135deg,#7A1F2B 0%,#B23A48 100%)',
            btnGradient: 'linear-gradient(135deg,#7A1F2B 0%,#B23A48 100%)',
            section_colors: { 'Contact Info':'#7A1F2B','Organization':'#B23A48','Address':'#7A1F2B','Notes':'#B23A48','Lead Details':'#7A1F2B' }
        };
    }
    return {
        key: 'DEFAULT',
        primary: '#1e3a8a', secondary: '#3b82f6', accent: '#3b82f6',
        gradient: 'linear-gradient(135deg,#1e3a8a 0%,#3b82f6 100%)',
        btnGradient: 'linear-gradient(135deg,#1e40af,#3b82f6)',
        section_colors: { 'Contact Info':'#0ea5e9','Organization':'#8b5cf6','Address':'#f59e0b','Notes':'#10b981','Lead Details':'#3b82f6' }
    };
}

function hide_unused_fields(frm) {
    var candidate_fields = ['salutation','middle_name','gender','job_title','phone_ext','fax','website','whatsapp','market_segment','industry','territory','annual_revenue','no_of_employees','request_type','lead_type','blog_subscriber','unsubscribed','naming_series','company_name','qualification_status','qualified_by','qualified_on','image','campaign_name','source','city','state','country','pincode','county','address_line1','address_line2','address_title','address_type'];
    candidate_fields.forEach(function(fn){
        var df = frappe.meta.get_docfield(frm.doctype, fn, frm.docname);
        if (!df) return;
        var val = frm.doc[fn];
        var is_empty = (val === undefined || val === null || val === '' || val === 0);
        if (!df.reqd && is_empty) { frm.set_df_property(fn, 'hidden', 1); }
        else { frm.set_df_property(fn, 'hidden', 0); }
    });
    if (frappe.meta.get_docfield(frm.doctype, 'company', frm.docname)) {
        frm.set_df_property('company', 'hidden', 0);
    }
    setTimeout(function(){ hide_empty_sections(frm); }, 250);
}

function hide_empty_sections(frm) {
    if (!frm.fields) return;
    frm.fields.forEach(function(field){
        if (field.df && field.df.fieldtype === 'Section Break') {
            var $section = $(field.wrapper);
            var $pane = $section.closest('.tab-pane');
            if ($pane.length && /activities_tab|notes_tab|dashboard_tab/.test($pane.attr('id') || '')) { return; }
            var $visible = $section.find('.frappe-control').filter(function(){ return $(this).is(':visible'); });
            if ($visible.length === 0) { $section.hide(); } else { $section.show(); }
        }
    });
}

function decorate_status_indicator(frm) {
    var status = frm.doc.status;
    if (!status) return;
    var color_map = {'Lead':'gray','Open':'blue','Replied':'cyan','Opportunity':'orange','Quotation':'purple','Lost Quotation':'red','Interested':'yellow','Converted':'green','Do Not Contact':'red'};
    var color = color_map[status] || 'gray';
    if (frm.page && frm.page.set_indicator) { frm.page.set_indicator(status, color); }
}

function decorate_sections(frm) {
    var theme = get_theme(frm);
    var $form = $(frm.wrapper);
    var icon_map = { 'Contact Info':'☎','Organization':'⌂','Address':'⚑','Notes':'✍','Lead Details':'★' };
    $form.find('.section-head').each(function(){
        var $sec = $(this);
        var text = ($sec.text() || '').trim();
        var color = theme.section_colors[text];
        var icon = icon_map[text];
        if (color && !$sec.data('ent-styled')) {
            if (icon) { $sec.prepend('<span class="ent-section-icon" style="margin-right:8px;">' + icon + '</span>'); }
            $sec.css({'border-left':'4px solid '+color,'padding-left':'10px','color':color,'font-weight':'600','letter-spacing':'0.3px'});
            $sec.data('ent-styled', true);
        }
    });
}

function add_dashboard_summary(frm) {
    if (frm.is_new && frm.is_new()) return;
    var $w0 = $(frm.wrapper); $w0.find('.ent-summary-card').remove();
    if (!frm.doc.company) { return; }
    var theme = get_theme(frm);
    var $wrap = $(frm.wrapper);
    var org   = frm.doc.company_name || frm.doc.organization_name || '-';
    var company = frm.doc.company || '-';
    var stat  = frm.doc.status || '-';
    var esc = function(s){ return frappe.utils.escape_html(String(s)); };
    var textColor = '#ffffff';
    var labelColor = 'rgba(255,255,255,.78)';
    var tile = function(label, value){
        return '<div style="flex:1;min-width:150px;">' +
               '<div style="color:'+labelColor+';font-size:11px;text-transform:uppercase;letter-spacing:1px;font-weight:600;">' + label + '</div>' +
               '<div style="font-weight:700;font-size:14px;color:'+textColor+';">' + esc(value) + '</div>' +
               '</div>';
    };
    var badge = '<span style="background:rgba(255,255,255,.18);color:#fff;font-size:10px;padding:2px 8px;border-radius:999px;letter-spacing:1px;margin-left:8px;border:1px solid rgba(255,255,255,.3);">' + theme.key + '</span>';
    var html = '<div class="ent-summary-card" style="position:relative;display:flex;flex-wrap:wrap;gap:14px;align-items:center;background:'+theme.gradient+';border-radius:10px;padding:14px 18px;margin:8px 0 18px 0;box-shadow:0 4px 14px rgba(0,0,0,0.18);">' +
               tile('Company', company) +
               tile('Organization', org) +
               tile('Status', stat) +
               '<div style="position:absolute;top:8px;right:12px;">'+badge+'</div>' +
               '</div>';
    var $layout = $wrap.find('.form-layout').first();
    if ($layout.length) { $layout.prepend(html); }
}

function inject_neutral_styles() {
    if (document.getElementById('ent-lead-styles')) return;
    var css = '<style id="ent-lead-styles" data-theme="NEUTRAL">'
        + '[data-doctype="Lead"] .form-layout { background:#f8fafc; border-radius:10px; }'
        + '[data-doctype="Lead"] .form-section { background:#ffffff; border:1px solid #e5e7eb; border-radius:8px; padding:14px 18px; margin-bottom:14px; box-shadow:0 1px 2px rgba(15,23,42,0.04); }'
        + '[data-doctype="Lead"] .control-label { color:#475569 !important; font-weight:600 !important; font-size:11.5px !important; text-transform:uppercase; letter-spacing:.4px; }'
        + '[data-doctype="Lead"] .form-control, [data-doctype="Lead"] .like-disabled-input { border-radius:6px !important; border:1px solid #cbd5e1 !important; background:#fbfdff !important; }'
        + '[data-doctype="Lead"] .form-control:focus { border-color:#94a3b8 !important; box-shadow:0 0 0 3px rgba(148,163,184,.18) !important; background:#fff !important; }'
        + '[data-doctype="Lead"] .title-text { color:#0f172a !important; font-weight:700 !important; }'
        + '</style>';
    $('head').append(css);
}

function inject_enterprise_styles(frm) {
    var existing = document.getElementById('ent-lead-styles');
    var desiredKey = get_theme(frm).key;
    if (existing && existing.getAttribute('data-theme') === desiredKey) return;
    if (existing) existing.remove();
    var theme = get_theme(frm);
    var css = '<style id="ent-lead-styles" data-theme="'+theme.key+'">'
        + '[data-doctype="Lead"] .form-layout { background:#f8fafc; border-radius:10px; }'
        + '[data-doctype="Lead"] .form-section { background:#ffffff; border:1px solid #e5e7eb; border-radius:8px; padding:14px 18px; margin-bottom:14px; box-shadow:0 1px 2px rgba(15,23,42,0.04); transition:box-shadow .2s ease; }'
        + '[data-doctype="Lead"] .form-section:hover { box-shadow:0 4px 12px rgba(15,23,42,0.08); }'
        + '[data-doctype="Lead"] .control-label { color:#475569 !important; font-weight:600 !important; font-size:11.5px !important; text-transform:uppercase; letter-spacing:.4px; }'
        + '[data-doctype="Lead"] .form-control, [data-doctype="Lead"] .like-disabled-input { border-radius:6px !important; border:1px solid #cbd5e1 !important; background:#fbfdff !important; transition:border-color .15s,box-shadow .15s; }'
        + '[data-doctype="Lead"] .form-control:focus { border-color:'+theme.primary+' !important; box-shadow:0 0 0 3px '+hexToRgba(theme.primary,0.15)+' !important; background:#fff !important; }'
        + '[data-doctype="Lead"] .form-tabs-list .nav-link.active { color:'+theme.primary+' !important; border-bottom:2px solid '+theme.primary+' !important; font-weight:600; }'
        + '[data-doctype="Lead"] .title-text { color:#0f172a !important; font-weight:700 !important; }'
        + '[data-doctype="Lead"] .standard-actions .btn-primary { background:'+theme.btnGradient+' !important; border:none !important; box-shadow:0 2px 6px '+hexToRgba(theme.primary,0.35)+'; }'
        + '</style>';
    $('head').append(css);
}

function hexToRgba(hex, a) {
    var h = hex.replace('#','');
    if (h.length === 3) { h = h[0]+h[0]+h[1]+h[1]+h[2]+h[2]; }
    var r = parseInt(h.substring(0,2),16), g = parseInt(h.substring(2,4),16), b = parseInt(h.substring(4,6),16);
    return 'rgba('+r+','+g+','+b+','+a+')';
}

function relocate_company_field(frm) {
    try {
        var f = frm.fields_dict.company;
        if (!f || !f.wrapper) return;
        var $w = $(f.wrapper);
        var $ctrl = $w.closest('.frappe-control');
        if (!$ctrl.length) $ctrl = $w;
        var $layout = $(frm.wrapper).find('.form-layout').first();
        var $first = $layout.find('.form-section').first();
        if (!$first.length) return;
        var $col = $first.find('.form-column').first();
        if (!$col.length) $col = $first;
        if ($ctrl.closest('.form-section')[0] === $first[0]) {
            $ctrl.show(); $w.show(); f.df.hidden = 0;
            if (f.refresh) f.refresh();
            return;
        }
        $ctrl.detach().appendTo($col);
        $ctrl.show(); $w.show();
        f.df.hidden = 0;
        if (f.df.label !== 'Company') { f.df.label = 'Company'; }
        frm.set_df_property('company', 'hidden', 0);
        if (f.refresh) f.refresh();
    } catch(e) { console.warn('relocate_company_field failed', e); }
}