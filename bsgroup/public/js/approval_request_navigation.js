// Account-specific menu entry; the server independently protects data and decisions.
(() => {
    if (window.top !== window.self) return;
    const allowed = () => frappe.session?.user === 'mohan@bitssecureit.com';
    let scheduled = false;
    function update() {
        scheduled = false;
        if (!allowed()) {
            document.querySelectorAll('.bs-approval-request-link').forEach(row => row.remove());
            return;
        }
        document.querySelectorAll('.body-sidebar .sidebar-items, .desk-sidebar .sidebar-items').forEach(host => {
            const quotation = [...host.querySelectorAll('a[href]')].find(a => /\/(?:quotation)(?:[/?#]|$)/.test(a.getAttribute('href') || ''));
            if (!quotation) { host.querySelectorAll('.bs-approval-request-link').forEach(row=>row.remove()); return; }
            const anchor = quotation.closest('.sidebar-item-container') || quotation.closest('.standard-sidebar-item') || quotation.parentElement;
            let row = host.querySelector('.bs-approval-request-link');
            if (!row) {
                row = document.createElement('div'); row.className = 'sidebar-item-container bs-approval-request-link';
                const item = document.createElement('div'); item.className = 'standard-sidebar-item';row.append(item);
                const link = document.createElement('a'); link.className = 'item-anchor';
                link.href = '/desk/bs-group/bs-approval-request';
                link.innerHTML='<span class="sidebar-item-icon"><svg class="icon current-color icon-sm" aria-hidden="true"><use href="#icon-clipboard-check"></use></svg></span><span class="sidebar-item-label"></span>';
                link.querySelector('.sidebar-item-label').textContent = __('Approval Request');item.append(link);
            }
            if (anchor.nextElementSibling !== row) anchor.after(row);
            row.querySelector('.standard-sidebar-item').classList.toggle('selected', (document.body.dataset.route || '').includes('bs-approval-request'));
        });
    }
    function schedule() { if (!scheduled) { scheduled = true; setTimeout(update, 100); } }
    function start() {
        new MutationObserver(schedule).observe(document.body, {childList:true,subtree:true});
        frappe.router.on('change', schedule); $(document).on('page-change', schedule); schedule();
    }
    if (document.body) start(); else document.addEventListener('DOMContentLoaded', start, {once:true});
})();
