frappe.pages['bs-user-management'].on_page_load = function(wrapper) {
    const page = frappe.ui.make_app_page({parent:wrapper,title:__('BS User Management'),single_column:true});
    const root = $('<div class="bs-users">').appendTo(page.main);
    let request = 0, detailRequest = 0, start = 0, selected, rows = [];
    const style = document.createElement('style');
    style.textContent = `.bs-users{--blue:#1758bd;color:#173251;padding:8px}.bs-users .hero{background:linear-gradient(120deg,#102d52,#20599b);color:white;border-radius:16px;padding:24px;margin-bottom:18px}.bs-users h2{font-size:24px;font-weight:750;margin:0 0 6px}.bs-users h3{font-size:17px;font-weight:700}.bs-users .tools{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:16px}.bs-users .tools input{min-width:260px;flex:1}.bs-users input,.bs-users select{border:1px solid #cedbed;border-radius:8px;padding:10px;background:white}.bs-users .layout{display:grid;grid-template-columns:minmax(320px,40%) minmax(0,1fr);gap:18px}.bs-users .card{border:1px solid #dae4f1;border-radius:14px;background:white;padding:18px;margin-bottom:14px}.bs-users .directory{padding:0;overflow:hidden}.bs-users .person{width:100%;display:flex;align-items:center;gap:12px;border:0;border-bottom:1px solid #edf1f6;padding:15px;text-align:left;background:white;color:inherit}.bs-users .person:hover,.bs-users .person.selected{background:#edf4ff}.bs-users .avatar{width:40px;height:40px;flex-shrink:0;border-radius:12px;background:#e7effc;color:#1758bd;display:grid;place-items:center;font-weight:750}.bs-users .identity{min-width:0;flex:1}.bs-users .identity strong{display:block;font-size:15px}.bs-users small{display:block;color:#60758c;overflow-wrap:anywhere}.bs-users .badge{display:inline-block;border-radius:20px;padding:4px 9px;font-size:11px;background:#e9f1ff;color:#245ca7;margin:3px}.bs-users .disabled{background:#f0f1f3;color:#686f78}.bs-users .warning{background:#fff5df;color:#78581e;padding:10px;border-radius:8px}.bs-users .actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:14px}.bs-users .btn{border-radius:8px}.bs-users .muted{color:#60758c}.bs-users .matrix{width:100%;font-size:12px}.bs-users .matrix th,.bs-users .matrix td{padding:8px 4px;border-bottom:1px solid #edf1f6;text-align:center}.bs-users .matrix th:first-child,.bs-users .matrix td:first-child{text-align:left}.bs-users details{border-top:1px solid #edf1f6;padding:12px 0}.bs-users summary{cursor:pointer;font-weight:700}.bs-users .footer{display:flex;justify-content:space-between;align-items:center;padding:12px}.bs-users .empty{padding:28px;text-align:center;color:#60758c}@media(max-width:900px){.bs-users .layout{grid-template-columns:1fr}.bs-users .hero{padding:18px}}`;
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
                $('<strong>').text(user.full_name||user.first_name||'Name missing').appendTo(identity);
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
        const token=++detailRequest; selected=user;detail.html('<div class="card">Loading account…</div>');
        list.find('.person').removeClass('selected');
        try {
            const r=await frappe.call({method:'bsgroup.user_management.details',args:{user}});
            if(token!==detailRequest)return;
            const d=r.message;detail.empty();
            const head=$('<div class="card">').appendTo(detail);
            $('<h2>').text(d.first_name||'First name missing').appendTo(head);
            $('<div>').text(d.full_name||d.name).appendTo(head);
            $('<small>').text(d.name).appendTo(head);
            $('<span class="badge">').toggleClass('disabled',!d.enabled).text(d.enabled?'Active':'Disabled').appendTo(head);
            $('<span class="badge">').text(d.user_type).appendTo(head);
            $('<p class="muted">').text('Last login: '+(d.last_login?frappe.datetime.str_to_user(d.last_login):'Not recorded')).appendTo(head);
            if(!d.first_name)$('<p class="warning">').text('First Name is required. Complete it when editing this account.').appendTo(head);
            for(const e of d.employees)$('<p>').text(`${e.employee_name} · ${e.company} · ${e.department||'No department'} · ${e.status}`).appendTo(head);
            if(!d.employees.length)$('<p class="muted">').text('No employee link visible to you. This may be a service account or an unlinked employee.').appendTo(head);
            const actions=$('<div class="actions">').appendTo(head);
            button(actions,'Account Details',()=>editor('User',d.name,'user_details_tab'),true);
            button(actions,'Roles & Permissions',()=>editor('User',d.name,'roles_permissions_tab'));
            button(actions,'Account Settings',()=>editor('User',d.name,'settings_tab'));
            const roles=$('<div class="card">').appendTo(detail);$('<h3>').text('Current roles and profiles').appendTo(roles);
            $('<p class="muted">').text('Existing roles are retained. Review changes in the account editor and use Save to apply them.').appendTo(roles);
            for(const role of d.roles)$('<span class="badge">').text(role).appendTo(roles);
            $('<p>').text('Role profiles: '+([...(d.role_profiles||[]),d.role_profile].filter(Boolean).join(', ')||'None')).appendTo(roles);
            $('<p>').text('Module profile: '+(d.module_profile||'None')).appendTo(roles);
            if(d.blocked_modules.length)$('<p>').text('Hidden modules: '+d.blocked_modules.join(', ')).appendTo(roles);
            const access=$('<div class="card">').appendTo(detail);$('<h3>').text('Module permissions').appendTo(access);
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
            const restrictions=$('<div class="card">').appendTo(detail);$('<h3>').text('Record restrictions').appendTo(restrictions);
            $('<p class="muted">').text('These are existing User Permission rules. An empty list does not mean unrestricted access; assignment rules and individual sharing remain in effect.').appendTo(restrictions);
            for(const rule of d.restrictions)button(restrictions,`${rule.allow}: ${rule.for_value} · ${rule.applicable_for||'All applicable records'}`,()=>editor('User Permission',rule.name));
            if(d.can_manage_restrictions)button($('<div class="actions">').appendTo(restrictions),'Add Restriction',()=>editor('User Permission',null,null,{user:d.name}));
            const history=$('<div class="card">').appendTo(detail);$('<h3>').text('Account change history').appendTo(history);
            for(const item of d.history)button($('<div>').appendTo(history),`${frappe.datetime.str_to_user(item.creation)} · ${item.owner}`,()=>editor('Version',item.name));
            if(!d.history.length)$('<p class="muted">').text('No visible account versions. The account editor also retains its native activity history.').appendTo(history);
        } catch(e) {if(token===detailRequest)detail.html('<div class="card">This account could not be opened with your current permissions.</div>');}
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
    let debounce;search.on('input',()=>{clearTimeout(debounce);debounce=setTimeout(()=>{start=0;load();},250);});
    state.add(kind).on('change',()=>{start=0;load();});refresh.on('click',()=>{load();if(selected)show(selected);});create.on('click',()=>editor('User'));
    load();
};
