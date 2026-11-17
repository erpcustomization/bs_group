frappe.pages['bs-user-management'].on_page_load = function(wrapper) {
    const page = frappe.ui.make_app_page({parent:wrapper,title:__('BS User Management'),single_column:true});
    const root = $('<div class="bs-users">').appendTo(page.main);
    let request = 0, detailRequest = 0, start = 0, selected, rows = [], dirty = false;
    const style = document.createElement('style');
    style.textContent = `.bs-users{--blue:#1758bd;color:#173251;padding:8px}.bs-users .hero{background:linear-gradient(120deg,#102d52,#20599b);color:white;border-radius:16px;padding:24px;margin-bottom:18px}.bs-users h2{font-size:24px;font-weight:750;margin:0 0 6px}.bs-users h3{font-size:17px;font-weight:700}.bs-users .tools{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:16px}.bs-users .tools input{min-width:260px;flex:1}.bs-users input,.bs-users select{border:1px solid #cedbed;border-radius:8px;padding:10px;background:white}.bs-users .layout{display:grid;grid-template-columns:minmax(320px,40%) minmax(0,1fr);gap:18px}.bs-users .card{border:1px solid #dae4f1;border-radius:14px;background:white;padding:18px;margin-bottom:14px}.bs-users .directory{padding:0;overflow:hidden}.bs-users .person{width:100%;display:flex;align-items:center;gap:12px;border:0;border-bottom:1px solid #edf1f6;padding:15px;text-align:left;background:white;color:inherit}.bs-users .person:hover,.bs-users .person.selected{background:#edf4ff}.bs-users .avatar{width:40px;height:40px;flex-shrink:0;border-radius:12px;background:#e7effc;color:#1758bd;display:grid;place-items:center;font-weight:750}.bs-users .identity{min-width:0;flex:1}.bs-users .identity strong{display:block;font-size:15px}.bs-users small{display:block;color:#60758c;overflow-wrap:anywhere}.bs-users .badge{display:inline-block;border-radius:20px;padding:4px 9px;font-size:11px;background:#e9f1ff;color:#245ca7;margin:3px}.bs-users .disabled{background:#f0f1f3;color:#686f78}.bs-users .warning{background:#fff5df;color:#78581e;padding:10px;border-radius:8px}.bs-users .actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:14px}.bs-users .btn{border-radius:8px}.bs-users .muted{color:#60758c}.bs-users .matrix{width:100%;font-size:12px}.bs-users .matrix th,.bs-users .matrix td{padding:8px 4px;border-bottom:1px solid #edf1f6;text-align:center}.bs-users .matrix th:first-child,.bs-users .matrix td:first-child{text-align:left}.bs-users details{border-top:1px solid #edf1f6;padding:12px 0}.bs-users summary{cursor:pointer;font-weight:700}.bs-users .footer{display:flex;justify-content:space-between;align-items:center;padding:12px}.bs-users .empty{padding:28px;text-align:center;color:#60758c}@media(max-width:900px){.bs-users .layout{grid-template-columns:1fr}.bs-users .hero{padding:18px}}`;
    style.textContent += `.bs-users .hero h2{color:#fff!important}.bs-users .module-access{width:100%;table-layout:fixed;border-collapse:collapse;margin:16px 0}.bs-users .module-access th,.bs-users .module-access td{padding:12px 6px;border-bottom:1px solid #e3ebf6;vertical-align:top}.bs-users .module-access thead{background:#edf4ff;color:#174b86}.bs-users .module-access td{text-align:center}.bs-users .module-access input[type=checkbox]{width:19px;height:19px;accent-color:#1758bd;cursor:pointer}.bs-users .module-access input:disabled{cursor:default}.bs-users .module-access small{font-weight:400;font-size:11px;margin-top:5px}.bs-users .module-access details{border:0;font-size:11px;padding:8px 0}.bs-users .permission-note{line-height:1.35}.bs-users .layout{grid-template-columns:minmax(240px,30%) minmax(0,1fr);align-items:start}@media(max-width:900px){.bs-users .layout{grid-template-columns:1fr}}`;
    root.append(style);
    root.append('<div class="hero"><h2>BS User Management</h2><div>People, accounts and access — in one place</div></div>');
    const tools = $('<div class="tools">').appendTo(root);
    const search = $('<input type="search" aria-label="Search users" placeholder="Search first name, full name or email">').appendTo(tools);
    const state = $('<select aria-label="Account status"><option value="all">All statuses</option><option value="active">Active</option><option value="disabled">Disabled</option></select>').appendTo(tools);
    const kind = $('<select aria-label="Account type"><option value="all">All account types</option><option>System User</option><option>Website User</option></select>').appendTo(tools);
    const refresh = $('<button class="btn btn-default">Refresh</button>').appendTo(tools);
    const create = $('<button class="btn btn-primary" style="display:none">Add User</button>').appendTo(tools);
    const layout = $('<div class="layout">').appendTo(root);
    const list = $('<section class="card directory" aria-label="User directory">').appendTo(layout);
    const detail = $('<section aria-label="User details and permissions"><div class="card empty">Select a user to review their account and access.</div></section>').appendTo(layout);
    function button(host,label,action,primary=false) {
        return $('<button>').addClass('btn '+(primary?'btn-primary':'btn-default')).text(__(label)).appendTo(host).on('click',action);
    }
    async function load() {
        const token=++request;
        list.html('<div class="empty">Loading users…</div>');
        try {
            const r=await frappe.call({method:'bsgroup.user_management.directory',args:{search:search.val(),state:state.val(),kind:kind.val(),start}});
            if(token!==request)return;
            rows=r.message.rows;create.toggle(!!r.message.can_create);list.empty();
            for(const user of rows) {
                const row=$('<button class="person">').toggleClass('selected',user.name===selected).appendTo(list);
                const identity=$('<span class="identity">').appendTo(row);
                $('<strong>').text(user.first_name||user.full_name||'Name missing').appendTo(identity);
                $('<small>').text(user.name).appendTo(identity);
                row.on('click',()=>show(user.name));
            }
            if(!rows.length)list.append('<div class="empty">No matching users. Try another name or clear the filters.</div>');
            const footer=$('<div class="footer">').appendTo(list);
            button(footer,'Previous',()=>{start=Math.max(0,start-100);load();}).prop('disabled',!start);
            $('<small>').text(rows.length?`${start+1}–${start+rows.length}`:'0 users').appendTo(footer);
            button(footer,'Next',()=>{start+=100;load();}).prop('disabled',!r.message.has_more);
        } catch(e) {if(token===request)list.html('<div class="empty">Unable to load users. Your existing User administration permissions are required.</div>');}
    }
    async function show(user) {
        if(dirty){frappe.confirm('Discard unsaved account changes?',()=>{dirty=false;show(user);});return;}
        const token=++detailRequest; selected=user;detail.html('<div class="card">Loading account…</div>');
        list.find('.person').removeClass('selected');
        try {
            const r=await frappe.call({method:'bsgroup.user_management.details',args:{user}});
            if(token!==detailRequest)return;
            const d=r.message;detail.empty();
            const head=$('<div class="card">').appendTo(detail);
            $('<h2>').text(d.first_name||'First name missing').appendTo(head);
            $('<small>').text(d.name).appendTo(head);
            $('<span class="badge">').toggleClass('disabled',!d.enabled).text(d.enabled?'Active':'Disabled').appendTo(head);
            $('<span class="badge">').text(d.user_type).appendTo(head);
            $('<p class="muted">').text('Last login: '+(d.last_login?frappe.datetime.str_to_user(d.last_login):'Not recorded')).appendTo(head);
            if(!d.first_name)$('<p class="warning">').text('First Name is required. Complete it when editing this account.').appendTo(head);
            for(const e of d.employees)$('<p>').text(`${e.employee_name} · ${e.company} · ${e.department||'No department'} · ${e.status}`).appendTo(head);
            if(!d.employees.length)$('<p class="muted">').text('No employee link visible to you. This may be a service account or an unlinked employee.').appendTo(head);
            const actions=$('<div class="actions">').appendTo(head);
            const inline=$('<div class="card" aria-label="Inline account editor">').appendTo(detail);
            function openPanel(mode){
                if(dirty){frappe.confirm('Discard unsaved account changes?',()=>{dirty=false;openPanel(mode);});return;}
                actions.find('button').removeClass('btn-primary').addClass('btn-default');
                actions.find('button').filter((i,el)=>el.textContent===mode).removeClass('btn-default').addClass('btn-primary');
                accountPanel(inline,d,mode);
            }
            button(actions,'Account Details',()=>openPanel('Account Details'));
            button(actions,'Permissions',()=>openPanel('Permissions'));
            button(actions,'Account Settings',()=>openPanel('Account Settings'));
            openPanel('Permissions');
            const advanced=$('<details class="card">').appendTo(detail);
            $('<summary>').text('Advanced access details & history').appendTo(advanced);
            const access=$('<div>').appendTo(advanced);$('<h3>').text('Module permissions').appendTo(access);
            $('<p class="muted">').text('Role grants only. Actual records also depend on ownership, user restrictions, assignments, sharing and workflow rules. Approval authority is determined by the existing workflow.').appendTo(access);
            for(const module of d.modules) {
                const group=$('<details>').appendTo(access);$('<summary>').text(module.title).appendTo(group);
                const table=$('<table class="matrix"><thead><tr><th>Record</th><th>View</th><th>Create</th><th>Edit</th><th>Submit</th><th>Cancel</th><th>Share</th></tr></thead><tbody></tbody></table>').appendTo(group);
                for(const row of module.rows) {
                    const tr=$('<tr>').appendTo(table.find('tbody'));$('<td>').text(row.doctype+(row.owner_only?' *':'')).appendTo(tr);
                    for(const a of ['read','create','write','submit','cancel','share'])$('<td>').text(row.actions[a]?'✓':'—').appendTo(tr);
                }
            }
            $('<small>').text('* Includes an owner-based rule; access may be limited to owned records. Disabled accounts cannot sign in.').appendTo(access);
            const restrictions=$('<div>').appendTo(advanced);$('<h3>').text('Record restrictions').appendTo(restrictions);
            $('<p class="muted">').text('These are existing User Permission rules. An empty list does not mean unrestricted access; assignment rules and individual sharing remain in effect.').appendTo(restrictions);
            for(const rule of d.restrictions)button(restrictions,`${rule.allow}: ${rule.for_value} · ${rule.applicable_for||'All applicable records'}`,()=>editor('User Permission',rule.name));
            if(d.can_manage_restrictions)button($('<div class="actions">').appendTo(restrictions),'Add Restriction',()=>editor('User Permission',null,null,{user:d.name}));
            const history=$('<div>').appendTo(advanced);$('<h3>').text('Account change history').appendTo(history);
            for(const item of d.history)button($('<div>').appendTo(history),`${frappe.datetime.str_to_user(item.creation)} · ${item.owner}`,()=>editor('Version',item.name));
            if(!d.history.length)$('<p class="muted">').text('No visible account versions. The account editor also retains its native activity history.').appendTo(history);
        } catch(e) {if(token===detailRequest)detail.html('<div class="card">This account could not be opened with your current permissions.</div>');}
    }
    function accountPanel(host,d,mode) {
        host.empty();$('<h3>').text(mode).appendTo(host);
        if(mode==='Permissions'){modulePanel(host,d);return;}
        const controls={}, labels={first_name:'First Name',middle_name:'Middle Name',last_name:'Last Name',enabled:'Account status',user_type:'Account type'};
        function field(key,options){
            const label=$('<label style="display:block;margin:12px 0">').text(labels[key]+(key==='first_name'?' *':'')).appendTo(host);
            const input=$(options?'<select>':'<input type="text">').attr('aria-label',labels[key]).css({display:'block',width:'100%',marginTop:'6px'}).appendTo(label);
            if(options)for(const [value,text] of options)$('<option>').val(value).text(text).appendTo(input);
            input.val(d[key]??'').prop('disabled',!d.can_write).on('input change',()=>{dirty=true;save.prop('disabled',false);});
            if(key==='first_name')input.prop('required',true);
            controls[key]=input;
        }
        if(mode==='Account Details'){
            field('first_name');field('middle_name');field('last_name');
            $('<small>').text('Email: '+d.name).appendTo(host);
        } else if(mode==='Account Settings'){
            field('enabled',[[1,'Active'],[0,'Disabled']]);
            field('user_type',[['System User','ERP user'],['Website User','Portal user']]);
            $('<small>').text('Other account settings are retained. Disabling an account prevents sign-in.').appendTo(host);
        }
        const footer=$('<div class="actions">').appendTo(host);
        const save=button(footer,'Save changes',()=>{
            const changes={},review=[];
            for(const [key,input] of Object.entries(controls)){
                const value=key==='enabled'?Number(input.val()):String(input.val()||'').trim();
                if(value!==(d[key]??'')){changes[key]=value;review.push(labels[key]+': '+(key==='enabled'?(value?'Active':'Disabled'):value||'(blank)'));}
            }
            if('first_name' in changes&&!changes.first_name){frappe.msgprint('First Name is required.');return;}
            if(!Object.keys(changes).length){dirty=false;save.prop('disabled',true);frappe.show_alert('No changes to save.');return;}
            const content=$('<div>');$('<p>').text('Save these changes for '+d.name+'?').appendTo(content);for(const line of review)$('<p>').text(line).appendTo(content);
            frappe.confirm(content.html(),async()=>{
                save.prop('disabled',true);
                try{await frappe.call({method:'bsgroup.user_management.save_account',args:{user:d.name,expected_modified:d.modified,changes},freeze:true,freeze_message:'Saving account…'});dirty=false;frappe.show_alert({message:'Account changes saved',indicator:'green'});await load();await show(d.name);}
                catch(e){save.prop('disabled',false);}
            });
        },true).prop('disabled',true);
        button(footer,'Discard changes',()=>{dirty=false;accountPanel(host,d,mode);});
        if(!d.can_write)footer.hide();
    }
    function modulePanel(host,d){
        const changes={};
        const recordName=name=>({'Material Request':'Purchase Requisition','Deal Cost Sheet':'Costing Sheet','Labor Preapproval':'Labour Approval','Employee Checkin':'Attendance Check-ins'}[name]||name);
        $('<p class="muted">').text('View, edit and approve by module. Existing access is protected; new grants can be added or removed here.').appendTo(host);
        const table=$('<table class="module-access"><thead><tr><th>Module</th><th>View</th><th>Edit</th><th>Approve</th></tr></thead><tbody></tbody></table>').appendTo(host);
        for(const row of d.module_access||[]){
            const tr=$('<tr>').appendTo(table.find('tbody'));
            const title=$('<th scope="row">').text(row.module).appendTo(tr);
            const scope=$('<details>').appendTo(title);$('<summary>').text('Scope & rules').appendTo(scope);
            $('<small>').text(row.records.map(recordName).join(', ')).appendTo(scope);
            if(row.note)$('<small>').text(row.note).appendTo(scope);
            for(const action of ['view','edit','approve']){
                const cell=row.cells[action],key=row.module+'.'+action;
                const td=$('<td>').appendTo(tr),label=$('<label>').appendTo(td);
                const input=$('<input type="checkbox">').attr('aria-label',row.module+' '+action).attr('title',cell.reason||cell.note)
                    .prop({checked:cell.checked,indeterminate:cell.partial,disabled:!d.can_write||(!cell.editable&&!cell.managed)}).appendTo(label);
                $('<small>').text(cell.status).appendTo(label);
                if(cell.reason){$('<small class="permission-note">').attr('title',cell.reason).text(cell.inherited?'Protected':'Restricted').appendTo(td);$('<small>').text(action.charAt(0).toUpperCase()+action.slice(1)+': '+cell.reason).appendTo(scope);}
                if(action==='approve')$('<small>').text(cell.note).appendTo(scope);
                input.on('change',()=>{const enabled=input.prop('checked');if(enabled===cell.managed)delete changes[key];else changes[key]=enabled;dirty=!!Object.keys(changes).length;review.prop('disabled',!dirty);});
            }
        }
        const manager=(d.module_access||[]).find(row=>row.module==='Projects')?.cells?.manager;
        if(manager){
            const card=$('<div class="card project-manager-access">').appendTo(host);
            const label=$('<label style="display:flex;gap:10px;align-items:center;font-weight:600">').appendTo(card);
            const input=$('<input type="checkbox">').attr('aria-label',manager.label)
                .prop({checked:manager.checked,disabled:!d.can_write||(!manager.editable&&!manager.managed)}).appendTo(label);
            $('<span>').text(manager.label).appendTo(label);
            $('<p class="muted">').text(manager.note).appendTo(card);
            if(manager.reason)$('<small>').text(manager.reason).appendTo(card);
            input.on('change',()=>{const enabled=input.prop('checked');if(enabled===manager.managed)delete changes['Projects.manager'];else changes['Projects.manager']=enabled;dirty=!!Object.keys(changes).length;review.prop('disabled',!dirty);});
        }
        $('<small>').text('Limited means access to some record types. Existing restrictions apply except for the explicitly reviewed all-projects manager grant above. A disabled account cannot sign in.').appendTo(host);
        const footer=$('<div class="actions">').appendTo(host);
        const review=button(footer,'Preview changes',async()=>{
            review.prop('disabled',true);
            try{
                const response=await frappe.call({method:'bsgroup.user_module_access.preview',args:{user:d.name,expected_modified:d.modified,changes}});
                const p=response.message;
                if(!p.has_changes){frappe.msgprint('No access changes to save.');return;}
                const dialog=new frappe.ui.Dialog({title:'Review permission changes',size:'large',fields:[{fieldname:'preview',fieldtype:'HTML'}],primary_action_label:'Save permissions',primary_action:async()=>{
                    dialog.disable_primary_action();
                    try{await frappe.call({method:'bsgroup.user_module_access.save',args:{user:d.name,expected_modified:d.modified,changes,preview_token:p.token},freeze:true,freeze_message:'Saving permissions…'});dirty=false;dialog.hide();frappe.show_alert({message:'Module permissions saved',indicator:'green'});await load();await show(d.name);}
                    catch(e){dialog.enable_primary_action();}
                }});
                const content=dialog.fields_dict.preview.$wrapper;
                $('<p>').text('Account: '+d.name).appendTo(content);
                for(const change of p.changes)$('<p>').text(change.module+' — '+change.permission+': '+(change.enabled?'Add grant':'Remove new grant')).appendTo(content);
                $('<p>').text(p.note).appendTo(content);
                const impact=$('<table class="table table-bordered"><thead><tr><th>Records</th><th>Added</th><th>Removed</th></tr></thead><tbody></tbody></table>').appendTo(content);
                for(const item of p.impact){const tr=$('<tr>').appendTo(impact.find('tbody'));$('<td>').text(recordName(item.record)+(item.own_records?' (own records)':'')+(item.field_level?' (restricted fields '+item.field_level+')':'')).appendTo(tr);$('<td>').text(item.added.join(', ')||'—').appendTo(tr);$('<td>').text(item.removed.join(', ')||'—').appendTo(tr);}
                if(!p.impact.length)$('<p>').text('These rights are already covered by another grant. Existing record access remains unchanged.').appendTo(content);
                dialog.show();
            }finally{review.prop('disabled',!dirty);}
        },true).prop('disabled',true);
        button(footer,'Discard changes',()=>{dirty=false;host.empty();$('<h3>').text('Permissions').appendTo(host);modulePanel(host,d);});
        if(!d.can_write)footer.hide();
    }
    function editor(doctype,name,tab,defaults={}) {
        const dialog=new frappe.ui.Dialog({title:name?`${doctype} · ${name}`:`New ${doctype}`,size:'extra-large',fields:[{fieldname:'editor',fieldtype:'HTML'}]});
        const host=dialog.fields_dict.editor.$wrapper;
        $('<p class="text-muted">').text('Use Save in this panel to apply changes. Existing permissions and validation remain enforced. First Name is required for user accounts.').appendTo(host);
        const loading=$('<p>').text('Loading account editor…').appendTo(host);
        const frame=$('<iframe title="User administration editor" style="width:100%;height:73vh;border:0;visibility:hidden">').appendTo(host);
        let timer,closing=false,initialized=false;
        frame.on('load',()=>{const win=frame[0].contentWindow;let attempts=0;clearInterval(timer);timer=setInterval(()=>{
            const f=win.frappe;
            if(!f?.boot?.user||!f?.model?.with_doctype||!f?.set_route){if(++attempts>120){clearInterval(timer);loading.text('Unable to load the editor. Close and try again.');}return;}
            clearInterval(timer);if(initialized)return;initialized=true;
            const css=win.document.createElement('style');css.textContent='#desk-dock,.body-sidebar,.workspace-sidebar,.navbar,.body-sidebar-container{display:none!important}.main-section,.layout-main-section-wrapper{margin-left:0!important}.page-container{padding:12px!important}';win.document.head.appendChild(css);
            if(doctype==='User')f.ui.form.on('User',{refresh(frm){frm.set_df_property('first_name','reqd',1);frm.set_df_property('first_name','hidden',0);},validate(frm){if(!String(frm.doc.first_name||'').trim())f.throw('First Name is required.');}});
            f.after_ajax(()=>f.model.with_doctype(doctype,()=>{
                let id=name;if(!id){const doc=f.model.get_new_doc(doctype);Object.assign(doc,defaults);id=doc.name;}
                Promise.resolve(f.set_route('Form',doctype,id)).then(()=>f.after_ajax(()=>{if(tab)win.document.getElementById('user-'+tab+'-tab')?.click();}));
                loading.remove();frame.css('visibility','visible');
            }));
        },100);});
        dialog.$wrapper.on('hide.bs.modal',event=>{if(!closing&&frame[0].contentWindow?.cur_frm?.is_dirty()){event.preventDefault();frappe.confirm('Discard unsaved changes and close?',()=>{closing=true;dialog.hide();});}});
        dialog.$wrapper.on('hidden.bs.modal',()=>{clearInterval(timer);frame.remove();load();if(selected)show(selected);});
        dialog.show();frame.attr('src','/desk');
    }
    function createUser(){
        const dialog=new frappe.ui.Dialog({title:'Create user',fields:[
            {fieldname:'first_name',label:'First Name',fieldtype:'Data',reqd:1},
            {fieldname:'last_name',label:'Last Name',fieldtype:'Data'},
            {fieldname:'email',label:'Email',fieldtype:'Data',options:'Email',reqd:1},
            {fieldname:'enabled',label:'Enable account',fieldtype:'Check',default:1},
            {fieldtype:'HTML',options:'<p>Module permissions are chosen after creation. No administrator role is added. No invitation email is sent; the user can use Forgot Password after activation.</p>'}
        ],primary_action_label:'Create user',primary_action:async(values)=>{
            dialog.disable_primary_action();
            try{const r=await frappe.call({method:'bsgroup.user_management.create_account',args:values,freeze:true});dialog.hide();await load();await show(r.message.name);frappe.show_alert({message:'User created. Review module permissions below.',indicator:'green'});}
            catch(e){dialog.enable_primary_action();}
        }});dialog.show();
    }
    let debounce;search.on('input',()=>{clearTimeout(debounce);debounce=setTimeout(()=>{start=0;load();},250);});
    state.add(kind).on('change',()=>{start=0;load();});refresh.on('click',()=>{load();if(selected)show(selected);});create.on('click',createUser);
    load();
};
