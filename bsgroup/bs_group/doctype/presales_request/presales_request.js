// Copyright (c) 2026, Tridots Tech and contributors
// For license information, please see license.txt

function presales_move_timeline_to_additional(frm) {
    const layout = frm.layout;
    const section = layout?.sections_dict.section_break_btny;
    if (!section) return;
    if (!layout.tabs.length) {
        layout.setup_tabbed_layout();
        const sections = [...layout.sections];
        const details = layout.make_tab({fieldname:'presales_details_tab', fieldtype:'Tab Break', label:__('Details')});
        sections.forEach(item => item.wrapper.appendTo(details.wrapper));
        layout.fields_list.forEach(field => details.add_field(field));
        details.set_active();
    }
    let additional = layout.tabs.find(tab =>
        tab.df.fieldname === 'presales_additional_details' ||
        (tab.df.label || '').toLowerCase() === 'additional details');
    if (!additional) {
        additional = layout.make_tab({fieldname:'presales_additional_details', fieldtype:'Tab Break', label:__('Additional details')});
    }
    if (section.wrapper.parent()[0] !== additional.wrapper[0]) {
        section.wrapper.appendTo(additional.wrapper);
        section.fields_list.forEach(field => additional.add_field(field));
    }
    const owner = frm.fields_dict.presales_owner;
    if (owner && owner.$wrapper.parent()[0] !== additional.wrapper[0]) {
        owner.$wrapper.insertBefore(section.wrapper);
        additional.add_field(owner);
    }
    const results = frm.fields_dict.custom_survey_results;
    if (results && results.$wrapper.parent()[0] !== additional.wrapper[0]) {
        results.$wrapper.appendTo(additional.wrapper);
        additional.add_field(results);
    }
    const footer = $(frm.page.wrapper).find('.form-footer');
    if (footer.length && footer.parent()[0] !== additional.wrapper[0]) footer.appendTo(additional.wrapper);
    layout.refresh_tabs();
    const timing = layout.sections_dict.custom_completion_time_section;
    const completion = frm.fields_dict.custom_completion_time;
    const priority = frm.fields_dict.priority;
    if (completion && priority) {
        const tab = layout.tabs.find(item => item.df.fieldname === 'presales_details_tab') || layout.tabs[0];
        completion.$wrapper.insertAfter(priority.$wrapper);
        tab.add_field(completion);
        frm.set_df_property('priority', 'hidden', 1);
        // Keep dependency refreshes from removing the required marker on drafts.
        frm.set_df_property('custom_completion_time', 'mandatory_depends_on', 'eval:doc.docstatus !== 2');
        frm.toggle_reqd('custom_completion_time', frm.doc.docstatus !== 2);
        layout.refresh_tabs();
        if (timing) timing.wrapper.hide();
    }
}

function presales_status_panel(frm) {
    frm.set_df_property('status', 'hidden', 1);
    const host = frm.layout.tabs[0]?.wrapper || frm.layout.wrapper;
    let bar = host.children('.presales-status-bar');
    if (!bar.length) {
        bar = $('<div class="presales-status-bar" style="display:flex;justify-content:flex-end;align-items:center;gap:12px;padding:12px 16px"><span></span><span class="presales-status-value" style="padding:9px 14px;border-radius:8px;background:#e3edff;color:#174e9b;font-weight:600" role="status"></span></div>').prependTo(host);
        bar.children().first().text(__('Status'));
    }
    const show = label => {
        bar.find('.presales-status-value').text(__(label));
        frm.page.set_indicator(__(label), ['Completed','Submitted to Sales','Won'].includes(label) ? 'green' : 'blue');
    };
    show(frm.doc.status === 'Awaiting Site Survey Results' ? 'Awaiting Site Survey' :
        frm.doc.status === 'Site Survey Results Received' ? 'Open with Presales' : frm.doc.status || 'Open with Presales');
    if (!frm.is_new()) {
        const name = frm.doc.name;
        frappe.call({method:'bsgroup.site_survey.presales_handoff', args:{name}}).then(r => {
            if (frm.doc.name !== name || !r.message) return;
            show(r.message.label);
            if (r.message.results != null && frm.fields_dict.custom_survey_results) {
                frm.doc.custom_survey_results = r.message.results;
                frm.refresh_field('custom_survey_results');
            }
        });
    }
}

