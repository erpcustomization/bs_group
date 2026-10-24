// Presentation only: retain the native list, controls and event handlers.
(() => {
    const doctypes = new Set([
        "Lead", "Opportunity", "Presales Request", "Deal Cost Sheet",
        "Quotation", "Sales Target GP Entry",
    ]);
    const pages = new Set([
        "sales-management-das", "presales-request-das", "monthly-sales-entry",
    ]);
    const mounted = new Map();
    let pending = false;

    function restoreLists(activePage) {
        for (const [page, state] of mounted) {
            if (page === activePage) continue;
            if (state.origin.parentNode) state.origin.replaceWith(state.actions);
            state.heading.remove();
            page.classList.remove("bs-list-shell");
            mounted.delete(page);
        }
    }

    function layoutList() {
        const route = document.body.dataset.route || "";
        const [view, name, mode] = route.split("/");
        const enabled = view === "List" && doctypes.has(name) && mode === "List";
        const page = enabled ? document.getElementById(`page-${route}`) : null;
        restoreLists(page);
        if (!page || mounted.has(page)) return;
        const main = page.querySelector(".layout-main-section");
        const actions = page.querySelector(".page-head .page-actions");
        if (!main || !actions || !main.querySelector(".list-page-form")) return;

        const heading = document.createElement("header");
        heading.className = "bs-list-heading";
        const title = document.createElement("h1");
        title.textContent = name === "Sales Target GP Entry" ? "Sales Target Entry" : name;
        heading.appendChild(title);
        const origin = document.createComment("BS list actions original position");
        actions.before(origin);
        // Move the original controls; copying them would lose Frappe's handlers.
        heading.appendChild(actions);
        main.prepend(heading);
        page.classList.add("bs-list-shell");
        mounted.set(page, { heading, actions, origin });
    }

    function scheduleLayout() {
        if (pending) return;
        pending = true;
        requestAnimationFrame(() => { pending = false; layoutList(); });
    }
    function syncTheme() {
        const [view, name] = (document.body.dataset.route || "").split("/");
        const selected = ((view === "List" || view === "Form") && doctypes.has(name))
            || pages.has(view)
            || (view === "query-report" && name === "Opportunity Summary Report");
        document.body.classList.toggle("bs-sales-ui", selected);
        scheduleLayout();
    }
    function start() {
        syncTheme();
        new MutationObserver(syncTheme).observe(document.body, {
            attributes: true, attributeFilter: ["data-route"],
        });
        // Lists arrive asynchronously and can be cached by Desk on navigation.
        new MutationObserver(scheduleLayout).observe(document.body, {
            childList: true, subtree: true,
        });
    }
    if (document.body) start();
    else document.addEventListener("DOMContentLoaded", start, { once: true });
})();
