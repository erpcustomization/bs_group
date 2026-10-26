// Three user decisions; Delayed and Closed are derived outcomes, never manual choices.
const bsi_lead_lifecycle = (() => {
    const active = new Set(["Lead", "Open", "Replied", "Interested", "Delayed"]);
    const closed = new Set(["Opportunity", "Quotation", "Converted", "Lost Quotation"]);
    function display(doc) {
        if (closed.has(doc.status)) return [doc.status === "Opportunity" ? "Opportunity · Closed" : "Closed", "green"];
        if (["Dropped", "Do Not Contact"].includes(doc.status)) return ["Dropped", "red"];
        const age = doc.creation ? moment().diff(frappe.datetime.convert_to_user_tz(doc.creation, false), 'hours', true) : 0;
        return doc.status === "Delayed" || (active.has(doc.status) && age >= 24) ? ["Delayed", "orange"] : ["Open", "blue"];
    }
    function convert(frm) {
        return frappe.prompt([{fieldname:'subject',fieldtype:'Data',label:__('Opportunity subject'),reqd:1,
            default:frm.doc.company_name || frm.doc.lead_name || ''},
            {fieldname:'opportunity_amount',fieldtype:'Currency',label:__('Opportunity Amount'),reqd:1},
            {fieldname:'custom_business_type',fieldtype:'Select',label:__('Supply / Service'),options:'\nSupply\nService\nSupply and Installation',reqd:1},
            {fieldname:'custom_service_type',fieldtype:'Select',label:__('Service Type'),options:'\nCCTV\n3CX\nELV',depends_on:"eval:doc.custom_business_type === 'Service'",mandatory_depends_on:"eval:doc.custom_business_type === 'Service'"},
            {fieldname:'custom_service_survey',fieldtype:'Select',label:__('Site Survey Requirement'),options:'\nSite Survey by ELV\nSite Survey by Technical Team\nNo Site Survey Required',depends_on:"eval:doc.custom_business_type === 'Service' && doc.custom_service_type",mandatory_depends_on:"eval:doc.custom_business_type === 'Service'"},
            {fieldname:'custom_service_details',fieldtype:'Small Text',label:__('Service Details'),depends_on:"eval:doc.custom_business_type === 'Service' && doc.custom_service_survey",mandatory_depends_on:"eval:doc.custom_business_type === 'Service'"},
            {fieldname:'custom_installation_type',fieldtype:'Select',label:__('Installation Type'),options:'\nCCTV\n3CX\nNetworking\nOther',depends_on:"eval:doc.custom_business_type === 'Supply and Installation'",mandatory_depends_on:"eval:doc.custom_business_type === 'Supply and Installation'"},
            {fieldname:'custom_camera_count',fieldtype:'Int',label:__('Number of Cameras'),depends_on:"eval:doc.custom_business_type === 'Supply and Installation' && doc.custom_installation_type === 'CCTV'",mandatory_depends_on:"eval:doc.custom_business_type === 'Supply and Installation' && doc.custom_installation_type === 'CCTV'"},
            {fieldname:'custom_site_survey_needed',fieldtype:'Select',label:__('Site Survey Required?'),options:'\nYes\nNo',depends_on:"eval:doc.custom_business_type === 'Supply and Installation' && doc.custom_installation_type === 'CCTV' && doc.custom_camera_count >= 30",mandatory_depends_on:"eval:doc.custom_business_type === 'Supply and Installation' && doc.custom_installation_type === 'CCTV' && doc.custom_camera_count >= 30"}], async values => {
            if (frm._bsi_converting) return;
            frm._bsi_converting = true;
            try {
                if (frm.is_new() || frm.is_dirty()) await frm.save();
                if (frm.is_new() || frm.is_dirty()) return;
                const result = await frappe.call({method:'bsgroup.lead_lifecycle.confirm_opportunity',
                    args:{source_name:frm.doc.name,subject:values.subject,opportunity_amount:values.opportunity_amount,intake:values},freeze:true});
                if (!result.exc && result.message) {
                    await frm.reload_doc();
                    frappe.show_alert({message:__('Opportunity created: {0}', [result.message]),indicator:'green'});
                }
            } finally { frm._bsi_converting = false; }
        }, __('Convert to Opportunity'), __('OK'));
    }
    function followup(frm) {
        const field = frm.fields_dict.custom_next_follow_up_date;
        if (!field?.$wrapper?.[0]) return;
        let button = field.$wrapper[0].parentElement.querySelector('.bsi-followup-ok');
        if (!button) {
            button = document.createElement('button');button.type='button';button.className='btn btn-primary btn-sm bsi-followup-ok';button.textContent=__('OK');
            field.$wrapper[0].after(button);
            button.addEventListener('click', async () => {
                button.disabled=true;
                try { await frm.save(); if (!frm.is_dirty()) { frm._bsi_saved_followup=frm.doc.custom_next_follow_up_date || ''; button.hidden=true; } }
                finally {button.disabled=false;}
            });
        }
        button.hidden=(frm.doc.custom_next_follow_up_date || '') === (frm._bsi_saved_followup || '') || !frm.perm?.some(p=>p.write);
    }
    let timer;
    function refresh(frm) {
        // Activation follows the server schema update; old benches remain usable during deployment.
        const statusField = frm.fields_dict.status;
        if (!statusField || !(statusField.df.options || "").includes("Dropped")) return;
        frm.set_df_property("status", "hidden", 1);
        let box = frm.wrapper.querySelector?.('.bsi-lead-outcome') || frm.wrapper[0]?.querySelector('.bsi-lead-outcome');
        if (!box) {
            box = document.createElement('div'); box.className = 'bsi-lead-outcome';
            const root = frm.wrapper[0] || frm.wrapper;
            const host = root.querySelector('#lead-__details') || root.querySelector('.tab-pane');
            if (host) host.prepend(box); else statusField.$wrapper[0].after(box);
        }
        box.replaceChildren();
        box.style.cssText = 'display:flex;justify-content:flex-end;align-items:center;gap:10px;padding:4px 0;';
        const style = document.createElement('style');
        style.textContent = '.bsi-compact-lead .indicator-pill.blue{background:#ddd6fe!important;color:#5b21b6!important}.bsi-lead-outcome select{background-color:var(--primary,#1d5dcc);color:#fff;border:1px solid var(--primary,#1d5dcc);border-radius:8px;width:144px;min-height:34px;padding:6px 12px;font-weight:600;cursor:pointer}.bsi-lead-outcome select:disabled{opacity:.7;cursor:default}.bsi-lead-outcome option{background:#fff;color:var(--text-color,#15345c)}';
        box.append(style);
        const label=document.createElement('label');label.textContent=__('Status');label.style.cssText='font-weight:600;margin:0';box.append(label);
        const select=document.createElement('select');select.className='form-control bsi-current-status';select.setAttribute('aria-label','Status');
        for (const [value,text] of [['open','Open'],['convert','Opportunity'],['drop','Dropped']]) {
            const option=document.createElement('option');option.value=value;option.textContent=__(text);select.append(option);
        }
        const current=closed.has(frm.doc.status)?'convert':['Dropped','Do Not Contact'].includes(frm.doc.status)?'drop':'open';
        select.value=current;
        select.disabled=!frm.perm?.some(p=>p.write)||closed.has(frm.doc.status);
        if (closed.has(frm.doc.status)) select.title=__('This Lead is closed through its existing sales document.');
        box.append(select);
        const render=()=>{
            const [text,color]=display(frm.doc);
            const palette={blue:'#ddd6fe',green:'#087f5b',red:'#c92a2a',orange:'#a35b00'};
            select.style.setProperty('background-color',palette[color],'important');select.style.setProperty('border-color',color==='blue'?'#a78bfa':palette[color],'important');select.style.setProperty('color',color==='blue'?'#5b21b6':'#fff','important');
            frm.page.set_indicator(__(text),color);
        };
        render();clearInterval(timer);timer=setInterval(()=>{if(document.body.dataset.route==='Form/Lead/'+frm.doc.name)render();},60000);
        select.addEventListener('change', async () => {
            const action = select.value; select.value = current;
            if (action === 'convert') return convert(frm);
            if (action === 'open') {
                await frm.set_value('status', 'Open');
                await frm.save();
            } else if (action === 'drop') {
                frappe.prompt([{fieldname:'reason',fieldtype:'Small Text',label:__('Reason for dropping'),reqd:1}], async values => {
                    const reason = (values.reason || '').trim();
                    if (!reason) return frappe.msgprint(__('Enter a reason before dropping this Lead.'));
                    frm.add_child('notes', {note: frappe.utils.escape_html('Dropped: ' + reason), added_by: frappe.session.user, added_on: frappe.datetime.now_datetime()});
                    await frm.set_value('status', 'Dropped');
                    await frm.save();
                }, __('Drop Lead'), __('OK'));
            }
        });
    }
    return {refresh, convert, display, followup};
})();

frappe.ui.form.on("Lead", {custom_next_follow_up_date(frm) { bsi_lead_lifecycle.followup(frm); }, refresh(frm) {
    frm._bsi_saved_followup=frm.doc.custom_next_follow_up_date || '';
    bsi_lead_lifecycle.followup(frm);
    bsi_lead_lifecycle.refresh(frm);
    frm.page.remove_inner_button("Opportunity", "Create");
    if (!frm.is_new() && frm.perm?.some(p => p.write) && !["Opportunity", "Quotation", "Converted", "Lost Quotation", "Dropped", "Do Not Contact"].includes(frm.doc.status)) {
        frm.page.add_inner_button("Opportunity", () => bsi_lead_lifecycle.convert(frm), "Create");
    }
}});