function presales_compact_layout(frm) {
    // Keep inherited context visible without editable links or navigation.
    for (const field of ['opportunity', 'company']) {
        frm.set_df_property(field, 'read_only', 1);
        frm.set_df_property(field, 'fieldtype', 'Data');
    }
    for (const field of ['timeline_defined', 'site_visit_required', 'site_visit', 'decision_maker_known', 'competition_known', 'budget_confirmed', 'opportunity_qualification_mandatory_section']) {
        frm.set_df_property(field, 'hidden', 1);
    }
    for (const field of ['decision_maker_known', 'competition_known', 'budget_confirmed']) frm.toggle_reqd(field, false);
    const root = $(frm.page.wrapper);
    root.addClass('bsi-presales-compact');
    if (!root.children('style.bsi-presales-compact-style').length) {
        $('<style class="bsi-presales-compact-style"></style>').text(`
            .bsi-presales-compact .form-layout .form-section { padding:12px 16px; margin-bottom:8px; }
            .bsi-presales-compact .form-layout .section-head { margin-bottom:10px; }
            .bsi-presales-compact .form-layout .section-body { margin-top:0; }
            .bsi-presales-compact .form-layout .frappe-control { margin-bottom:10px; }
            .bsi-presales-compact .form-layout .control-label { margin-bottom:4px; }
            .bsi-presales-compact .form-layout .form-column:has(> form):not(:has(> form > .frappe-control:not(.hide-control))) { display:none; }
            .bsi-presales-compact [data-fieldname="opportunity_qualification_mandatory_section"] .form-column { flex:1; max-width:100%; }
            .bsi-presales-compact [data-fieldname="opportunity_qualification_mandatory_section"] .form-column > form { display:flex; flex-wrap:wrap; gap:8px 24px; }
            .bsi-presales-compact [data-fieldname="opportunity_qualification_mandatory_section"] .frappe-control { margin-bottom:0; }
            .bsi-presales-compact .presales-status-bar { padding:8px 16px!important; }
            .bsi-presales-compact .form-footer { margin-top:12px; padding-top:8px; }
        `).appendTo(root);
    }
}

function presales_show_party(frm) {
    for (const name of ['party_type', 'customer', 'is_new_customer']) {
        frm.set_df_property(name, 'hidden', 1);
    }
    frm.set_df_property('party', 'label', frm.doc.party_type === 'Lead' ? __('Lead') : __('Customer'));
    frm.set_df_property('party', 'read_only', 1);
    frm.set_df_property('party', 'description', '');
    frm.set_df_property('organisation_name', 'description', '');
    frm.set_df_property('organisation_name', 'hidden',
        frm.doc.party_type !== 'Lead' || !frm.doc.organisation_name || frm.doc.organisation_name === frm.doc.party);
}

frappe.ui.form.on("Presales Request", {
    onload(frm) {
        if (!frm.doc.requested_by) {
            frm.set_value("requested_by", frappe.session.user);
        }
    },
    opportunity(frm) {
        // A-6: the party comes from the Opportunity as recorded there. `customer`
        // is derived on the server from the party and is never set here.
        if (!frm.doc.opportunity) return;
        frappe.db.get_value("Opportunity", frm.doc.opportunity,
            ["opportunity_from", "party_name", "custom_organization_name"]
        ).then(async r => {
            if (!r.message) return;
            let opp = r.message;
            if ((opp.opportunity_from === "Customer" || opp.opportunity_from === "Lead") && opp.party_name) {
                await frm.set_value("party_type", opp.opportunity_from);
                await frm.set_value("party", opp.party_name);
                await frm.set_value("is_new_customer", opp.opportunity_from === "Lead" ? 1 : 0);
                presales_show_party(frm);
            }
        });
    },
    party_type(frm) {
        if (frm.doc.party && frm.doc.party_type) {
            // party is a Dynamic Link: a change of type invalidates the value.
            return frm.set_value("party", "");
        }
    },
    party(frm) {
        if (!frm.doc.party || !frm.doc.party_type) return;
        let field = frm.doc.party_type === "Customer" ? "customer_name" : "company_name";
        return frappe.db.get_value(frm.doc.party_type, frm.doc.party, field).then(async r => {
            if (r.message) await frm.set_value("organisation_name", r.message[field] || frm.doc.party);
            presales_show_party(frm);
        });
    },
    refresh(frm){
        presales_compact_layout(frm);
        presales_show_party(frm);
        presales_move_timeline_to_additional(frm);
        presales_sales_brief(frm);
        set_completion_date(frm);
        presales_status_panel(frm);
        reduce_subject_height(frm);
        frm.toggle_reqd("site_visit", frm.doc.site_visit_required == 1);
        // Submission creates the DCS on the server; no manual duplicate action.
        frm.remove_custom_button(__('Deal Cost Sheet'), __('Create'));
    },
    status(frm){
        set_completion_date(frm)
    },
    site_visit_required(frm){
        frm.toggle_reqd("site_visit", frm.doc.site_visit_required == 1);
    }
});

