// These records are started from their linked sales workflow, not the list.
(() => {
    if (!document.getElementById('bsi-linked-list-actions')) {
        const style = document.createElement('style');
        style.id = 'bsi-linked-list-actions';
        style.textContent = `
            body:is([data-route="List/Presales Request/List"],[data-route="List/Deal Cost Sheet/List"],[data-route="List/Quotation/List"]) .page-actions .primary-action,
            body:is([data-route="List/Presales Request/List"],[data-route="List/Deal Cost Sheet/List"],[data-route="List/Quotation/List"]) .btn-new-doc { display: none !important; }
        `;
        document.head.appendChild(style);
    }
    for (const doctype of ['Presales Request', 'Deal Cost Sheet', 'Quotation']) {
        const settings = frappe.listview_settings[doctype] ||= {};
        if (settings.bsi_linked_creation_only) continue;
        settings.bsi_linked_creation_only = true;
        for (const event of ['onload', 'refresh']) {
            const previous = settings[event];
            settings[event] = function (listview) {
                listview.can_create = false;
                const result = previous?.apply(this, arguments);
                listview.page.clear_primary_action();
                listview.$no_result?.find('.btn-new-doc').hide();
                return result;
            };
        }
    }
})();
