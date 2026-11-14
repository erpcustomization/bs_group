// Presentation only. Keep native controls, permissions and document events intact.
(() => {
    if (window.bsCommercialStudioInstalled) return;
    window.bsCommercialStudioInstalled = true;

    function render(frm) {
        const root = $(frm.page.wrapper);
        root.addClass('bs-commercial-studio');
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
