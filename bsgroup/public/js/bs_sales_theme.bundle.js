// Presentation scope only. Never intercept routes or document events.
(() => {
    const doctypes = new Set([
        "Lead", "Opportunity", "Presales Request", "Deal Cost Sheet",
        "Quotation", "Sales Target GP Entry",
    ]);
    const pages = new Set([
        "sales-management-das", "presales-request-das", "monthly-sales-entry",
    ]);
    function syncTheme() {
        const [view, name] = (document.body.dataset.route || "").split("/");
        const selected = ((view === "List" || view === "Form") && doctypes.has(name))
            || pages.has(view)
            || (view === "query-report" && name === "Opportunity Summary Report");
        document.body.classList.toggle("bs-sales-ui", selected);
    }
    function start() {
        syncTheme();
        new MutationObserver(syncTheme).observe(document.body, {
            attributes: true, attributeFilter: ["data-route"],
        });
    }
    if (document.body) start();
    else document.addEventListener("DOMContentLoaded", start, { once: true });
})();
