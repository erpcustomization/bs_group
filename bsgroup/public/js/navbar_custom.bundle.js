// Company Badge — Frappe v16 desk.
// Shows the Bits Secure logo with the current company in its tooltip.
// No switching logic — display only.

(function () {
    'use strict';

    var _companyData = null;
    var _observer    = null;

    /* ── 1. Fetch company info once on toolbar_setup ─────────────────────── */
    $(document).on('toolbar_setup', function () {
        var bodyEl = document.getElementById('body');
        if (bodyEl && !_observer) {
            _observer = new MutationObserver(function () { if (_companyData) _tryMount(); });
            _observer.observe(bodyEl, { childList: true });
        }
        frappe.call({
            method: 'bsgroup.utils.company_access.user_details',
            callback: function (r) {
                if (!r.message || !r.message.length) return;
                var items = Array.isArray(r.message) ? r.message : [r.message];

                // pick the default company
                var defaultCompany = (
                    frappe.boot && frappe.boot.user &&
                    frappe.boot.user.defaults && frappe.boot.user.defaults.company
                ) || '';

                _companyData = items[0];
                for (var i = 0; i < items.length; i++) {
                    if (items[i].name === defaultCompany) { _companyData = items[i]; break; }
                }
                _tryMount();
            }
        });
    });

    /* ── 2. Re-mount on every SPA navigation ────────────────────────────── */
    $(document).on('page-change', function () {
        if (_companyData) _tryMount();
    });

    /* ── 3. Find .page-head-content of the active page ──────────────────── */
    function _getHeadContent() {
        try {
            var pg = frappe.container && frappe.container.page;
            if (pg) {
                var el = $(pg).find('.page-head-content').get(0);
                if (el) return el;
            }
        } catch (_) {}
        var nodes = document.querySelectorAll('.page-head-content');
        for (var i = 0; i < nodes.length; i++) {
            if (nodes[i].offsetParent !== null) return nodes[i];
        }
        return null;
    }

    function _tryMount() {
        var content = _getHeadContent();
        if (!content || content.querySelector('.bs-co-badge')) return;
        _buildBadge(_companyData, content);
    }

    /* Display branding only; company access and switching remain unchanged. */
    function _buildBadge(item, content) {
        var wrapper = document.createElement('div');
        wrapper.className = 'bs-co-badge';
        wrapper.title = item.name || 'Bits Secure IT Infrastructure';
        wrapper.style.cssText = 'display:inline-flex;align-items:center;justify-content:center;flex-shrink:0;padding:0 8px;';

        var logo = document.createElement('img');
        logo.src = '/assets/bsgroup/img/logo.png';
        logo.alt = 'Bits Secure IT Infrastructure';
        logo.width = 126;
        logo.height = 44;
        logo.style.cssText = 'display:block;width:126px;height:44px;object-fit:contain;background:transparent;';
        logo.draggable = false;
        wrapper.appendChild(logo);

        var stdSection = content.querySelector('.standard-items-section');
        content.insertBefore(wrapper, stdSection || null);
    }

})();
