// Presentation only. Native forms, list controls and permissions remain in use.
(() => {
    const doctypes = new Set([
        'Project', 'Task', 'Timesheet', 'Tech Task Scheduler', 'Site Survey Request',
        'Expense Claim', 'Employee Advance', 'Labor Preapproval',
        'Labor Attendance', 'Labor Payment Voucher', 'Task Scheduler',
    ]);
    const reports = new Set([
        'Task Summary Report', 'Task Scheduler Report', 'Tech Task Scheduler Report',
        'Weekly Project Governance Report',
    ]);
    const mounted = new Map();
    let pending = false;
    function layout() {
        pending = false;
        const route = document.body.dataset.route || '';
        const [view, name, mode] = route.split('/');
        const selected = ((view === 'List' || view === 'Form') && doctypes.has(name))
            || view === 'bs-project-modules'
            || (view === 'query-report' && reports.has(name))
            || (view === 'Workspaces' && ['BS Project', 'Projects', 'Projects, AMC & PPM Management'].includes(name));
        document.body.classList.toggle('bs-project-ui', selected);
        const page = view === 'List' && doctypes.has(name) && mode === 'List'
            ? document.getElementById(`page-${route}`) : null;
        for (const [oldPage, state] of mounted) {
            if (oldPage === page) continue;
            if (state.origin.parentNode) state.origin.replaceWith(state.actions);
            state.heading.remove();
            oldPage.classList.remove('bs-list-shell');
            mounted.delete(oldPage);
        }
        if (!page || mounted.has(page)) return;
        const main = page.querySelector('.layout-main-section');
        const actions = page.querySelector('.page-head .page-actions');
        if (!main || !actions || !main.querySelector('.list-page-form')) return;
        const heading = document.createElement('header');
        heading.className = 'bs-list-heading';
        const title = document.createElement('h1');
        title.textContent = name;
        heading.appendChild(title);
        const origin = document.createComment('Project list actions original position');
        actions.before(origin);
        heading.appendChild(actions);
        main.prepend(heading);
        page.classList.add('bs-list-shell');
        mounted.set(page, {heading, actions, origin});
    }
    function schedule() {
        if (pending) return;
        pending = true;
        requestAnimationFrame(layout);
    }
    function start() {
        layout();
        new MutationObserver(schedule).observe(document.body, {
            attributes: true, attributeFilter: ['data-route'], childList: true, subtree: true,
        });
    }
    if (document.body) start();
    else document.addEventListener('DOMContentLoaded', start, {once: true});
})();
