(() => {
    function restrictNavigation() {
        const screens = frappe.boot.bs_scoped_screens;
        if (!screens) {
            if (frappe.session.user === 'manikandan@bitssecureit.com') {
                document.querySelectorAll('.body-sidebar .sidebar-items, .desk-sidebar .sidebar-items').forEach(host => {
                    if (!host.querySelector('.bs-personal-dashboard')) {
                        const row = document.createElement('div');
                        row.className = 'standard-sidebar-item bs-personal-dashboard';
                        row.innerHTML = '<a class="item-anchor" href="/desk/my-work-dashboard">Dashboard</a>';
                        host.prepend(row);
                    }
                });
            }
            return;
        }
        document.querySelectorAll('.body-sidebar .sidebar-items, .desk-sidebar .sidebar-items').forEach(host => {
            Array.from(host.children).forEach(row => {
                if (!row.classList.contains('bs-scoped-navigation')) row.style.display = 'none';
            });
            if (host.querySelector('.bs-scoped-navigation')) return;
            const nav = document.createElement('div');
            nav.className = 'bs-scoped-navigation';
            const dashboard = document.createElement('div');
            dashboard.className = 'standard-sidebar-item';
            dashboard.innerHTML = '<a class="item-anchor" href="/desk/my-work-dashboard">Dashboard</a>';
            nav.append(dashboard);
            for (const screen of screens) {
                const row = document.createElement('div');
                row.className = 'standard-sidebar-item';
                const link = document.createElement('a');
                link.className = 'item-anchor';
                link.href = '/desk/bs-group/' + screen.toLowerCase().replaceAll(' ', '-');
                link.textContent = __(screen);
                row.append(link);
                nav.append(row);
            }
            host.append(nav);
        });
    }
    frappe.router.on('change', () => setTimeout(restrictNavigation, 100));
    $(document).on('page-change', restrictNavigation);
    new MutationObserver(restrictNavigation).observe(document.body, {childList: true, subtree: true});
    restrictNavigation();
})();
