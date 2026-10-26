(() => {
    const fields = ['custom_survey_instructions','custom_survey_location','custom_survey_contact_phone'];
    const selected = d => d.custom_presales_required && (d.custom_elv_site_survey_required || d.custom_technical_site_survey_required);
    function render(frm) {
        if (!frm.fields_dict.custom_survey_step) return;
        const active = !!selected(frm.doc), sent = !!frm.doc.custom_site_survey_request;
        const step = Number(frm.doc.custom_survey_step || 0);
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
                button.addEventListener('click', async () => {
                    if (frm._saving_survey_step || frm.doc.custom_site_survey_request) return;
                    const value = String(field.get_value() || '').trim();
                    if (!value) { field.set_focus(); return; }
                    frm._saving_survey_step = true;
                    button.disabled = true;
                    const previous = Number(frm.doc.custom_survey_step || 0);
                    try {
                        await frm.set_value(name,value);
                        await frm.set_value('custom_survey_step',index + 1);
                        await frm.save();
                        if (frm.is_dirty() || frm.is_new()) {
                            await frm.set_value('custom_survey_step',previous);
                            return;
                        }
                        frappe.show_alert({message:__(index === 2 ? 'Survey request saved and sent to Projects.' : 'Saved. Complete the next step.'),indicator:'green'});
                        render(frm);
                        if (index < 2) frm.fields_dict[fields[index+1]].set_focus();
                    } catch (error) {
                        await frm.set_value('custom_survey_step',previous);
                        throw error;
                    } finally {
                        frm._saving_survey_step = false;
                        button.disabled = false;
                        render(frm);
                    }
                });
                wrapper.append(button);
                field.$input?.on('input.bsi_survey', () => {
                    button.hidden = !selected(frm.doc) || !!frm.doc.custom_site_survey_request || !String(field.get_value() || '').trim();
                });
            }
            button.hidden = !active || sent || step !== index || !String(field.get_value() || '').trim();
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
        custom_service_survey:reset,
        custom_business_type:reset,
        custom_site_survey_needed:reset,
        custom_elv_site_survey_required:render,
        custom_technical_site_survey_required:render,
        custom_presales_required:render
    });
})();
