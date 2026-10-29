(() => {
    const fields = ['custom_survey_instructions','custom_survey_location','custom_survey_contact_phone'];
    const selected = d => (d.custom_elv_site_survey_required || d.custom_technical_site_survey_required);
    const entered = field => String(field?.$wrapper?.[0]?.querySelector('input,textarea')?.value ?? field?.get_value?.() ?? '').trim();
    function render(frm) {
        if (!frm.fields_dict.custom_survey_step) return;
        const active = !!selected(frm.doc), sent = !!frm.doc.custom_site_survey_request;
        for (const name of [...fields, 'custom_survey_contact_name']) frm.toggle_reqd(name, active && !sent);
        frm.toggle_reqd('custom_enquiry', frm.is_new() || active);
        const step = Number(frm.doc.custom_survey_step || 0);
        const contact = frm.fields_dict.custom_survey_contact_name;
        if (contact) {
            frm.set_df_property('custom_survey_contact_name','read_only',sent);
            frm.toggle_display('custom_survey_contact_name',active && (sent || step >= 2));
        }
        fields.forEach((name,index) => {
            const field = frm.fields_dict[name];
            if (!field) return;
            frm.set_df_property(name,'read_only',sent);
            frm.toggle_display(name,active && (sent || step >= index));
            const wrapper = field.$wrapper[0];
            let button = wrapper.querySelector('.bsi-survey-step-ok');
            if (!button) {
                button = document.createElement('button');
                button.type = 'button';
                button.className = 'btn btn-primary btn-sm bsi-survey-step-ok';
                button.textContent = __('OK');
                button.style.marginTop = '7px';
                wrapper.append(button);
            }
                button.onclick = async () => {
                    if (frm._saving_survey_step || frm.doc.custom_site_survey_request) return;
                    const value = entered(field);
                    if (!value) { field.set_focus(); return; }
                    const contactName = entered(contact);
                    if (index === 2 && !contactName) {
                        frappe.msgprint(__('Enter the contact person name.'));
                        contact?.set_focus();
                        return;
                    }
                    frm._saving_survey_step = true;
                    button.disabled = true;
                    const previous = Number(frm.doc.custom_survey_step || 0);
                    try {
                        await frm.set_value(name,value);
                        if (index === 2) await frm.set_value('custom_survey_contact_name',contactName);
                        await frm.set_value('custom_survey_step',index + 1);
                        const draft = frm.is_new();
                        if (!draft && index === 2) {
                            await frm.save();
                            if (frm.is_dirty()) {
                                await frm.set_value('custom_survey_step',previous);
                                return;
                            }
                        }
                        frappe.show_alert({message:__(draft
                            ? (index === 2 ? 'Details confirmed. Click Submit Opportunity when ready.' : 'Confirmed. Complete the next step.')
                            : (index === 2 ? 'Survey request saved and sent to Projects.' : 'Confirmed. Complete the next step before saving.')),indicator:'green'});
                        frm.trigger('bsi_update_submit');
                        render(frm);
                        if (index < 2) (index === 1 && contact ? contact : frm.fields_dict[fields[index+1]]).set_focus();
                    } catch (error) {
                        await frm.set_value('custom_survey_step',previous);
                        frappe.msgprint({title:__('Unable to confirm survey details'),message:error.message || String(error),indicator:'red'});
                    } finally {
                        frm._saving_survey_step = false;
                        button.disabled = false;
                        render(frm);
                    }
                };
            // Controls hidden by depends_on may create/recreate their input only
            // when revealed. Listen on the persistent wrapper, not that input.
            const updateButton = () => {
                button.hidden = !selected(frm.doc) || !!frm.doc.custom_site_survey_request || !entered(field)
                    || (index === 2 && !entered(contact));
            };
            field.$wrapper.off('input.bsi_survey').on('input.bsi_survey','input,textarea',updateButton);
            if (index === 2 && contact) contact.$wrapper.off('input.bsi_survey_contact').on('input.bsi_survey_contact','input,textarea',updateButton);
            button.hidden = !active || sent || step !== index || !entered(field);
            if (index === 2 && !entered(contact)) button.hidden = true;
            button.disabled = !!frm._saving_survey_step;
        });
    }
    async function changed(frm, index) {
        if (!frm.doc.custom_site_survey_request && !frm._saving_survey_step && Number(frm.doc.custom_survey_step || 0) > index) {
            await frm.set_value('custom_survey_step',index);
        }
        render(frm);
    }
    async function reset(frm) {
        if (!frm.doc.custom_site_survey_request) await frm.set_value('custom_survey_step',0);
        render(frm);
    }
    frappe.ui.form.on('Opportunity', {
        refresh:render,
        custom_survey_step:render,
        custom_survey_instructions(frm){return changed(frm,0);},
        custom_survey_location(frm){return changed(frm,1);},
        custom_survey_contact_phone(frm){return changed(frm,2);},
        custom_survey_contact_name(frm){return changed(frm,2);},
        custom_service_survey:reset,
        custom_business_type:reset,
        custom_site_survey_needed:reset,
        custom_elv_site_survey_required:render,
        custom_technical_site_survey_required:render,
        custom_presales_required:render
    });
})();
