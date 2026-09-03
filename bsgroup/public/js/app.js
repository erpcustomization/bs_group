(function () {
    const WORKSPACE_KEY = "bsgroup_active_workspace";

    // --- Persist workspace via prototype patch ---
    // Patch runs after desk.bundle.js defines frappe.ui.Sidebar but before
    // jQuery's $(document).ready microtask fires Frappe's startup/routing.
    if (frappe.ui && frappe.ui.Sidebar && frappe.ui.Sidebar.prototype) {
        const _origSetWorkspaceSidebar = frappe.ui.Sidebar.prototype.set_workspace_sidebar;
        frappe.ui.Sidebar.prototype.set_workspace_sidebar = function (router) {
            if (!this.sidebar_title) {
                const stored = localStorage.getItem(WORKSPACE_KEY);
                if (
                    stored &&
                    frappe.boot &&
                    frappe.boot.workspace_sidebar_item &&
                    frappe.boot.workspace_sidebar_item[stored.toLowerCase()]
                ) {
                    this.sidebar_title = stored;
                }
            }
            return _origSetWorkspaceSidebar.call(this, router);
        };

        const _origSetup = frappe.ui.Sidebar.prototype.setup;
        frappe.ui.Sidebar.prototype.setup = function (workspace_name) {
            const result = _origSetup.apply(this, arguments);
            if (this.sidebar_title) {
                localStorage.setItem(WORKSPACE_KEY, this.sidebar_title);
            }
            return result;
        };
    }

    // --- Show absolute date/time instead of relative "x ago" timestamps ---
    // comment_when() (core) renders every timestamp — sidebar "Created By" /
    // "Last Edited By", and the activity/comment timeline — as
    // <span class="frappe-timestamp" data-timestamp="...">. Swap the
    // rendered text for the raw timestamp instead of the relative text.
    function applyRawTimestamps() {
        $(".frappe-timestamp").each(function () {
            const raw = $(this).attr("data-timestamp");
            if (raw) {
                $(this).text(raw.split(".")[0]);
            }
        });
    }

    // Sidebar and timeline re-render on route change, on timeline
    // refresh (new comment/activity), and on frappe's own 60s
    // relative-time refresh — reapply after each.
    frappe.router.on("change", () => setTimeout(applyRawTimestamps, 300));
    $(document).on("form-refresh form-rename timeline_refresh", () =>
        setTimeout(applyRawTimestamps, 300)
    );
    setInterval(applyRawTimestamps, 60000);

    // --- Fallback via router event ---
    // In case the prototype patch missed the initial call, re-apply on every
    // route change: if sidebar landed on the wrong workspace and the stored
    // one is a valid alternative for this DocType, switch to it.
    frappe.router.on("change", function () {
        const sidebar = frappe.app && frappe.app.sidebar;
        if (!sidebar) return;

        const stored = localStorage.getItem(WORKSPACE_KEY);
        if (!stored) {
            // No stored preference — save whatever Frappe chose
            if (sidebar.sidebar_title) {
                localStorage.setItem(WORKSPACE_KEY, sidebar.sidebar_title);
            }
            return;
        }

        // Save the current workspace if it changed
        if (sidebar.sidebar_title) {
            localStorage.setItem(WORKSPACE_KEY, sidebar.sidebar_title);
            return;
        }

        // sidebar_title is empty — Frappe couldn't determine a workspace.
        // Check if the stored workspace contains this DocType and switch.
        const route = frappe.get_route ? frappe.get_route() : [];
        const doctype = route && route[1];
        if (!doctype) return;

        const sidebars = sidebar.get_workspace_sidebars
            ? sidebar.get_workspace_sidebars(doctype)
            : [];
        if (sidebars.includes(stored)) {
            sidebar.setup(stored);
        }
    });
})();
