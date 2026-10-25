/* Lead workflow and permission-aware customer brief.
 * Use standard Frappe field/section visibility. Never hide a section because
 * its parent tab is inactive. No global layout changes, timers, polling or AI calls.
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
        bsi_lead_focus.refresh(frm);
        bsi_customer_brief.refresh(frm);
        // Frappe rebuilds the generated Connections tab after refresh handlers.
        // Keep presentation scoped to this Lead form without altering its links.
        const root = frm.wrapper[0] || frm.wrapper;
        if (!root.querySelector('.bsi-lead-connections-visibility')) {
            const style = document.createElement('style');
            style.className = 'bsi-lead-connections-visibility';
            style.textContent = '#lead-dashboard_tab-tab, #lead-dashboard_tab { display:none !important; }';
            root.appendChild(style);
        }
    }
});

const bsi_customer_brief = (() => {
    const esc = value => frappe.utils.escape_html(String(value ?? ""));
    const labels = { rfq: "Quotation request", tender: "Tender", general_sales: "Sales enquiry", job_seeker: "Careers enquiry", support: "Support request", other: "Other", end_user: "End user", reseller_partner: "Reseller / partner", genuine_lead: "Genuine sales enquiry", needs_review: "Needs review", existing_lead: "Existing lead", duplicate_submission: "Duplicate submission" };
    const words = value => labels[value] || String(value || "Not available").replace(/_/g, " ");
    const text = value => value ? esc(value) : '<span class="text-muted">Not provided</span>';
    const route = (doctype, name, label) => '<a href="/desk/' + doctype + '/' +
        encodeURIComponent(name) + '">' + esc(label || name) + '</a>';
    const item = (label, value) => '<div style="min-width:0;overflow-wrap:anywhere">' +
        '<div class="text-muted small">' + esc(label) + '</div><div style="font-weight:500">' + value + '</div></div>';
    const group = items => '<div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,210px),1fr));gap:12px 20px;margin:14px 0">' + items.join("") + '</div>';
    const paragraph = (title, value) => '<div style="margin:14px 0"><strong>' + esc(title) +
        '</strong><div style="white-space:pre-wrap;overflow-wrap:anywhere;margin-top:4px">' + text(value) + '</div></div>';
    function safe_url(value) {
        try {
            const url = new URL(value);
            if (!["https:", "http:"].includes(url.protocol)) return text(value);
            return '<a href="' + esc(url.href) + '" target="_blank" rel="noopener noreferrer">' + esc(value) + '</a>';
        } catch (_) { return text(value); }
    }
    function responsibility(lead) {
        const inherited = lead.__onload?.bsi_sales_responsibility;
        if (inherited?.users?.length) {
            return {label: inherited.source === "Opportunity" ? "Assigned salesperson (Opportunity)" : "Assigned salesperson",
                value: inherited.users.map(u => u.full_name || u.user).join(", ")};
        }
        let assigned = lead._assign;
        try { assigned = typeof assigned === "string" ? JSON.parse(assigned) : assigned; } catch (_) { assigned = []; }
        assigned = Array.isArray(assigned) ? [...new Set(assigned.filter(u => typeof u === "string" && u.trim()))] : [];
        const names = assigned.map(user => typeof frappe.user?.full_name === "function" ? frappe.user.full_name(user) || user : user);
        if (names.length) return { label: "Assigned team", value: names.join(", ") };
        return { label: "Lead owner", value: lead.lead_owner || "Unassigned — assign a salesperson" };
    }
    function ai_result(doc) {
        try { return JSON.parse(doc.bsli_ai_result || "{}"); } catch (_) { return {}; }
    }
    function percent(value) {
        return value === null || value === undefined || value === "" ? "Not available" : esc(Number(value).toFixed(0)) + "%";
    }
    const disclosure = (title, body, open = false) => '<details style="margin-top:14px;border-top:1px solid var(--border-color);padding-top:12px"' + (open ? ' open' : '') + '><summary style="cursor:pointer;font-weight:600;padding:4px 0">' + esc(title) + '</summary>' + body + '</details>';
    const badge = (value, color) => '<span class="indicator-pill ' + color + '">' + esc(value) + '</span>';
    function header(doc, lead) {
        return '<div style="display:flex;flex-wrap:wrap;justify-content:space-between;gap:12px;align-items:start"><div><h4 style="margin:0 0 4px">Website enquiry</h4>' +
            '<div class="text-muted small">' + esc(doc.bsli_submission_ref || doc.name) + ' · ' + esc(frappe.datetime.str_to_user(doc.creation)) + '</div></div>' +
            route("lead-intake", doc.name, "Open enquiry / review").replace('<a ', '<a class="btn btn-sm btn-primary" ') + '</div>' + group([
                item("Organization", text(doc.organization_name || lead.company_name)),
                item("Contact", text(doc.full_name || lead.lead_name)),
                item("Email", text(doc.normalized_email || doc.email || lead.email_id)),
                item("Phone", text(doc.normalized_phone || doc.phone || lead.mobile_no))
            ]);
    }
    function ai_html(doc, lead = {}, expanded = true) {
        const ai = ai_result(doc);
        const completed = doc.ai_status === "Completed";
        const list = value => Array.isArray(value) && value.length ? value.join(", ") : null;
        const review = doc.bsli_review_state || "Not recorded";
        const awaiting = review === "Awaiting Review";
        const next = awaiting ? "Review the original enquiry and AI findings, then confirm or correct the outcome before following up." :
            (doc.bsli_human_outcome && ["spam", "job_seeker", "support", "duplicate_submission"].includes(doc.bsli_human_outcome) ?
                "Follow the recorded human review outcome; this enquiry is not an approved new sales requirement." : doc.ai_next_action ||
                (completed ? "Review the customer requirement and follow up through the normal sales workflow." : "Review the original enquiry; AI analysis is not complete."));
        const diagnostics = paragraph("AI reasoning", Array.isArray(ai.reasons) ? ai.reasons.join("\n") : null) +
            group([item("Risk flags", text(list(ai.risk_flags))), item("Country signals", text(list(ai.country_signals))),
                item("AI model", text(doc.bsli_ai_model)), item("Processed on", text(doc.ai_processed_on ? frappe.datetime.str_to_user(doc.ai_processed_on) : null))]) +
            paragraph("AI routing recommendation", [doc.bsli_proposed_outcome && words(doc.bsli_proposed_outcome), doc.bsli_decision_reason].filter(Boolean).join(" — ")) +
            (doc.bsli_human_outcome ? paragraph("Human review outcome", words(doc.bsli_human_outcome)) +
                group([item("Reviewed by", text(doc.bsli_reviewed_by)), item("Reviewed on", text(doc.bsli_reviewed_on ? frappe.datetime.str_to_user(doc.bsli_reviewed_on) : null))]) +
                paragraph("Review note", doc.bsli_review_note) : "") +
            '<p class="small text-muted">Confidence describes classification certainty; it is not a lead score or probability of winning. Unprovided customer facts are not inferred.</p>';
        const extracted = group([
            item("Products / services", text(list(ai.products_or_services))),
            item("Customer type (AI)", text(ai.customer_type && words(ai.customer_type))),
            item("Urgency (AI)", text(ai.urgency && words(ai.urgency))),
            item("Deadline mentioned", text(ai.deadline_mentioned)),
            item("Quantity / value mentioned", text(ai.estimated_value_hint)),
            item("Verdict", text(ai.verdict && words(ai.verdict)))
        ]);
        return '<div aria-label="AI processing and review status" style="display:flex;flex-wrap:wrap;gap:8px;margin:14px 0">' +
            badge("AI: " + (doc.ai_status || "Pending"), completed ? "green" : (doc.ai_status === "Failed" ? "red" : "gray")) +
            badge(words(doc.ai_intent), "blue") + badge("Confidence: " + (completed ? percent(doc.ai_confidence) : "Not available"), "gray") +
            badge(review, awaiting ? "orange" : "gray") + '</div>' +
            '<div style="background:var(--control-bg);border-radius:6px;padding:12px 16px;margin:12px 0">' + paragraph("Requirement at a glance · AI summary", doc.ai_summary) + '</div>' + '<div style="border-left:3px solid var(--primary);padding:4px 14px;margin:18px 0;background:var(--control-bg);border-radius:4px">' +
            paragraph("Next action", next) + '<p class="small"><strong>' + esc(responsibility(lead).label) + ': </strong>' + text(responsibility(lead).value) + '</p></div>' +
            disclosure("Products, urgency and extracted details", extracted, expanded) +
            disclosure("AI reasoning, routing and audit", diagnostics, expanded);
    }
    function enquiry_html(doc, lead) {
        return '<h5>Original customer enquiry</h5>' + group([
            item("Customer / contact", text(doc.full_name || lead.lead_name)),
            item("Organization", text(doc.organization_name || lead.company_name)),
            item("Email", text(doc.normalized_email || doc.email || lead.email_id)),
            item("Phone", text(doc.normalized_phone || doc.phone || lead.mobile_no)),
            item("Receiving company", text(lead.company)),
            item(responsibility(lead).label, text(responsibility(lead).value))
        ]) + paragraph("Enquiry type / subject", doc.subject) + paragraph("Customer message", doc.transcript) +
            group([item("Received on", text(frappe.datetime.str_to_user(doc.creation))),
                item("Website reference", text(doc.bsli_submission_ref)),
                item("Source page", safe_url(doc.source_url)),
                item("Source record", route("lead-intake", doc.name))]);
    }
    function focused_html(doc, lead) {
        const ai = ai_result(doc);
        let website = null;
        try { const url = new URL(doc.source_url); if (["https:", "http:"].includes(url.protocol)) website = url.hostname; } catch (_) {}
        const products = Array.isArray(ai.products_or_services) ? ai.products_or_services.join(", ") : null;
        return paragraph("Requirement", doc.transcript) + group([
            item("Product / service (extracted)", text(products)),
            item(responsibility(lead).label, text(responsibility(lead).value))
        ]) + paragraph("AI analysis result", doc.ai_summary || ai.summary) +
        '<section class="bsi-enquiry-details" aria-label="Enquiry details" style="margin-top:14px;border-top:1px solid var(--border-color);padding-top:12px"><h5>Enquiry details</h5>' + group([
            item("Enquiry ID", text(doc.bsli_submission_ref || doc.name)),
            item("Website", text(website)),
            item("Received on", text(doc.creation ? frappe.datetime.str_to_user(doc.creation) : null)),
            item("Landing page", safe_url(doc.source_url)),
            item("Receiving company", text(lead.company)),
            item("Country recorded on enquiry", text(doc.country)),
            item("AI classification", text(ai.verdict ? words(ai.verdict) : null)),
        
        ]) + paragraph("Review note", doc.bsli_review_note) + "</section>";
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
    function mount(frm, html, aiHtml = html) {
        const wrap = $(frm.wrapper);
        const panes = wrap.find('.tab-pane');
        const details = panes.first();
        let ai = wrap.find('#lead-custom_bsi_status_tab');
        if (!ai.length) ai = wrap.find('[data-fieldname="bsi_ai_section"]').closest('.tab-pane');
        [details, ai].forEach((pane, index) => {
            if (!pane.length) return;
            let box = pane.children('.bsi-customer-brief');
            if (!box.length) box = $('<section class="bsi-customer-brief" aria-label="Customer enquiry and AI brief" style="padding:20px;border:1px solid var(--border-color);border-radius:8px;margin:12px 0 20px;font-size:var(--text-base,14px);line-height:1.55"></section>').prependTo(pane);
            box.html(index === 0 ? html : aiHtml);
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
            await frappe.model.with_doctype("Lead Intake");
            const available = new Set(["name", "creation", ...frappe.get_meta("Lead Intake").fields.map(f => f.fieldname)]);
            const present = fields => fields.filter(f => available.has(f));
            const query = {
                method: "frappe.client.get_list",
                args: {
                    doctype: "Lead Intake",
                    filters: { external_system: "website-form" },
                    or_filters: [["converted_lead", "=", name], ["matched_lead", "=", name]],
                    fields: present(["name", "creation", "ai_intent", "subject", "status", "bsli_review_state", "converted_lead", "matched_lead"]),
                    order_by: "creation desc", limit_page_length: 20
                }
            };
            const detailFields = present(["name", "creation", "full_name", "organization_name", "email", "phone", "normalized_email", "normalized_phone",
                        "subject", "transcript", "source_url", "country", "converted_lead", "matched_lead", "status", "ai_status", "ai_intent", "ai_confidence",
                        "ai_summary", "ai_next_action", "ai_processed_on", "bsli_submission_ref", "bsli_ai_result", "bsli_ai_model",
                        "bsli_review_state", "bsli_proposed_outcome", "bsli_decision_reason", "bsli_human_outcome", "bsli_reviewed_by", "bsli_reviewed_on", "bsli_review_note"]);
            // Fetch the creating enquiry independently so later linked enquiries
            // cannot push it out of the bounded recent-history window.
            const originalQuery = { method: query.method, args: {
                ...query.args, filters: { external_system: "website-form", converted_lead: name },
                fields: detailFields, or_filters: undefined, order_by: "creation asc", limit_page_length: 1
            }};
            const [original, recent] = await Promise.all([frappe.call(originalQuery), frappe.call(query)]);
            if (frm.doc.name !== name || frm._bsi_brief_generation !== generation) return;
            const docs = [...(original.message || []), ...(recent.message || [])]
                .filter((d, i, all) => all.findIndex(x => x.name === d.name) === i);
            if (!docs.length) {
                mount(frm, '<p class="text-muted">No website enquiry is linked to this Lead.</p>');
                return;
            }
            let doc = primary(docs, name);
            if (!(original.message || []).length) {
                // Only one full enquiry is loaded. The history list never fetches
                // every customer's message or model JSON merely to show links.
                const detail = await frappe.call({ method: query.method, args: {
                    ...query.args, filters: { external_system: "website-form", name: doc.name }, fields: detailFields, limit_page_length: 1
                }});
                if (frm.doc.name !== name || frm._bsi_brief_generation !== generation) return;
                doc = (detail.message || [])[0];
                if (!doc) throw new Error("Linked enquiry not readable");
            }
            legacy_fields(frm, true);
            // Frappe loads active ToDos in docinfo, separately from the Lead document.
            const assignments = frm.get_docinfo?.()?.assignments;
            const lead = Array.isArray(assignments) ? { ...frm.doc, _assign: assignments.map(row => row.owner) } : frm.doc;
            const context = header(doc, lead);
            const source = disclosure("Original customer enquiry and source", enquiry_html(doc, lead));
            const history = related_html(docs, doc);
            mount(frm, paragraph("Requirement", doc.transcript),
                focused_html(doc, lead).replace(paragraph("Requirement", doc.transcript), "") + history +
                disclosure("AI analysis and routing", context + ai_html(doc, lead, true) + source));
        } catch (_) {
            if (frm.doc.name !== name || frm._bsi_brief_generation !== generation) return;
            mount(frm, '<h5>Customer enquiry and AI brief</h5><p role="alert">The linked enquiry could not be loaded. Refresh to retry. If this persists, ask your administrator to check your existing Lead Intake access.</p>');
        }
    }
    return { refresh, primary, safe_url, ai_html, enquiry_html, focused_html };
})();

// Two tabs, using the original controls and their existing save/permission handlers.
const bsi_lead_focus = (() => {
    const contact = new Set(["first_name", "last_name", "company_name", "email_id", "mobile_no", "phone", "whatsapp_no"]);
    function refresh(frm) {
        const root = frm.wrapper[0] || frm.wrapper;
        const tabs = frm.layout?.tabs || [];
        const detailsTab = tabs.find(t => t.df.fieldname === "__details") || tabs[0];
        const extraTab = tabs.find(t => t.df.fieldname === "custom_bsi_status_tab");
        if (!detailsTab || !extraTab) return;
        const details = detailsTab.wrapper[0], extra = extraTab.wrapper[0];
        extraTab.df.label = extraTab.label = "Additional details";
        extraTab.tab_link.find('.nav-link').text(__('Additional details'));
        function card(parent, cls, label) {
            let node = parent.querySelector('.' + cls);
            if (!node) {
                node = document.createElement('section'); node.className = 'form-section ' + cls;
                node.style.cssText = 'padding:16px 20px;border:1px solid var(--border-color);border-radius:8px;margin:12px 0';
                const title = document.createElement('h5'); title.textContent = __(label); node.append(title);
                const body = document.createElement('div'); body.className = 'section-body'; node.append(body); parent.append(node);
            }
            return node.querySelector('.section-body');
        }
        const customer = card(details, 'bsi-contact-card', 'Contact details');
        customer.style.cssText = 'display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,220px),1fr));gap:12px 24px';
        const follow = card(details, 'bsi-follow-card', 'Next follow-up date');
        const notes = card(details, 'bsi-notes-card', 'Notes');
        // Move whole native sections first, retaining section dependencies and controls.
        for (const tab of tabs) {
            if (tab === extraTab || tab.df.fieldname === 'dashboard_tab') continue;
            for (const section of Array.from(tab.wrapper[0].children)) {
                if (section.classList.contains('form-section') && !section.className.includes('bsi-')) extra.append(section);
            }
        }
        for (const [name, field] of Object.entries(frm.fields_dict)) {
            const node = field.$wrapper?.[0];
            if (!node || ['Section Break','Column Break','Tab Break'].includes(field.df.fieldtype)) continue;
            if (contact.has(name)) { customer.append(node); field.tab = detailsTab; }
            else if (name === 'open_activities_html') { follow.append(node); field.tab = detailsTab; }
            else if (['notes_html','notes'].includes(name)) { notes.append(node); field.tab = detailsTab; }
            else if (extra.contains(node)) field.tab = extraTab;
        }
        for (const tab of tabs) {
            tab.df.hidden = ![detailsTab, extraTab].includes(tab) ? 1 : 0;
            tab.refresh();
        }
        if (![detailsTab, extraTab].some(t => t.is_active())) detailsTab.set_active();
        // Reuse the native task/event dates; do not create a second follow-up record.
        let date = follow.querySelector('.bsi-next-follow-date');
        if (!date) { date = document.createElement('p'); date.className = 'bsi-next-follow-date text-muted'; follow.prepend(date); }
        date.textContent = __('Not scheduled');
        if (!frm.is_new()) {
            const name = frm.doc.name;
            frappe.call({method:'erpnext.crm.utils.get_open_activities',args:{ref_doctype:'Lead',ref_docname:name},callback(r) {
                if (frm.doc.name !== name || r.exc) return;
                const values = [...(r.message?.tasks || []).map(x => x.date), ...(r.message?.events || []).map(x => x.starts_on)].filter(Boolean).sort();
                date.textContent = values.length ? frappe.datetime.str_to_user(values[0]) : __('Not scheduled');
            }});
        }
    }
    return {refresh};
})();
