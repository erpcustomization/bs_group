/* Correct existing app tiles, without creating or granting access to modules. */
(() => {
    const routes = frappe.boot?.bs_app_destinations;
    if (!routes || window.top !== window.self) return;
    let scheduled = false;
    function update() {
        scheduled = false;
        document.querySelectorAll('a.desktop-icon[data-id]').forEach(tile => {
            const name = tile.dataset.id;
            if (!Object.prototype.hasOwnProperty.call(routes, name)) return;
            const route = routes[name];
            tile.hidden = !route;
            if (route && tile.getAttribute('href') !== route) tile.setAttribute('href', route);
        });
    }
    // Native workspace tiles otherwise resolve their shared app to its first
    // sidebar item (Lead). Follow our permission-checked destination instead.
    document.addEventListener('click', event => {
        const tile = event.target.closest?.('a.desktop-icon[data-id]');
        if (!tile || !Object.prototype.hasOwnProperty.call(routes, tile.dataset.id)) return;
        if (event.target.closest('.hide-button')) return;
        const route = routes[tile.dataset.id];
        if (!route) { event.preventDefault(); event.stopImmediatePropagation(); return; }
        if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey || event.button) return;
        event.preventDefault(); event.stopImmediatePropagation();
        window.location.assign(route);
    }, true);
    function schedule() { if (!scheduled) { scheduled = true; setTimeout(update, 0); } }
    new MutationObserver(schedule).observe(document.body, {childList:true, subtree:true});
    frappe.router.on('change', schedule);
    update();
})();
