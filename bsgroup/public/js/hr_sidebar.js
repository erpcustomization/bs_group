/* BS HR uses the main application sidebar, without changing native HR permissions. */
(() => {
    const sections=[['dashboard','Dashboard','layout-dashboard'],['organization','Organization Structure','network'],['employees','Employee Profiles','users'],['onboarding','Onboarding','user-plus'],['attendance','Attendance','clock'],['leave','Leave Approvals','calendar-check'],['review','Attendance and Leave Management','calendar'],['policies','Policies','file-text'],['warnings','Warnings','shield-alert'],['exit','Exit Interviews','message-circle'],['offboarding','Offboarding','log-out'],['requests','HR Requests','inbox']];
    function update() {
        // Existing sessions may retain boot data from before this menu was installed.
        // Server endpoints independently enforce the same audience and document permissions.
        if(!(frappe.boot.bs_hr_management || ['Administrator','muskan@bitssecureit.com'].includes(frappe.session.user) || frappe.user.has_role('System Manager')))return;
        const hosts=document.querySelectorAll('.body-sidebar .sidebar-items, .desk-sidebar .sidebar-items');
        for(const host of hosts) {
            let group=host.querySelector('.sidebar-item-container[data-id="BS HR"]');
            if(!group && !location.pathname.includes('hr-dashboard'))continue;
            if(!group) {
                group=document.createElement('div');group.className='sidebar-item-container section-item';group.dataset.id='BS HR';
                group.innerHTML='<div class="standard-sidebar-item"><button class="item-anchor section-break btn-reset" type="button" aria-expanded="true"><span class="sidebar-item-label">BS HR</span></button></div><div class="sidebar-child-item nested-container"></div>';
                const toggle=group.querySelector('button');toggle.onclick=()=>{const child=group.querySelector('.sidebar-child-item');child.hidden=!child.hidden;toggle.setAttribute('aria-expanded',String(!child.hidden));};
                host.append(group);
            }
            const children=group.querySelector(':scope > .sidebar-child-item');
            if(!children)continue;
            if(!children.querySelector('.bs-hr-sidebar-link[data-hr-section="review"]')) {
                children.replaceChildren();
                for(const [key,label,icon] of sections) {
                    const row=document.createElement('div');row.className='sidebar-item-container';
                    const item=document.createElement('div');item.className='standard-sidebar-item';row.append(item);
                    const a=document.createElement('a');a.className='item-anchor bs-hr-sidebar-link';a.dataset.hrSection=key;
                    a.href='/desk/bs-group/hr-dashboard?hr_section='+key;
                    a.innerHTML=`<span class="sidebar-item-icon"><svg class="icon current-color icon-sm" aria-hidden="true"><use href="#icon-${icon}"></use></svg></span><span class="sidebar-item-label"></span>`;
                    a.querySelector('.sidebar-item-label').textContent=label;
                    a.onclick=event=>{if(event.ctrlKey||event.metaKey||event.shiftKey||event.altKey)return;event.preventDefault();Promise.resolve(frappe.set_route('hr-dashboard',{hr_section:key})).then(()=>window.bsHRSelectSection?.(key));};
                    item.append(a);children.append(row);
                }
            }
            const active=location.pathname.includes('hr-dashboard')?(new URLSearchParams(location.search).get('hr_section')||'dashboard'):null;
            children.querySelectorAll('.bs-hr-sidebar-link').forEach(a=>{
                const selected=a.dataset.hrSection===active;
                a.parentElement.classList.toggle('selected',selected);
                if(selected)a.setAttribute('aria-current','page');else a.removeAttribute('aria-current');
            });
        }
    }
    frappe.router.on('change',()=>setTimeout(update,50));
    new MutationObserver(update).observe(document.body,{childList:true,subtree:true});
    update();
})();
