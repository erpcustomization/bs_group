// Oman-only draft quotation pilot. All authority remains on the server.
(() => {
    const base = 'bsgroup.oman_quotation_flow.';
    const call = async (method, args) => (await frappe.call({method:base+method,args,freeze:true})).message;
    async function install(frm) {
        const result = await call('install', {});
        if (result?.enabled) { frappe.msgprint(__('Quotation workflow enabled. Reloading…')); window.location.reload(); }
    }
    function installationButton(frm, data) {
        if (data.can_install) frm.add_custom_button(__('Enable {0}',[data.workflow_label || 'Oman Quotation Pilot']), () => install(frm), __('Workflow setup'));
        if(data.can_install_descriptions) frm.add_custom_button(__('Enable CO Item Descriptions'),async()=>{
            const result=(await frappe.call({method:'bsgroup.oman_item_description.install',freeze:true})).message;
            if(result?.enabled) window.location.reload();
        },__('Pilot setup'));
    }
    function clientGrid(frm, active) {
        const grid=frm.fields_dict?.items?.grid;
        if(!grid?.fields_map?.custom_oman_client_description) return;
        // CO is the display complement of the stored costing choice, including
        // existing draft rows whose newly installed Check column starts at zero.
        if(active) for(const row of frm.doc.items || []) {
            row.custom_oman_use_co_description=Number(row.custom_oman_use_costing_description)?0:1;
        }
        const description=grid.fields_map.description;
        grid._oman_original_description ||= {label:description.label,read_only:description.read_only};
        grid.update_docfield_property('description','label',active?__('Item Description (Costing)'):grid._oman_original_description.label);
        grid.update_docfield_property('description','read_only',active?1:grid._oman_original_description.read_only);
        grid.update_docfield_property('custom_oman_client_description','hidden',active?0:1);
        for(const field of ['custom_oman_use_costing_description','custom_oman_use_co_description']) {
            if(grid.fields_map[field]) grid.update_docfield_property(field,'hidden',active?0:1);
        }
        if(!grid._oman_columns_wrapped){
            const original=grid.setup_user_defined_columns;
            grid.setup_user_defined_columns=function(...args){
                const result=original.apply(this,args);
                if(frm.__oman_client_descriptions) this.user_defined_columns=[
                    ['custom_oman_use_costing_description',1],['description',2],
                    ['custom_oman_use_co_description',1],['custom_oman_client_description',2],['qty',1],['rate',1],['amount',2]
                ].map(([name,columns])=>({...this.fields_map[name],in_list_view:1,columns}));
                return result;
            };
            grid._oman_columns_wrapped=true;
        }
        grid.reset_grid();
    }
    async function pdf(frm) {
        if (frm.is_dirty()) { frappe.msgprint(__('Save the quotation before converting to PDF.')); return; }
        const result = await call('convert_pdf',{quotation:frm.doc.name,expected_modified:String(frm.doc.modified)});
        if (result?.file_url) window.open(result.file_url,'_blank','noopener');
    }
    function projectFields(data) {
        if (!data.project_required) return [];
        const modules=[['elv','ELV Project'],['3cx','3CX Project'],['infra','Infra Project'],['supply','Supply Only']];
        return [
            {fieldtype:'Section Break',label:__('Select Project Category — choose one or more')},
            {fieldtype:'HTML',options:'<p><strong>'+__('A new project will be created automatically for this quotation.')+'</strong> '+__('Aira AI will automatically generate the project plan from the quotation and linked costing sheet. Please select ELV Project, 3CX Project, Infra Project or Supply Only (choose all that apply) and enter the expected completion date. The project start date will be set to today; the project team can assign a manager and refine the plan later. If AI is unavailable, the project remains created and its plan shows the action required.')+'</p>'},
            ...modules.map(([key,label])=>({fieldtype:'Check',fieldname:'module_'+key,label:__(label),default:(data.project_modules||[]).includes(key)?1:0})),
            ...[
                {fieldtype:'Date',fieldname:'expected_end_date',label:__('Expected Project Completion Date'),reqd:1,
                    description:__('Sales must enter this date before sending to Procurement. It sets the project completion date and the schedule for its project plan.')},
                {fieldtype:'Link',fieldname:'customer',label:__('Customer'),options:'Customer',reqd:1,default:data.project_customer},
                {fieldtype:'Small Text',fieldname:'custom_project_description',label:__('Project Description'),reqd:1,default:data.project_description},
            ]
        ];
    }
    async function statusDetails(frm, stage) {
        const won=stage==='Won';
        const data=won ? await call('won_context',{quotation:frm.doc.name}) : {};
        let dialog;
        const fields=[
            {fieldtype:'HTML',options:won ? '<p>'+__('Won will submit the quotation, record the approved award and create one draft Purchase Requisition with the DCS, quotation and customer PO. Existing purchasing approval remains required.')+'</p>' : ''},
            ...(won ? [
                {fieldtype:'Data',fieldname:'customer_po_reference',label:__('Customer PO Reference'),reqd:1,default:frm.doc.custom_customer_po_reference},
                {fieldtype:'Data',fieldname:'customer_po',label:__('Attached Customer PO'),read_only:1,reqd:1,default:frm.doc.custom_customer_po},
                {fieldtype:'Button',fieldname:'upload_po',label:__('Upload Customer PO'),click(){
                    new frappe.ui.FileUploader({doctype:'Quotation',docname:frm.doc.name,is_private:1,
                        on_success(file){dialog.set_value('customer_po',file.file_url);}});
                }},
                {fieldtype:'Date',fieldname:'schedule_date',label:__('Required By'),reqd:1,default:data.required_by},
                {fieldtype:'Select',fieldname:'warehouse',label:__('Target Warehouse'),options:['',...data.warehouses],reqd:data.stock_items?1:0,
                    default:data.warehouses.length===1?data.warehouses[0]:''},
                ...projectFields(data),
            ] : []),
            {fieldtype:'Small Text',fieldname:'reason',label:__('Reason'),reqd:['Lost','Cancelled','Delayed'].includes(stage)?1:0},
        ];
        dialog=new frappe.ui.Dialog({title:__('Mark quotation {0}',[stage]),fields,
            primary_action_label:won?__('Confirm Won, Create Project and Send'):__('Save Status'),
            async primary_action(values){
                dialog.disable_primary_action();
                try {
                    const projectModules=['supply','elv','3cx','infra'].filter(key=>values['module_'+key]);
                    if(won && data.project_required && !projectModules.length) {frappe.msgprint(__('Choose at least one project module.'));return;}
                    const result=await call('change_status',{quotation:frm.doc.name,stage,expected_modified:String(frm.doc.modified),
                        reason:values.reason,customer_po:values.customer_po,customer_po_reference:values.customer_po_reference,
                        schedule_date:values.schedule_date,warehouse:values.warehouse,
                        project_modules:JSON.stringify(projectModules),project_details:JSON.stringify(Object.fromEntries(
                            ['expected_end_date','customer','custom_project_description'].map(key=>[key,values[key]])))});
                    dialog.hide();await frm.reload_doc();
                    if(result?.requisition) frappe.msgprint(__('Purchase Requisition created: {0}',[frappe.utils.escape_html(result.requisition)]));
                    if(result?.project) frappe.msgprint(__('Project created/linked: {0}. Open Project Plan to follow automatic planning.',[frappe.utils.escape_html(result.project)]));
                } finally {dialog.enable_primary_action();}
            }});
        dialog.show();
    }
    frappe.ui.form.on('Quotation',{
        async refresh(frm){
            if(frm.is_new()) return;
            const name=frm.doc.name;
            const data=await call('context',{quotation:name});
            if(frm.doc.name!==name) return;
            installationButton(frm,data);
            frm.__oman_quotation_pilot=!!data.enabled;
            frm.__oman_client_descriptions=!!data.client_descriptions;
            clientGrid(frm,frm.__oman_client_descriptions);
            if(frm.fields_dict?.custom_oman_revision_no) frm.toggle_display('custom_oman_revision_no',!!data.enabled);
            if(!data.enabled) return;
            // The approved UAE PDF requires a terms template. Keep its native
            // selector and wording available even when legacy customisation hid them.
            if(data.show_standard_terms) {
                for(const field of ['tc_name','terms']) {
                    if(frm.fields_dict?.[field]) frm.toggle_display(field,true);
                }
            }
            if(data.conflict){
                frm.set_intro(__('This DCS has multiple active quotations. Review the existing quotations before saving, revising or finalising. No quotation has been merged or deleted.'),'red');
                frm.page.clear_primary_action();
                frm.remove_custom_button(__('Send to Procurement'));
                return;
            }
            if(data.discount_before_vat && data.editable){
                frm.set_df_property('apply_discount_on','read_only',1);
                frm.set_df_property('apply_discount_on','description',__('Discounts are deducted from the net amount before VAT is calculated.'));
                if(data.can_write && frm.doc.apply_discount_on!=='Net Total'){
                    await frm.set_value('apply_discount_on','Net Total');
                }
            }
            frm.set_df_property('custom_pipeline_stage','read_only',1);
            frm.remove_custom_button(__('Download Enterprise PDF'));
            frm.remove_custom_button(__('Send to Procurement'));
            frm.remove_custom_button(__('Set as Lost'));
            frm.set_intro(__('Quotation revision R{0}. DCS revisions update this same quotation. Won and Lost are locked.',[data.revision]),'blue');
            if(data.client_descriptions) frm.set_intro(__('Choose one description per line: Use Item Description (Costing) prints the original costing wording, including any part numbers. Use CO Item Description prints your editable client wording. Choices and CO wording are retained during costing revisions.'),'blue');
            frm.dashboard.set_headline(__('Quotation Status: {0} · R{1}',[frappe.utils.escape_html(frm.doc.custom_pipeline_stage || 'Draft'),data.revision]));
            if(data.editable && data.can_write){
                frm.add_custom_button(__('Revise Costing Sheet'),()=>frappe.set_route('Form','Deal Cost Sheet',frm.doc.custom_deal_cost_sheet));
                frm.add_custom_button(__('Change Status'),()=>{
                    if(frm.is_dirty()){frappe.msgprint(__('Save the quotation before changing status.'));return;}
                    frappe.prompt([{fieldtype:'Select',fieldname:'stage',label:__('Status'),options:data.statuses,reqd:1}],
                        values=>statusDetails(frm,values.stage),__('Change quotation status'),__('Continue'));
                });
            }
            if(!frm.is_dirty() && data.can_print && data.ready_to_convert) frm.add_custom_button(__('Convert to PDF'),()=>pdf(frm));
            if(data.editable && data.can_write){
                if(frm.is_dirty() || !data.ready_to_convert) frm.page.set_primary_action(__('Save'),()=>frm.save());
                else if(data.can_print) frm.page.set_primary_action(__('Convert to PDF'),()=>pdf(frm));
                else frm.page.clear_primary_action();
            }
        }
    });
    async function selectDescription(frm,cdt,cdn,costing) {
        if(!frm.__oman_client_descriptions || frm.__oman_description_selecting) return;
        frm.__oman_description_selecting=true;
        try {
            await frappe.model.set_value(cdt,cdn,{
                custom_oman_use_costing_description:costing?1:0,
                custom_oman_use_co_description:costing?0:1
            });
            frm.refresh_field('items');
            frm.remove_custom_button(__('Convert to PDF'));
            frm.page.set_primary_action(__('Save'),()=>frm.save());
            if(typeof window.eqa_readiness==='function') window.eqa_readiness(frm);
        } finally {frm.__oman_description_selecting=false;}
    }
    frappe.ui.form.on('Quotation Item',{
        custom_oman_use_costing_description(frm,cdt,cdn){
            return selectDescription(frm,cdt,cdn,!!frappe.get_doc(cdt,cdn).custom_oman_use_costing_description);
        },
        custom_oman_use_co_description(frm,cdt,cdn){
            return selectDescription(frm,cdt,cdn,!frappe.get_doc(cdt,cdn).custom_oman_use_co_description);
        },
        custom_oman_client_description(frm){
            if(frm.__oman_client_descriptions && typeof window.eqa_readiness==='function') window.eqa_readiness(frm);
        }
    });
    frappe.ui.form.on('Deal Cost Sheet',{
        async refresh(frm){
            if(frm.is_new()) return;
            const name=frm.doc.name,data=await call('dcs_context',{dcs:frm.doc.name});
            if(frm.doc.name!==name) return;
            installationButton(frm,data);
            if(!data.enabled) return;
            frm.__oman_quotation_pilot=!!data.auto_sync;
            frm.remove_custom_button(__('Create Quotation'),__('More actions'));
            if(data.conflict){
                frm.remove_custom_button(__('Revise BOQ'));
                frm.set_intro(__('This DCS has multiple active quotations. Review the existing quotation links before creating, revising or finalising. No records have been changed.'),'red');
                return;
            }
            if(frm.doc.docstatus===1 && !data.quotation) frm.add_custom_button(__('Create Linked Draft Quotation'),async()=>{
                const result=await frappe.call({method:'bsgroup.bs_group.doctype.deal_cost_sheet.deal_cost_sheet.make_quotation',args:{source_name:frm.doc.name},freeze:true});
                if(result.message) frappe.set_route('Form','Quotation',result.message);
            });
            if(data.terminal) frm.remove_custom_button(__('Revise BOQ'));
            if(data.quotation) frm.add_custom_button(__('View Linked Quotation'),()=>frappe.set_route('Form','Quotation',data.quotation));
            if(frm.doc.docstatus===1 && data.auto_sync) frm.set_intro(data.terminal ? __('The linked quotation is Won or Lost. Costing and quotation revisions are locked.') : __('Use Revise BOQ to edit costing. The linked Draft Quotation updates automatically with revision history; no new quotation is created.'),'blue');
        }
    });
})();
