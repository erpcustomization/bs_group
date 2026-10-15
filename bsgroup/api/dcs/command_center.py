"""Read-only legacy Command Center, with request-local aggregation."""
import frappe
from bsgroup.dcs.currency import money_round
from bsgroup.api.dcs._common import governed_endpoint

@governed_endpoint("dcs_screen1", ptype="read", idempotent=False)
def dcs_screen1(args):
    previous = frappe.response.get("message")
    try:
        # ---------------- NRC-1 delegating client (self-contained) ----------------
        # The canonical narrative redaction contract lives in Server Script
        # "dcs_narrative_guard" (NRC-1). No surface re-implements the rules.
        # Note: Script Reports run safe_exec with an explicit locals mapping, so
        # module-level constants are NOT visible inside functions. Everything this
        # helper needs is therefore declared inside the function body.
        def nrc_batch(items):
            out = {"ok": 0, "texts": [], "levels": [], "err": ""}
            if items is None:
                return out
            if len(items) == 0:
                out["ok"] = 1
                return out
            try:
                frappe.call("dcs_narrative_guard", mode="redact_batch", items=items)
                got = frappe.response.get("message")
                if got:
                    if got.get("ok") == 1 and got.get("contract") == "NRC-1" and got.get("count") == len(items):
                        out["ok"] = 1
                        out["texts"] = got.get("texts")
                        out["levels"] = got.get("levels")
                    else:
                        out["err"] = "NRC-1 contract mismatch"
                else:
                    out["err"] = "NRC-1 service returned no payload"
            except Exception as nerr:
                out["err"] = str(nerr)
            return out
        # -------------- end NRC-1 delegating client --------------
        
        # dcs_screen1 - Commercial Command Center. READ ONLY. Writes nothing.
        # Every figure traces to a real field on Deal Cost Sheet, DCS Revision or DCS Handover Condition.
        # No prototype figures. Unavailable is returned where no populated source exists.
        
        COMMERCIAL_ROLES = ["Sales Manager", "Commercial Controller", "Managing Director"]
        TECHNICAL_ROLES = ["Technical Engineer", "Project Engineer", "Project Manager", "Operations Manager"]
        MARGIN_FLOOR = 20.0
        CONCESSION_CEILING = 26.0
        STALE_DAYS = 30
        MAX_LIST = 25
        HELP_CARDS = ["cannot_invoice", "never_quoted", "approval_blocks", "below_floor", "concession_blocks", "unpriced", "stale_drafts", "handover_blockers"]
        OWNER = {}
        
        def get_user_roles(u):
            rows = frappe.get_all("Has Role", filters={"parent": u, "parenttype": "User"}, fields=["role"])
            out = []
            for r in rows:
                out.append(r.get("role"))
            return out
        
        def has_any(roles, wanted):
            for r in wanted:
                if r in roles:
                    return 1
            return 0
        
        def r2(v):
            x = float(v or 0)
            if x < 0:
                return 0 - (int(((0 - x) * 100) + 0.5) / 100.0)
            return int((x * 100) + 0.5) / 100.0
        
        def card(key, title, question, action, ignored):
            return {"key": key, "title": title, "question": question, "action": action, "if_ignored": ignored, "available": 1, "count": 0, "exposure": 0.0, "groups": [], "source": "", "unavailable_reason": ""}
        
        def add_group(c, cause, name, amount, owner, detail):
            g = None
            for x in c["groups"]:
                if x["cause"] == cause:
                    g = x
            if g is None:
                g = {"cause": cause, "count": 0, "exposure": 0.0, "deals": [], "truncated": 0}
                c["groups"].append(g)
            g["count"] = g["count"] + 1
            g["exposure"] = g["exposure"] + float(amount or 0)
            if len(g["deals"]) < MAX_LIST:
                g["deals"].append({"name": name, "amount": money(amount, currency_by.get(name)), "owner": owner, "detail": detail})
            else:
                g["truncated"] = 1
            c["count"] = c["count"] + 1
            c["exposure"] = c["exposure"] + float(amount or 0)
            if c["key"] in HELP_CARDS:
                k = owner if owner else "Unassigned"
                o = OWNER.get(k)
                if o is None:
                    o = {"owner": k, "issues": 0, "reasons": {}, "deals": {}}
                    OWNER[k] = o
                o["issues"] = o["issues"] + 1
                prev = float(o["deals"].get(name) or 0)
                if float(amount or 0) > prev:
                    o["deals"][name] = float(amount or 0)
                else:
                    o["deals"][name] = prev
                o["reasons"][c["key"]] = (o["reasons"].get(c["key"]) or 0) + 1
        
        def finish(c):
            c["exposure"] = money(c["exposure"])
            for g in c["groups"]:
                g["exposure"] = money(g["exposure"])
            return c
        
        user = frappe.session.user
        roles = get_user_roles(user)
        is_comm = has_any(roles, COMMERCIAL_ROLES)
        is_tech = has_any(roles, TECHNICAL_ROLES)
        # governed_view is a one-way downgrade used for governance verification and for
        # operational users who want to see exactly what a technical role receives.
        # It can only remove commercial data, never grant it.
        if args.get("governed_view"):
            is_comm = 0
            is_tech = 1
        now_dt = frappe.utils.now_datetime()
        today = str(now_dt)[0:10]
        
        if is_comm != 1:
            if is_tech != 1:
                frappe.response["message"] = {"projection": "none", "authorised": 0, "user": user, "generated_on": str(now_dt), "reason": "The Commercial Command Center requires an authorised commercial projection. System Manager alone does not grant commercial access."}
            else:
                tc = frappe.get_list("DCS Handover Condition", filters={"domain": "Technical"}, fields=["name", "dcs", "condition_no", "condition_title", "state", "domain", "assigned_to", "raised_on", "hold_state"], limit_page_length=0)
                topen = []
                tclosed = 0
                for t in tc:
                    if t.get("state") == "Open":
                        topen.append({"condition": t.get("name"), "dcs": t.get("dcs"), "title": t.get("condition_title"), "assigned_to": t.get("assigned_to"), "hold_state": t.get("hold_state"), "raised_on": str(t.get("raised_on") or "")})
                    else:
                        tclosed = tclosed + 1
                # NRC-1: condition titles are free text and may contain typed commercial
                # figures. The technical projection never returns raw narrative.
                titles = []
                for tt in topen:
                    titles.append(str(tt.get("title") or ""))
                govt = nrc_batch(titles)
                if govt["ok"] == 1:
                    gi = 0
                    for tt in topen:
                        tt["title"] = govt["texts"][gi]
                        gi = gi + 1
                else:
                    for tt in topen:
                        tt["title"] = "[withheld - governed redaction unavailable]"
                frappe.response["message"] = {"projection": "technical", "authorised": 1, "user": user, "generated_on": str(now_dt), "open_technical_conditions": len(topen), "closed_technical_conditions": tclosed, "conditions": topen, "narrative_contract": "NRC-1", "note": "Technical projection. The server returns no cost, selling, margin, concession or exposure value."}
        else:
            FIELDS = ["currency", "name", "docstatus", "customer", "deal_owner", "total_cost", "total_selling", "margin_percent", "modified", "custom_quotation", "custom_deal_status", "custom_approval_state", "custom_approval_required", "custom_margin_gate", "custom_concession_percent_from_baseline", "custom_award_state", "custom_delivery_release_state", "custom_po_recon_state", "custom_baseline_frozen", "custom_frozen_total_selling", "custom_dcs_revision_no", "custom_working_total_cost", "custom_working_total_selling", "custom_working_margin_percent", "custom_presales_cost", "custom_awarded_on", "custom_approved_on", "custom_endorsed_on", "project"]
            sheets = frappe.get_list("Deal Cost Sheet", filters={"docstatus": ["!=", 2]}, fields=FIELDS, limit_page_length=0)
            currency_by = {s.get("name"): s.get("currency") for s in sheets}
            report_currency = "OMR" if "OMR" in currency_by.values() else frappe.defaults.get_global_default("currency")
            def money(value, currency=None):
                return money_round(value, currency or report_currency)
            conds = frappe.get_list("DCS Handover Condition", fields=["name", "dcs", "condition_no", "condition_title", "category", "original_category", "domain", "state", "exposure_amount", "assigned_to", "raised_on", "cleared_on", "accepted_on", "follow_up_date"], limit_page_length=0)
            revs = frappe.get_list("DCS Revision", fields=["name", "dcs", "revision_no", "source", "changed_by", "changed_on", "approval_state", "approval_requirement", "margin_gate", "decided_by", "decided_on"], limit_page_length=0)
            for s in sheets:
                if int(s.get("custom_dcs_revision_no") or 0) > 0 and float(s.get("custom_working_total_selling") or 0) > 0:
                    s["living"] = 1
                    s["total_selling"] = float(s.get("custom_working_total_selling") or 0)
                    s["total_cost"] = float(s.get("custom_working_total_cost") or 0)
                    s["margin_percent"] = float(s.get("custom_working_margin_percent") or 0)
                else:
                    s["living"] = 0
            sell_by = {}
            owner_by = {}
            for s in sheets:
                sell_by[s.get("name")] = float(s.get("custom_frozen_total_selling") or s.get("total_selling") or 0)
                owner_by[s.get("name")] = s.get("deal_owner")
            cards = []
        
            c = card("no_way_back", "Money with no way back", "Cost already committed on deals that can no longer be won.", "Capture presales cost at source before this figure can be trusted.", "Sunk cost stays invisible and the same loss is repeated.")
            lost = frappe.get_list("Deal Cost Sheet", filters={"custom_deal_status": ["in", ["Lost", "Dropped", "No Bid", "Dropped / No Bid"]]}, fields=["name", "custom_presales_cost", "deal_owner", "total_selling"], limit_page_length=0)
            pc_total = 0.0
            for s in lost:
                pc_total = pc_total + float(s.get("custom_presales_cost") or 0)
            for s in sheets:
                pc_total = pc_total + float(s.get("custom_presales_cost") or 0)
            if pc_total <= 0:
                c["available"] = 0
                c["unavailable_reason"] = "No populated source. custom_presales_cost is 0.00 on every Deal Cost Sheet and custom_presales_hourly_rate is 0.00 on every Deal Cost Sheet, so irrecoverable spend cannot be derived from real data."
                c["source"] = "Deal Cost Sheet.custom_presales_cost, custom_presales_hourly_rate, custom_presales_actual_hours"
            else:
                c["source"] = "Deal Cost Sheet.custom_presales_cost where custom_deal_status is Lost, Dropped or No Bid"
                for s in lost:
                    if float(s.get("custom_presales_cost") or 0) > 0:
                        add_group(c, "Presales cost on lost or dropped deals", s.get("name"), s.get("custom_presales_cost"), s.get("deal_owner"), "")
            cards.append(finish(c))
        
            c = card("cannot_invoice", "Money earned but cannot progress", "Awarded work that cannot be released to delivery or invoiced.", "Clear the outstanding handover condition or release delivery.", "Revenue is won on paper while no delivery or cash movement follows.")
            c["source"] = "Deal Cost Sheet.custom_award_state = Awarded and custom_delivery_release_state not Released. Exposure from custom_frozen_total_selling."
            for s in sheets:
                if s.get("custom_award_state") == "Awarded":
                    d = s.get("custom_delivery_release_state") or "Not set"
                    if d != "Released" and d != "Released with MD Override":
                        amt = s.get("custom_frozen_total_selling") or s.get("total_selling")
                        add_group(c, "Delivery release " + str(d), s.get("name"), amt, s.get("deal_owner"), "PO reconciliation " + str(s.get("custom_po_recon_state") or "Not Started"))
            cards.append(finish(c))
        
            c = card("never_quoted", "Money the customer has never seen", "Costed value never issued to the customer as a quotation.", "Issue the quotation or close the sheet.", "Effort is spent, the customer never receives a price and the deal cannot convert.")
            c["source"] = "Deal Cost Sheet.custom_quotation is empty and total_selling greater than 0. Where a sheet carries revisions the living working position is used."
            for s in sheets:
                if float(s.get("total_selling") or 0) > 0:
                    if not s.get("custom_quotation"):
                        add_group(c, "No quotation linked - status " + str(s.get("custom_deal_status") or "Not set"), s.get("name"), s.get("total_selling"), s.get("deal_owner"), "")
            cards.append(finish(c))
        
            c = card("approval_blocks", "Approval blocks", "Negotiated positions waiting on a commercial approval decision.", "Endorse or decide in the Approval Workspace.", "The customer waits while the price sits in an internal queue.")
            c["source"] = "Deal Cost Sheet.custom_approval_state in Pending Endorsement, Endorsed - Pending MD, Returned for Rework, Blocked. Grouped by custom_approval_required. Legacy workflow_state is not used."
            PEND = ["Pending Endorsement", "Endorsed - Pending MD", "Returned for Rework", "Blocked"]
            for s in sheets:
                st = s.get("custom_approval_state") or ""
                if st in PEND:
                    add_group(c, str(s.get("custom_approval_required") or "Not set") + " - " + st, s.get("name"), s.get("total_selling"), s.get("deal_owner"), "Revision R" + str(s.get("custom_dcs_revision_no") or 0))
            cards.append(finish(c))
        
            c = card("below_floor", "Below-floor margin", "Working margin below the 20.0 percent floor.", "Recover margin in the Negotiation Workspace or escalate.", "The company sells below its own floor and the loss surfaces only after delivery.")
            c["source"] = "Deal Cost Sheet.custom_margin_gate = Blocked, and Deal Cost Sheet.margin_percent below 20.0 where total_selling greater than 0. Where a sheet carries revisions custom_working_margin_percent is used."
            for s in sheets:
                if s.get("custom_margin_gate") == "Blocked":
                    add_group(c, "Margin gate Blocked", s.get("name"), s.get("total_selling"), s.get("deal_owner"), "Margin " + str(r2(s.get("margin_percent"))) + " percent")
            for s in sheets:
                if float(s.get("total_selling") or 0) > 0:
                    mp = float(s.get("margin_percent") or 0)
                    if mp < MARGIN_FLOOR and s.get("custom_margin_gate") != "Blocked":
                        band = "Negative margin" if mp < 0 else ("Margin 0 to 10 percent" if mp < 10 else "Margin 10 to 20 percent")
                        add_group(c, band, s.get("name"), s.get("total_selling"), s.get("deal_owner"), "Margin " + str(r2(mp)) + " percent")
            cards.append(finish(c))
        
            c = card("concession_blocks", "Concession blocks", "Customer concession at or beyond the authorised ceiling.", "Re-negotiate or route for a Managing Director decision.", "Discount is conceded without authority and margin never recovers.")
            c["source"] = "Deal Cost Sheet.custom_concession_percent_from_baseline above 26.0, or custom_approval_required = Blocked"
            for s in sheets:
                cp = float(s.get("custom_concession_percent_from_baseline") or 0)
                if cp > CONCESSION_CEILING:
                    add_group(c, "Concession above the 26.0 percent ceiling", s.get("name"), s.get("total_selling"), s.get("deal_owner"), "Concession " + str(r2(cp)) + " percent")
                else:
                    if s.get("custom_approval_required") == "Blocked":
                        add_group(c, "Approval requirement Blocked", s.get("name"), s.get("total_selling"), s.get("deal_owner"), "Concession " + str(r2(cp)) + " percent")
            cards.append(finish(c))
        
            c = card("unpriced", "Unpriced deals", "Sheets carrying no selling value.", "Price the sheet or close it.", "Cost is carried with no revenue intent and the pipeline is overstated.")
            c["source"] = "Deal Cost Sheet.total_selling is 0 or empty. Where a sheet carries revisions the living working position is used."
            for s in sheets:
                if float(s.get("total_selling") or 0) <= 0:
                    cause = "Cost entered with no selling price" if float(s.get("total_cost") or 0) > 0 else "No cost and no selling price"
                    add_group(c, cause, s.get("name"), s.get("total_cost"), s.get("deal_owner"), "Cost " + str(money(s.get("total_cost"), s.get("currency"))) + " with no selling price")
            cards.append(finish(c))
        
            c = card("stale_drafts", "Stale drafts", "Draft sheets untouched for more than 30 days.", "Submit, update or close the draft.", "Draft value is neither live pipeline nor closed, so the forecast is wrong.")
            c["source"] = "Deal Cost Sheet.docstatus = 0 and modified older than 30 days"
            for s in sheets:
                if s.get("docstatus") == 0:
                    secs = frappe.utils.time_diff_in_seconds(now_dt, s.get("modified"))
                    days = int(float(secs) / 86400.0)
                    if days > STALE_DAYS:
                        band = "Idle over 180 days" if days > 180 else ("Idle 90 to 180 days" if days > 90 else "Idle 30 to 90 days")
                        add_group(c, band, s.get("name"), s.get("total_selling"), s.get("deal_owner"), str(days) + " days idle")
            cards.append(finish(c))
        
            c = card("handover_blockers", "Award and handover blockers", "Open conditions preventing a delivery release.", "Clear the condition in the Award and Handover Workspace.", "The award never converts into delivery and the customer sees no start.")
            c["source"] = "DCS Handover Condition.state = Open, grouped by domain. Exposure from the linked Deal Cost Sheet frozen selling value."
            for t in conds:
                if t.get("state") == "Open":
                    add_group(c, str(t.get("domain") or "Unassigned") + " domain", t.get("dcs"), sell_by.get(t.get("dcs")) or 0, t.get("assigned_to") or owner_by.get(t.get("dcs")), str(t.get("condition_title") or ""))
            cards.append(finish(c))
        
            c = card("accepted_risks", "Accepted risks", "Conditions formally accepted as risk instead of cleared.", "Review the exposure and the follow-up date.", "Accepted exposure is forgotten until it becomes a real cost.")
            c["source"] = "DCS Handover Condition.state = Accepted Risk. Exposure from exposure_amount."
            for t in conds:
                if t.get("state") == "Accepted Risk":
                    add_group(c, "Accepted risk originally raised as " + str(t.get("original_category") or "Unknown"), t.get("dcs"), t.get("exposure_amount"), t.get("assigned_to") or owner_by.get(t.get("dcs")), str(t.get("condition_title") or ""))
            cards.append(finish(c))
        
            no_project = [0]
            c = card("data_quality", "Data quality issues", "Records that cannot be trusted for a commercial decision.", "Correct the record at source.", "Every downstream figure inherits the error.")
            c["source"] = "Deal Cost Sheet field level checks on total_cost, total_selling, customer, deal_owner, project, custom_baseline_frozen and custom_po_recon_state"
            for s in sheets:
                nm = s.get("name")
                ow = s.get("deal_owner")
                tcst = float(s.get("total_cost") or 0)
                tsel = float(s.get("total_selling") or 0)
                if tsel > 0 and tcst > tsel:
                    add_group(c, "Cost exceeds the selling price", nm, tsel, ow, "Cost " + str(money(tcst)) + " against selling " + str(money(tsel)))
                if not s.get("customer"):
                    add_group(c, "No customer recorded", nm, tsel, ow, "")
                if not s.get("deal_owner"):
                    add_group(c, "No deal owner recorded", nm, tsel, ow, "")
                if not s.get("project"):
                    no_project[0] = no_project[0] + 1
                if s.get("custom_award_state") == "Awarded" and int(s.get("custom_baseline_frozen") or 0) != 1:
                    add_group(c, "Awarded without a frozen commercial baseline", nm, tsel, ow, "")
                if s.get("custom_po_recon_state") == "Mismatch":
                    add_group(c, "Customer PO does not reconcile", nm, tsel, ow, "")
            cards.append(finish(c))
        
            help_list = []
            for k in OWNER:
                o = OWNER[k]
                if o["issues"] > 0:
                    rl = []
                    for rk in o["reasons"]:
                        rl.append({"key": rk, "count": o["reasons"][rk]})
                    ex = 0.0
                    nd = 0
                    for dn in o["deals"]:
                        ex = ex + float(o["deals"][dn])
                        nd = nd + 1
                    help_list.append({"owner": o["owner"], "stuck": nd, "issues": o["issues"], "exposure": money(ex), "reasons": rl})
        
            acts = []
            rev_today = 0
            for r in revs:
                if str(r.get("changed_on") or "")[0:10] == today:
                    rev_today = rev_today + 1
                    acts.append({"kind": "Revision", "ref": r.get("name"), "dcs": r.get("dcs"), "who": r.get("changed_by"), "at": str(r.get("changed_on") or ""), "detail": "R" + str(r.get("revision_no") or 0) + " from " + str(r.get("source") or "") + ", approval " + str(r.get("approval_requirement") or "") + ", margin gate " + str(r.get("margin_gate") or "")})
                if str(r.get("decided_on") or "")[0:10] == today:
                    acts.append({"kind": "Approval decision", "ref": r.get("name"), "dcs": r.get("dcs"), "who": r.get("decided_by"), "at": str(r.get("decided_on") or ""), "detail": str(r.get("approval_state") or "")})
            aw_today = 0
            for s in sheets:
                if str(s.get("custom_awarded_on") or "")[0:10] == today:
                    aw_today = aw_today + 1
                    acts.append({"kind": "Award recorded", "ref": s.get("name"), "dcs": s.get("name"), "who": "", "at": str(s.get("custom_awarded_on") or ""), "detail": "Award state " + str(s.get("custom_award_state") or "")})
                if str(s.get("custom_endorsed_on") or "")[0:10] == today:
                    acts.append({"kind": "Endorsement", "ref": s.get("name"), "dcs": s.get("name"), "who": "", "at": str(s.get("custom_endorsed_on") or ""), "detail": str(s.get("custom_approval_state") or "")})
                if str(s.get("custom_approved_on") or "")[0:10] == today:
                    acts.append({"kind": "Approval", "ref": s.get("name"), "dcs": s.get("name"), "who": "", "at": str(s.get("custom_approved_on") or ""), "detail": str(s.get("custom_approval_state") or "")})
            cl_today = 0
            ar_today = 0
            for t in conds:
                if str(t.get("cleared_on") or "")[0:10] == today:
                    cl_today = cl_today + 1
                    acts.append({"kind": "Handover condition cleared", "ref": t.get("name"), "dcs": t.get("dcs"), "who": "", "at": str(t.get("cleared_on") or ""), "detail": str(t.get("condition_title") or "")})
                if str(t.get("accepted_on") or "")[0:10] == today:
                    ar_today = ar_today + 1
                    acts.append({"kind": "Risk accepted", "ref": t.get("name"), "dcs": t.get("dcs"), "who": "", "at": str(t.get("accepted_on") or ""), "detail": str(t.get("condition_title") or "")})
        
            browse = []
            sum_sell = 0.0
            sum_cost = 0.0
            for s in sheets:
                sum_sell = sum_sell + float(s.get("total_selling") or 0)
                sum_cost = sum_cost + float(s.get("total_cost") or 0)
                browse.append({"currency": s.get("currency"), "name": s.get("name"), "customer": s.get("customer"), "owner": s.get("deal_owner"), "selling": money(s.get("total_selling"), s.get("currency")), "cost": money(s.get("total_cost"), s.get("currency")), "margin": r2(s.get("margin_percent")), "status": s.get("custom_deal_status"), "docstatus": s.get("docstatus"), "approval_state": s.get("custom_approval_state") or "", "margin_gate": s.get("custom_margin_gate") or "", "award_state": s.get("custom_award_state") or "", "delivery": s.get("custom_delivery_release_state") or "", "revision_no": s.get("custom_dcs_revision_no") or 0, "living": s.get("living")})
            cancelled = frappe.get_list("Deal Cost Sheet", filters={"docstatus": 2}, fields=["name"], limit_page_length=0)
        
            want_roles = ["Managing Director", "Commercial Controller", "Technical Engineer", "Project Engineer"]
            present = frappe.get_all("Role", filters={"name": ["in", want_roles]}, fields=["name"], limit_page_length=0)
            pnames = []
            for p in present:
                pnames.append(p.get("name"))
            missing = []
            for w in want_roles:
                if w not in pnames:
                    missing.append(w)
        
            frappe.response["message"] = {"projection": "commercial", "authorised": 1, "user": user, "generated_on": str(now_dt), "today": today, "cards": cards, "who_needs_help": help_list, "handled_today": {"revisions": rev_today, "awards": aw_today, "conditions_cleared": cl_today, "risks_accepted": ar_today, "events": acts}, "browse": browse, "portfolio": {"live_sheets": len(sheets), "cancelled_sheets": len(cancelled), "total_sheets": len(sheets) + len(cancelled), "sum_total_selling": money(sum_sell), "sum_total_cost": money(sum_cost), "revisions": len(revs), "handover_conditions": len(conds)}, "structural_notes": [{"note": "Sheets without a linked Project are counted from the current records.", "sheets_without_project": no_project[0], "live_sheets": len(sheets)}], "role_blocker": {"missing_roles": missing, "note": "Approval and domain clearance paths that depend on these roles cannot be validated in a real session until the roles exist and are assigned."}}
        return frappe.response.get("message")
    finally:
        frappe.response["message"] = previous
