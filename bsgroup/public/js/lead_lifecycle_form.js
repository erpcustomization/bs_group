// Three user decisions; Delayed and Closed are derived outcomes, never manual choices.
const bsi_lead_lifecycle = (() => {
    const active = new Set(["Lead", "Open", "Replied", "Interested", "Delayed"]);
    const closed = new Set(["Opportunity", "Quotation", "Converted", "Lost Quotation"]);
    function display(doc) {
        if (closed.has(doc.status)) return [doc.status === "Opportunity" ? "Opportunity · Closed" : "Closed", "green"];
        if (["Dropped", "Do Not Contact"].includes(doc.status)) return ["Dropped", "red"];
        const age = doc.creation ? moment().diff(frappe.datetime.convert_to_user_tz(doc.creation, false), 'hours', true) : 0;
        return doc.status === "Delayed" || (active.has(doc.status) && age >= 24) ? ["Delayed", "orange"] : ["Open", "blue"];
    }
    async function convert(frm) {
        if (frm.is_new() || frm.is_dirty()) {
            frappe.msgprint(__("Save the Lead before converting it to an Opportunity."));
            return;
        }
        return frappe.call({
            method: "bsgroup.lead_lifecycle.make_opportunity", args: {source_name: frm.doc.name}, freeze: true,
            callback(r) {
                if (!r.exc && r.message) {
                    r.message.sales_stage = "Proposal";
                    r.message.custom_organization_name = frm.doc.company_name;
                    frappe.model.sync(r.message);
                    frappe.set_route("Form", r.message.doctype, r.message.name);
                }
            }
        });
    }
    let timer;
    function refresh(frm) {
        // Activation follows the server schema update; old benches remain usable during deployment.
        const statusField = frm.fields_dict.status;
        if (!statusField || !(statusField.df.options || "").includes("Dropped")) return;
        frm.set_df_property("status", "hidden", 1);
        let box = frm.wrapper.querySelector?.('.bsi-lead-outcome') || frm.wrapper[0]?.querySelector('.bsi-lead-outcome');
        if (!box) {
            box = document.createElement('div'); box.className = 'bsi-lead-outcome';
            const host = frm.fields_dict.custom_bsi_status_controls?.$wrapper?.[0];
            if (host) host.append(box); else statusField.$wrapper[0].after(box);
        }
        box.replaceChildren();
        const label = document.createElement('label'); label.className = 'control-label'; label.textContent = __('Status'); box.append(label);
        const badge = document.createElement('div'); badge.style.marginBottom = '6px'; box.append(badge);
        const render = () => {
            const [text, color] = display(frm.doc);
            badge.innerHTML = '<span class="indicator-pill ' + color + '">' + frappe.utils.escape_html(__(text)) + '</span>';
            frm.page.set_indicator(__(text), color);
        };
        render();
        clearInterval(timer);
        timer = setInterval(() => {
            if (document.body.dataset.route === 'Form/Lead/' + frm.doc.name) render();
        }, 60000);

        const select = document.createElement('select'); select.className = 'form-control'; select.setAttribute('aria-label', 'Status');
        for (const [value, text] of [['open','Open'],['convert','Opportunity'],['drop','Dropped']]) {
            const option = document.createElement('option'); option.value = value; option.textContent = __(text); select.append(option);
        }
        const selected = closed.has(frm.doc.status) ? 'convert' : ['Dropped','Do Not Contact'].includes(frm.doc.status) ? 'drop' : 'open';
        select.value = selected;
        select.disabled = !frm.perm?.some(p => p.write) || closed.has(frm.doc.status);
        if (closed.has(frm.doc.status)) select.title = __('This Lead is closed through its existing sales document.');
        box.append(select);
        select.addEventListener('change', async () => {
            const action = select.value; select.value = selected;
            if (action === 'convert') return convert(frm);
            if (action === 'open') {
                await frm.set_value('status', 'Open');
                await frm.save();
            } else if (action === 'drop') {
                frappe.prompt([{fieldname:'reason',fieldtype:'Small Text',label:__('Reason for dropping'),reqd:1}], async values => {
                    const reason = (values.reason || '').trim();
                    if (!reason) return frappe.msgprint(__('Enter a reason before dropping this Lead.'));
                    frm.add_child('notes', {note: frappe.utils.escape_html('Dropped: ' + reason), added_by: frappe.session.user, added_on: frappe.datetime.now_datetime()});
                    await frm.set_value('status', 'Dropped');
                    await frm.save();
                }, __('Drop Lead'), __('Save as Dropped'));
            }
        });
    }
    return {refresh, convert, display};
})();

frappe.ui.form.on("Lead", {refresh(frm) {
    bsi_lead_lifecycle.refresh(frm);
    frm.page.remove_inner_button("Opportunity", "Create");
    if (!frm.is_new() && frm.perm?.some(p => p.write) && !["Opportunity", "Quotation", "Converted", "Lost Quotation", "Dropped", "Do Not Contact"].includes(frm.doc.status)) {
        frm.page.add_inner_button("Opportunity", () => bsi_lead_lifecycle.convert(frm), "Create");
    }
}});
