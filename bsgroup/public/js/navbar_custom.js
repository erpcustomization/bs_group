// Company Badge — Frappe v16 desk.
// Shows the current user's default company as a static read-only pill.
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

    /* ── 4. Build static pill ───────────────────────────────────────────── */
    function _buildBadge(item, content) {
        var abbr = (item.abbr || '').trim();
        var name = item.name || '';

        var wrapper = document.createElement('div');
        wrapper.className = 'bs-co-badge';
        wrapper.style.cssText = 'display:inline-flex;align-items:center;flex-shrink:0;';

        var pill = document.createElement('span');
        pill.title = name;
        pill.style.setProperty('display',         'inline-flex', 'important');
        pill.style.setProperty('align-items',     'center',      'important');
        pill.style.setProperty('padding',         '8px 14px',    'important');
        pill.style.setProperty('border-radius',   '999px',       'important');
        pill.style.setProperty('background',      '#00AFC1',     'important');
        pill.style.setProperty('color',           '#fff',        'important');
        pill.style.setProperty('font-size',       '12px',        'important');
        pill.style.setProperty('font-weight',     '700',         'important');
        pill.style.setProperty('letter-spacing',  '.04em',       'important');
        pill.style.setProperty('white-space',     'nowrap',      'important');
        pill.style.setProperty('box-shadow',      '0 1px 4px rgba(0,0,0,.2)', 'important');
        pill.style.setProperty('line-height',     '1',           'important');
        pill.style.setProperty('user-select',     'none',        'important');

        pill.textContent = 'Bits Secure' + (abbr ? ' - ' + abbr : '');

        wrapper.appendChild(pill);

        var stdSection = content.querySelector('.standard-items-section');
        content.insertBefore(wrapper, stdSection || null);
    }

})();
