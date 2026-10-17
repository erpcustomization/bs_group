/* Lead workflow and permission-aware customer brief.
 * Use standard Frappe field/section visibility. Never hide a section because
 * its parent tab is inactive. No timers, polling, metadata mutation or AI calls.
 */
frappe.ui.form.on("Lead", {
    refresh(frm) {
        frm.page.remove_inner_button("Opportunity", "Create");
        frm.page.add_inner_button("Opportunity", function () {
            frappe.call({
                method: "erpnext.crm.doctype.lead.lead.make_opportunity",
                args: { source_name: frm.docname },
                freeze: true,
                callback(r) {
                    if (!r.exc && r.message) {
                        r.message.sales_stage = "Proposal";
                        r.message.custom_organization_name = frm.doc.company_name;
                        frappe.model.sync(r.message);
                        frappe.set_route("Form", r.message.doctype, r.message.name);
                    }
                }
            });
        }, "Create");
        bsi_customer_brief.refresh(frm);
    }
});

const bsi_customer_brief = (() => {
    const esc = value => frappe.utils.escape_html(String(value ?? ""));
    const words = value => String(value || "Not available").replace(/_/g, " ");
    const text = value => value ? esc(value) : '<span class="text-muted">Not provided</span>';
    const route = (doctype, name, label) => '<a href="/desk/' + doctype + '/' +
        encodeURIComponent(name) + '">' + esc(label || name) + '</a>';
    const item = (label, value) => '<div style="min-width:180px;flex:1;overflow-wrap:anywhere">' +
        '<div class="text-muted small">' + esc(label) + '</div><div>' + value + '</div></div>';
    const group = items => '<div style="display:flex;flex-wrap:wrap;gap:16px;margin:12px 0">' + items.join("") + '</div>';
    const paragraph = (title, value) => '<div style="margin:14px 0"><strong>' + esc(title) +
        '</strong><div style="white-space:pre-wrap;overflow-wrap:anywhere;margin-top:4px">' + text(value) + '</div></div>';
    function safe_url(value) {
        try {
            const url = new URL(value);
            if (!["https:", "http:"].includes(url.protocol)) return text(value);
            return '<a href="' + esc(url.href) + '" target="_blank" rel="noopener noreferrer">' + esc(value) + '</a>';
        } catch (_) { return text(value); }
    }
    function ai_result(doc) {
        try { return JSON.parse(doc.bsli_ai_result || "{}"); } catch (_) { return {}; }
    }
    function percent(value) {
        return value === null || value === undefined || value === "" ? "Not available" : esc(Number(value).toFixed(0)) + "%";
    }
    function ai_html(doc) {
        const ai = ai_result(doc);
        const completed = doc.ai_status === "Completed";
        const list = value => Array.isArray(value) && value.length ? value.join(", ") : null;
        const review = doc.bsli_review_state || "Not recorded";
        const awaiting = review === "Awaiting Review";
        return '<h5>AI analysis and sales handover</h5>' + group([
            item("AI processing", text(doc.ai_status || "Pending")),
            item("Classification", text(words(doc.ai_intent))),
            item("Classification confidence", completed ? percent(doc.ai_confidence) : "Not available"),
            item("Review", text(review))
        ]) + paragraph("AI summary", doc.ai_summary) + group([
            item("Products / services", text(list(ai.products_or_services))),
            item("Customer type (AI)", text(ai.customer_type && words(ai.customer_type))),
            item("Urgency (AI)", text(ai.urgency && words(ai.urgency))),
            item("Deadline mentioned", text(ai.deadline_mentioned)),
            item("Quantity / value mentioned", text(ai.estimated_value_hint)),
            item("Verdict", text(ai.verdict && words(ai.verdict)))
        ]) + paragraph("AI reasoning", Array.isArray(ai.reasons) ? ai.reasons.join("\n") : null) +
            group([item("Risk flags", text(list(ai.risk_flags))),
                item("Country signals", text(list(ai.country_signals))),
                item("AI model", text(doc.bsli_ai_model)),
                item("Processed on", text(doc.ai_processed_on ? frappe.datetime.str_to_user(doc.ai_processed_on) : null))]) +
            paragraph("AI routing recommendation", [doc.bsli_proposed_outcome && words(doc.bsli_proposed_outcome), doc.bsli_decision_reason].filter(Boolean).join(" — ")) +
            (doc.bsli_human_outcome ? paragraph("Human review outcome", words(doc.bsli_human_outcome)) +
                group([item("Reviewed by", text(doc.bsli_reviewed_by)), item("Reviewed on", text(doc.bsli_reviewed_on ? frappe.datetime.str_to_user(doc.bsli_reviewed_on) : null))]) +
                paragraph("Review note", doc.bsli_review_note) : "") +
            paragraph("Next action", awaiting ? "Review the original enquiry and AI findings, then confirm or correct the outcome in Lead Intake before following up." :
                (doc.bsli_human_outcome && ["spam", "job_seeker", "support", "duplicate_submission"].includes(doc.bsli_human_outcome) ?
                    "Follow the recorded human review outcome; this enquiry is not an approved new sales requirement." : doc.ai_next_action || (completed ? "Review the customer requirement and follow up through the normal sales workflow." : "Review the original enquiry; AI analysis is not complete."))) +
            '<p class="small text-muted">Confidence describes classification certainty; it is not a lead score or probability of winning. Unprovided customer facts are not inferred.</p>' +
            '<p>' + route("lead-intake", doc.name, "Open full enquiry and review controls") + '</p>';
    }
    function enquiry_html(doc, lead) {
        return '<h5>Original customer enquiry</h5>' + group([
            item("Customer / contact", text(doc.full_name || lead.lead_name)),
            item("Organization", text(doc.organization_name || lead.company_name)),
            item("Email", text(doc.normalized_email || doc.email || lead.email_id)),
            item("Phone", text(doc.normalized_phone || doc.phone || lead.mobile_no)),
            item("Receiving company", text(lead.company)),
            item("Lead owner", text(lead.lead_owner || "Unassigned — assign a salesperson"))
        ]) + paragraph("Enquiry type / subject", doc.subject) + paragraph("Customer message", doc.transcript) +
            group([item("Received on", text(frappe.datetime.str_to_user(doc.creation))),
                item("Website reference", text(doc.bsli_submission_ref)),
                item("Source page", safe_url(doc.source_url)),
                item("Source record", route("lead-intake", doc.name))]);
    }
    function primary(docs, name) {
        // A later support/job enquiry matched to this person must not overwrite the
        // sales enquiry that actually created the Lead.
        return docs.find(d => d.converted_lead === name) || docs[0];
    }
    function related_html(docs, selected) {
        const others = docs.filter(d => d.name !== selected.name);
        if (!others.length) return "";
        return '<details style="margin-top:16px"><summary>Recent linked enquiries (' + others.length + ')</summary>' +
            others.map(d => '<p>' + route("lead-intake", d.name) + ' · ' + esc(words(d.ai_intent || d.subject)) +
                ' · ' + esc(d.status || "") + ' · ' + esc(d.bsli_review_state || "") + '</p>').join("") +
            '<p class="small text-muted">Each enquiry retains its own classification and review. Up to 20 recent linked records are shown. Other linked enquiries do not replace the sales brief above.</p></details>';
    }
    function mount(frm, html) {
        const wrap = $(frm.wrapper);
        const panes = wrap.find('.tab-pane');
        const details = panes.first();
        let ai = wrap.find('#lead-bsi_ai_tab');
        if (!ai.length) ai = wrap.find('[data-fieldname="bsi_ai_section"]').closest('.tab-pane');
        [details, ai].forEach(pane => {
            if (!pane.length) return;
            let box = pane.children('.bsi-customer-brief');
            if (!box.length) box = $('<section class="bsi-customer-brief" aria-label="Customer enquiry and AI brief" style="padding:20px;border:1px solid var(--border-color);border-radius:8px;margin:12px 0 20px"></section>').prependTo(pane);
            box.html(html);
        });
    }
    function legacy_fields(frm, website) {
        // The authoritative website analysis is in the brief. Pilot review is
        // separate from model confidence; never show an uncalculated score as 0.
        if (!website) return;
        const fields = ["bsi_ai_status", "bsi_ai_score"];
        if (!frm.doc.bsi_rfq_value_estimate) fields.push("bsi_rfq_value_estimate");
        frm._bsi_legacy_visibility = {};
        fields.forEach(name => {
            const field = frm.fields_dict[name];
            if (!field) return;
            frm._bsi_legacy_visibility[name] = !field.df.hidden;
            frm.toggle_display(name, false);
        });
        // Keep native summary/confidence fields and their Section Breaks intact:
        // Frappe hides an entire tab if every native section is marked hidden.
    }
    async function refresh(frm) {
        const generation = (frm._bsi_brief_generation || 0) + 1;
        frm._bsi_brief_generation = generation;
        Object.entries(frm._bsi_legacy_visibility || {}).forEach(([name, visible]) => {
            if (frm.fields_dict[name]) frm.toggle_display(name, visible);
        });
        frm._bsi_legacy_visibility = null;
        if (frm.is_new()) {
            $(frm.wrapper).find('.bsi-customer-brief').remove();
            return;
        }
        const name = frm.doc.name;
        mount(frm, '<h5>Customer enquiry and AI brief</h5><p role="status">Loading saved enquiry and analysis…</p>');
        try {
            const query = {
                method: "frappe.client.get_list",
                args: {
                    doctype: "Lead Intake",
                    filters: { external_system: "website-form" },
                    or_filters: [["converted_lead", "=", name], ["matched_lead", "=", name]],
                    fields: ["name", "creation", "full_name", "organization_name", "email", "phone", "normalized_email", "normalized_phone",
                        "subject", "transcript", "source_url", "converted_lead", "matched_lead", "status", "ai_status", "ai_intent", "ai_confidence",
                        "ai_summary", "ai_next_action", "ai_processed_on", "bsli_submission_ref", "bsli_ai_result", "bsli_ai_model",
                        "bsli_review_state", "bsli_proposed_outcome", "bsli_decision_reason", "bsli_human_outcome", "bsli_reviewed_by", "bsli_reviewed_on", "bsli_review_note"],
                    order_by: "creation desc", limit_page_length: 20
                }
            };
            // Fetch the creating enquiry independently so later linked enquiries
            // cannot push it out of the bounded recent-history window.
            const originalQuery = { method: query.method, args: {
                ...query.args, filters: { external_system: "website-form", converted_lead: name },
                or_filters: undefined, order_by: "creation asc", limit_page_length: 1
            }};
            const [original, recent] = await Promise.all([frappe.call(originalQuery), frappe.call(query)]);
            if (frm.doc.name !== name || frm._bsi_brief_generation !== generation) return;
            const docs = [...(original.message || []), ...(recent.message || [])]
                .filter((d, i, all) => all.findIndex(x => x.name === d.name) === i);
            if (!docs.length) {
                mount(frm, '<h5>Customer enquiry and AI brief</h5><p>No website enquiry is linked to this Lead. Existing Lead details and any other source analysis remain below.</p>');
                return;
            }
            const doc = primary(docs, name);
            legacy_fields(frm, true);
            mount(frm, enquiry_html(doc, frm.doc) + '<hr>' + ai_html(doc) + related_html(docs, doc));
        } catch (_) {
            if (frm.doc.name !== name || frm._bsi_brief_generation !== generation) return;
            mount(frm, '<h5>Customer enquiry and AI brief</h5><p role="alert">The linked enquiry could not be loaded. Refresh to retry. If this persists, ask your administrator to check your existing Lead Intake access.</p>');
        }
    }
    return { refresh, primary, safe_url, ai_html, enquiry_html };
})();