async function presales_sales_brief(frm) {
    const salesFields = ['opportunity', 'party_type', 'party', 'organisation_name', 'customer',
        'is_new_customer', 'subject', 'company', 'estimated_value', 'requested_by',
        'request_date', 'expected_close_date', 'custom_service_details',
        'decision_maker_known', 'competition_known', 'budget_confirmed', 'timeline_defined'];
    if ((frappe.user.has_role('Presales') || frappe.user.has_role('BS Scoped Presales')) &&
        !frappe.user.has_role('System Manager')) {
        salesFields.forEach(field => {
            if (frm.fields_dict[field]) frm.set_df_property(field, 'read_only', 1);
        });
    }
    if (frm.is_new()) return;
    const host = frm.layout.tabs[0]?.wrapper || frm.layout.wrapper;
    let panel = host.children('.bs-sales-request-brief');
    if (!panel.length) {
        panel = $('<section class="bs-sales-request-brief" style="margin:12px 16px;padding:18px;border:1px solid #dce5ef;border-radius:10px;background:#f7faff"></section>');
        const status = host.children('.presales-status-bar');
        if (status.length) panel.insertAfter(status); else panel.prependTo(host);
    }
    panel.empty().append($('<h4>').text(__('Sales requirement')),
        $('<p>').css('color', '#62748a').text(__('Provided by Sales · read-only')),
        $('<p>').text(__('Loading sales details…')));
    const requestName = frm.doc.name;
    try {
        const r = await frappe.call({method: 'bsgroup.presales_sales_brief.get_brief', args: {name: requestName}});
        if (frm.doc.name !== requestName) return;
        const data = r.message || {};
        panel.empty().append($('<h4>').text(__('Sales requirement')),
            $('<p>').css('color', '#62748a').text(__('Provided by Sales · read-only')),
            $('<div>').css({'white-space': 'pre-wrap', 'font-size': '15px', 'margin-bottom': '16px'})
                .text(data.requirement || __('No enquiry recorded on the source Opportunity. Ask Sales to complete it.')));
        const grid = $('<div>').css({display:'grid', 'grid-template-columns':'repeat(auto-fit,minmax(220px,1fr))',gap:'12px'}).appendTo(panel);
        (data.details || []).forEach(row => $('<div>').append(
            $('<div>').css({color:'#62748a','font-size':'12px'}).text(__(row.label)),
            $('<div>').css('white-space','pre-wrap').text(row.value)).appendTo(grid));
        if ((data.items || []).length) {
            panel.append($('<h5>').css('margin-top','16px').text(__('Items requested by Sales')));
            const table = $('<table class="table table-bordered">').appendTo($('<div style="overflow:auto">').appendTo(panel));
            table.append($('<thead>').append($('<tr>').append(...['Item','Description','Quantity','UOM','Rate','Amount'].map(label => $('<th>').text(__(label))))));
            const body = $('<tbody>').appendTo(table);
            data.items.forEach(row => body.append($('<tr>').append(...[
                row.item_name || row.item_code || '', row.description || '', row.qty ?? '', row.uom || '', row.rate ?? '', row.amount ?? ''
            ].map(value => $('<td>').text(value)))));
        }
        if ((data.files || []).length) {
            panel.append($('<h5>').css('margin-top','16px').text(__('Sales attachments')));
            data.files.forEach(file => {
                const query = new URLSearchParams({doctype:'Presales Request',name:requestName,file:file.name});
                panel.append($('<div>').append($('<a>').attr('href','/api/method/bsgroup.opportunity_attachments.download?'+query).text(file.file_name)));
            });
        }
    } catch (error) {
        if (frm.doc.name === requestName) panel.append($('<p role="alert">').text(__('Sales details could not be loaded. Refresh to retry.')));
    }
}

function set_completion_date(frm) {
    if (frm.doc.status === "Completed") {
        frm.set_df_property("completion_date", "read_only", 0);
        frm.set_df_property("completion_date", "reqd", 1);
    } else {
        frm.set_df_property("completion_date", "read_only", 1);
        frm.set_df_property("completion_date", "reqd", 0);
    }
}

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

function set_status_indicator(frm){
    let color = {
        "Draft": "gray",
        "Open": "blue",
        "Assigned": "cyan",
        "In Progress": "orange",
        "Awaiting Sales Input": "yellow",
        "Awaiting Customer Input": "purple",
        "Awaiting Site Survey Results": "orange",
        "Site Survey Results Received": "green",
        "Costing in Progress": "pink",
        "Ready for Quotation": "green",
        "Submitted to Sales": "blue",
        "Completed": "darkgreen",
        "On Hold": "darkgrey",
        "Won": "lime",
        "Lost": "red",
        "Cancelled": "darkred"
    }[frm.doc.status] || "black";
    frm.page.set_indicator(frm.doc.status, color);
}
