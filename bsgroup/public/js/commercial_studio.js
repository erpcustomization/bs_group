// Presentation only. Keep native controls, permissions and document events intact.
(() => {
    if (window.bsCommercialStudioInstalled) return;
    window.bsCommercialStudioInstalled = true;

    function hideRoutineBanners(root) {
        root.find('.form-message').each(function () {
            const text = this.textContent.replace(/\s+/g, ' ').trim();
            const routine = /^Quotation Status:/.test(text)
                || text.startsWith('Save changes, then use Convert to PDF.')
                || text.startsWith('Use Revise BOQ to edit costing. The linked Draft Quotation updates automatically')
                || (!!this.querySelector('.dcs-compact') && /Next:\s/.test(text));
            this.classList.toggle('bs-commercial-routine-banner', routine);
        });
    }

    function render(frm) {
        const root = $(frm.page.wrapper);
        root.addClass('bs-commercial-studio');
        // Async workflow callbacks can recreate these messages after refresh.
        // Keep validation, duplicate-link and approval-routing error banners visible.
        hideRoutineBanners(root);
        if (!root[0].bsCommercialBannerObserver) {
            const observer = new MutationObserver(() => hideRoutineBanners(root));
            observer.observe(root[0], { childList: true, subtree: true, characterData: true });
            root[0].bsCommercialBannerObserver = observer;
        }
        const form = root.find('.form-page').first();
        if (!form.length) return;
        let hero = form.children('.bs-commercial-hero');
        if (!hero.length) {
            hero = $('<header class="bs-commercial-hero"><div class="bs-commercial-heading"><div class="bs-commercial-eyebrow"></div><h2></h2><p></p></div><div class="bs-commercial-document"><span>DOCUMENT STATUS</span><strong></strong><small></small></div></header>');
            form.prepend(hero);
        }
        const quote = frm.doctype === 'Quotation';
        hero.find('.bs-commercial-eyebrow').text(quote ? 'SALES / COMMERCIAL OFFER' : 'SALES / DEAL COSTING');
        hero.find('h2').text(quote ? __('Quotation') : __('Deal Cost Sheet'));
        hero.find('p').text(frm.is_new() ? __('New document') : frm.doc.name);
        hero.find('strong').text(frm.is_dirty() ? __('Unsaved changes') :
            frm.doc.docstatus === 2 ? __('Cancelled') :
            frm.doc.docstatus === 1 ? __('Submitted') : __('Draft'));
        hero.find('small').text(quote ? __('Prepare. Refine. Present.') : __('Scope. Cost. Approve.'));
    }
    for (const doctype of ['Quotation', 'Deal Cost Sheet']) {
        frappe.ui.form.on(doctype, { refresh: render });
    }
})();
