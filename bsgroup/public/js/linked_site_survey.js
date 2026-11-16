(() => {
    if (frappe.bsi_linked_survey_installed) return;
    frappe.bsi_linked_survey_installed = true;
    const plain = html => {
        const body = new DOMParser().parseFromString(html || '', 'text/html').body;
        body.querySelectorAll('br').forEach(e => e.replaceWith('\n'));
        body.querySelectorAll('p,div,li').forEach(e => e.append('\n'));
        return body.textContent || '';
    };
    async function render(frm) {
        if (frm.is_new()) return;
        const name = frm.doc.name;
        const tab = frm.layout?.tabs.find(t => t.df.fieldname ===
            (frm.doctype === 'Opportunity' ? 'contact_info' : 'dcs_approval_tab') ||
            String(t.df.label || '').toLowerCase() === 'additional details');
        if (!tab) return;
        const response = await frappe.call({method:'bsgroup.site_survey.linked_survey_details',
            args:{doctype:frm.doctype,name}});
        if (frm.doc.name !== name) return;
        tab.wrapper.children('.bsi-survey-results').remove();
        const rows = response.message || [];
        if (!rows.length) return;
        const section = $('<section class="bsi-survey-results" style="padding:16px;border:1px solid #d6e3f5;border-radius:12px;background:#f5f9ff;margin:12px"></section>').prependTo(tab.wrapper);
        const heading = $('<div style="display:flex;justify-content:space-between;align-items:center"></div>').appendTo(section);
        $('<h5 style="font-weight:700;color:#173a68"></h5>').text(__('Site Survey')).appendTo(heading);
        $('<button type="button" class="btn btn-default btn-sm"></button>').text(__('Refresh survey details')).on('click',()=>render(frm)).appendTo(heading);
        rows.forEach(survey => {
            $('<div style="font-weight:700;margin:10px 0"></div>').text(`${survey.name} · ${survey.status}`).appendTo(section);
            for (const [label,value] of [
                ['Requested on',survey.request_date],['Assigned to',survey.assigned_to],
                ['Planned date',survey.planned_date],['Completed on',survey.completed_on],
                ['Request details',survey.survey_request_details],['Site address',survey.site_address],
                ['Survey results',plain(survey.results)]]) {
                if (!value) continue;
                const row = $('<div style="white-space:pre-wrap;margin:8px 0"></div>').appendTo(section);
                $('<strong></strong>').text(__(label)+': ').appendTo(row);
                $('<span></span>').text(value).appendTo(row);
            }
            if (/^\/(private\/)?files\//.test(survey.attachment || '')) {
                $('<a target="_blank" rel="noopener"></a>').attr('href',survey.attachment)
                    .text(__('Open survey attachment')).appendTo(section);
            }
            if (!survey.results) $('<p class="text-muted"></p>').text(__('Survey results will appear here when the survey team records them.')).appendTo(section);
        });
        tab.refresh();
    }
    function request(frm) {
        if (frm.is_dirty()) { frappe.msgprint(__('Save your Opportunity changes first.')); return; }
        const dialog = new frappe.ui.Dialog({title:__('Request Site Survey'),fields:[
            {fieldname:'team',label:__('Survey Team'),fieldtype:'Select',options:'\nELV\nTechnical Team\nELV and Technical Team',reqd:1},
            {fieldname:'instructions',label:__('What should the survey team do?'),fieldtype:'Small Text',reqd:1},
            {fieldname:'location',label:__('Site Location'),fieldtype:'Small Text',reqd:1},
            {fieldname:'contact_name',label:__('Contact Person'),fieldtype:'Data',reqd:1,default:frm.doc.custom_contact_person_name},
            {fieldname:'contact_phone',label:__('Contact Phone'),fieldtype:'Data',reqd:1,default:frm.doc.contact_mobile},
            {fieldtype:'HTML',options:'<p>'+__('The existing DCS and Presales Request will remain at their current stage. Survey details will be available in Additional Details.')+'</p>'}
        ],primary_action_label:__('Send Site Survey Request'),async primary_action(values) {
            if (dialog._sending) return;
            dialog._sending = true;
            dialog.get_primary_btn().prop('disabled',true);
            try {
                const r = await frappe.call({method:'bsgroup.site_survey.request_supplementary_survey',
                    args:{opportunity:frm.doc.name,...values},freeze:true});
                dialog.hide();
                await frm.reload_doc();
                frappe.msgprint(r.message.created ? __('Site Survey Request {0} created.',[r.message.name]) :
                    __('Site Survey Request {0} already exists. No duplicate was created.',[r.message.name]));
            } finally { dialog._sending=false;dialog.get_primary_btn().prop('disabled',false); }
        }});
        dialog.show();
    }
    frappe.ui.form.on('Opportunity',{refresh(frm) {
        frm.remove_custom_button(__('Request Site Survey'));
        if (!frm.is_new() && frm.doc.docstatus !== 2 && !['Lost','Closed'].includes(frm.doc.status)
            && !frm.doc.custom_site_survey_request && frm.perm?.some(p=>p.write)) {
            frm.add_custom_button(__('Request Site Survey'),()=>request(frm));
        }
        return render(frm);
    }});
    frappe.ui.form.on('Deal Cost Sheet',{refresh:render});
})();
