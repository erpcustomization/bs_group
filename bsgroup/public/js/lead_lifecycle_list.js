// Preserve native list actions and links; replace only the visible lifecycle indicator.
(() => {
    const settings = frappe.listview_settings.Lead || (frappe.listview_settings.Lead = {});
    settings.add_fields = [...new Set([...(settings.add_fields || []), "status", "creation"])];
    const active = ["Lead", "Open", "Replied", "Interested", "Delayed"];
    const closed = ["Opportunity", "Quotation", "Converted", "Lost Quotation"];
    const nativeOnload = settings.onload;
    settings.onload = function(listview) {
        nativeOnload?.call(this, listview);
        const field = listview.page.fields_dict.status;
        if (field) {
            field.df.options = "\nOpen\nDelayed\nOpportunity\nDropped";
            field.refresh();
        }
    };
    settings.get_indicator = doc => {
        if (closed.includes(doc.status)) return [__(doc.status === "Opportunity" ? "Opportunity · Closed" : "Closed"), "green", "status,=," + doc.status];
        if (["Dropped", "Do Not Contact"].includes(doc.status)) return [__("Dropped"), "red", "status,=," + doc.status];
        const age = doc.creation ? moment().diff(frappe.datetime.convert_to_user_tz(doc.creation, false), 'hours', true) : 0;
        return doc.status === "Delayed" || (active.includes(doc.status) && age >= 24)
            ? [__("Delayed"), "orange", "status,=,Delayed"] : [__("Open"), "blue", "status,=," + doc.status];
    };
})();
