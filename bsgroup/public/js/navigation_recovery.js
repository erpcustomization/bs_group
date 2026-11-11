// Recover an empty collapsed module rail without adding links or changing access.
(() => {
    if (window.top !== window.self) return; // Project form popups intentionally hide navigation.
    const recovered = new Set();
    let scheduled = false, button;
    function visible(element) {
        return element && element.getBoundingClientRect().width > 0
            && element.getBoundingClientRect().height > 0
            && getComputedStyle(element).display !== 'none'
            && getComputedStyle(element).visibility !== 'hidden';
    }
    function update() {
        scheduled = false;
        const sidebar = document.querySelector('.body-sidebar-container');
        const toggle = sidebar?.querySelector('.sidebar-collapse-arrow');
        const links = sidebar?.querySelector('.sidebar-items a[href]');
        if (!sidebar || !toggle || !links) { if (button) button.hidden = true; return; }
        const collapsed = document.body.classList.contains('sidebar-collapsed');
        if (!button) {
            button = document.createElement('button');
            button.type = 'button';button.id = 'bs-show-modules';
            button.className = 'btn btn-default btn-sm';
            button.textContent = __('Modules');
            button.setAttribute('aria-label', __('Show module navigation'));
            button.addEventListener('click', () => {
                const current = document.querySelector('.body-sidebar-container .sidebar-collapse-arrow');
                if (document.body.classList.contains('sidebar-collapsed')) current?.click();
            });
            document.body.appendChild(button);
        }
        button.hidden = !collapsed;
        const route = document.body.dataset.route || '';
        const dockHasModules = [...document.querySelectorAll('#desk-dock .dock-items .dock-item')].some(visible);
        // Once per route, restore a menu whose only remaining rail is empty.
        // Subsequent deliberate collapse is allowed; the Modules button remains.
        if (collapsed && !dockHasModules && window.innerWidth >= 992 && !recovered.has(route)) {
            recovered.add(route);
            toggle.click();
        }
    }
    function schedule() {
        if (scheduled) return;
        scheduled = true;setTimeout(update, 200);
    }
    function start() {
        new MutationObserver(schedule).observe(document.body, {
            childList:true,subtree:true,attributes:true,attributeFilter:['class','data-route'],
        });
        window.addEventListener('resize', schedule);
        schedule();
    }
    if (document.body) start();else document.addEventListener('DOMContentLoaded', start, {once:true});
})();
