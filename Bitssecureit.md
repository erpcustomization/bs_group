# BS Group — Frappe Custom App Documentation

> **App:** bsgroup | **Version:** 0.0.1 | **Publisher:** Tridots Tech | **License:** MIT  
> **Stack:** Frappe 16.10.10 · ERPNext 16.21.1 · HRMS 16.4.4 · CRM 2.0.0-dev · Helpdesk 1.21.3  
> **Last analysed:** 2026-06-22

---

## Table of Contents

1. [App Overview](#1-app-overview)
2. [Custom DocTypes](#2-custom-doctypes)
3. [Hooks Configuration](#3-hooks-configuration)
4. [Permission System](#4-permission-system)
5. [Overrides & Monkey Patches](#5-overrides--monkey-patches)
6. [Utility Modules](#6-utility-modules)
7. [Client-Side Customisations (JS)](#7-client-side-customisations-js)
8. [Print Templates](#8-print-templates)
9. [Reports](#9-reports)
10. [Custom Pages / Dashboards](#10-custom-pages--dashboards)
11. [Workspaces](#11-workspaces)
12. [Scheduler Events](#12-scheduler-events)
13. [Fixtures & Data Sync](#13-fixtures--data-sync)
14. [Custom Fields on Standard DocTypes](#14-custom-fields-on-standard-doctypes)
15. [Key Business Logic Summary](#15-key-business-logic-summary)

---

## 1. App Overview

The **bsgroup** app is a Frappe custom application built for **Bits Secure IT Infrastructure LLC** (UAE). It extends ERPNext/Frappe with:

- Sales pipeline management (Opportunity → Presales → Deal Cost Sheet → Quotation)
- Presales request lifecycle and qualification scoring
- Deal costing with product/service GP calculation
- Labor planning and attendance tracking
- Cheque request approval workflow
- Help desk email threading and duplicate ticket consolidation
- PDF generation with wkhtmltopdf integration
- Custom dashboards for Sales and Presales

---

## 2. Custom DocTypes

All custom doctypes live in `bsgroup/bs_group/doctype/`.

### 2.1 Labor & Staffing

| DocType | Auto-name | Submittable | Purpose |
|---|---|---|---|
| **Labour Name** | by field | No | Worker registry (name, type, skill, rate) |
| **Labor Preapproval** | — | Yes | Pre-approve labor allocation per project/task |
| **Labor Attendance** | LAT-.YYYY.-.##### | Yes | Check-in/out with geolocation + photo proof |
| **Labor Line Item** | — (child) | — | Skill/cost breakdown rows for Labor Preapproval |

**Labor Attendance fields:** labour (Link), project, task, check_in_time, check_out_time, total_hours, site_location, latitude, photo, labor_preapproval, validation_status, remarks.

---

### 2.2 Project & Execution

| DocType | Purpose |
|---|---|
| **Execution Category** | Tree-structured project scope phases (Building/Service/Product/Phase/Other) |
| **Project Latest Update Log** | Child table — status update history on Project |
| **Sales Update Log** | Child table — sales activity log on Opportunity |
| **Opportunity Stage History** | Child table — tracks stage transitions on Opportunity |

---

### 2.3 Deal Costing

#### Deal Cost Sheet
- **Auto-name:** DCS-{customer}-.###
- **Submittable:** Yes, with amendment support
- **Controller:** `bsgroup/bs_group/doctype/deal_cost_sheet/deal_cost_sheet.py`
- **Key fields:** opportunity, presales_request, customer, company, territory, deal_owner, items (child table), resources (child table), document_upload, solution_responsibility_matrix, solutions, responsibilities
- **Financial summary:** products_cost_total, services_cost_total, total_cost, margin_value, margin_percent

**Controller methods:**

| Method | Description |
|---|---|
| `autoname()` | Generate name from customer name |
| `before_save()` | Calculate financial totals |
| `before_submit()` | Validate opportunity and items |
| `make_quotation()` | Create Quotation from this sheet |
| `read_deal_cost_sheet()` | Import items from CSV/Excel file |
| `calculate_deal_financials()` | Calculate cost, margin, GP separately for products vs. services |

**Permissions:** System Manager (full) · Sales Manager (full) · Sales User (create/write) · Project Manager (read)

#### Deal Cost Item *(child)*
Fields: item_code, item_name, brand, customer_item_name, exclude_item_name_and_brand, qty, cost_rate, cost_amount, selling_rate, selling_amount, gp_value, gp_percent, item_category, description, header, currency

#### Deal Cost Resource *(child)*
Fields: resource_type (Internal/Outsourced), role, no_of_persons, no_of_days, hours, cost_rate, cost_amount, linked_project, remarks, currency

#### Solution Responsibility Template
Fields: solution_type, responsibilities (child table of activities with our_responsibility / customer_responsibility columns)

---

### 2.4 Presales

#### Presales Request
- **Auto-name:** PR-{customer}-.###
- **Submittable:** Yes
- **Controller:** `bsgroup/bs_group/doctype/presales_request/presales_request.py`

**Qualification fields (each = 20 pts):** decision_maker_known, competition_known, budget_confirmed, timeline_defined, site_visit_required → `quality_score` (0–100), `quality_band` (Low/Medium/High)

**Status values (14):** Draft · Open · Assigned · In Progress · Awaiting Sales Input · Awaiting Customer Input · Costing in Progress · Ready for Quotation · Submitted to Sales · Completed · On Hold · Won · Lost · Cancelled

**Controller methods:**

| Method | Description |
|---|---|
| `autoname()` | Name from customer |
| `before_save()` | Calculate quality_score |
| `after_insert()` | Set linked Opportunity status to "Presales Request" |
| `calculate_due_date()` (scheduler) | Update overdue flag and delay_days daily |

---

### 2.5 Help Desk & Finance

| DocType | Auto-name | Purpose |
|---|---|---|
| **Cheque Request** | CR-.YYYY.-.MM.-.##### | Multi-stage cheque approval (pre-approval → preparation → signing → issue) |
| **Partner Email Source** | — | Regex rules for partner ITSM ticket threading into HD Ticket |
| **Office** | by field | Simple office location registry |

**Cheque Request workflow stages:** pre_approval → cheque_preparation → signing → issue_tracking

---

## 3. Hooks Configuration

**File:** `bsgroup/hooks.py`

### Assets
```python
app_include_js = [
    "/assets/bsgroup/js/app.js",
    "/assets/bsgroup/js/navbar_custom.js",
    "/assets/bsgroup/js/bs_welcome_banner.js",
]
app_include_css = [
    "/assets/bsgroup/css/sidebar.css",
    "/assets/bsgroup/css/bs_welcome_banner.css",
]
```

### DocType-specific JS
```python
doctype_js = {
    "Item":        "public/js/item.js",
    "Lead":        "public/js/Lead.js",
    "Opportunity": "public/js/opportunity.js",
    "Quotation":   "public/js/quotation.js",
    "Project":     "public/js/project.js",
    "Task":        "public/js/task.js",
    "Timesheet":   "public/js/timesheet.js",
}
```

### DocType Class Override
```python
override_doctype_class = {
    "Timesheet": "bsgroup.overrides.timesheet.CustomTimesheet",
}
```

### Whitelisted Method Override
```python
override_whitelisted_methods = {
    "erpnext.crm.doctype.opportunity.opportunity.make_quotation":
        "bsgroup.utils.quotation.make_quotation",
}
```

### Document Events
```python
doc_events = {
    "HD Ticket": {
        "after_insert": "bsgroup.utils.hd_ticket.thread_email_to_existing_ticket",
    },
    "Opportunity": {
        "before_insert": "bsgroup.utils.opportunity.set_opportunity_owner",
        "before_save": [
            "bsgroup.utils.opportunity.set_stage_history",
            "bsgroup.utils.opportunity.set_stage_updates",
            "bsgroup.utils.opportunity.set_last_updates",
        ],
        "autoname": "bsgroup.utils.doctype_naming.opportunity_autoname",
    },
    "Communication": {
        "before_insert": "bsgroup.utils.communication.hd_partner_email_threading",
    },
}
```

### Request Hook
```python
before_request = ["bsgroup.utils.email_threading.apply_patches"]
```

### Permission Query Conditions
```python
permission_query_conditions = {
    "Lead":             "bsgroup.permissions.get_common_conditions",
    "Opportunity":      "bsgroup.permissions.get_common_conditions",
    "Presales Request": "bsgroup.permissions.get_common_conditions",
    "Deal Cost Sheet":  "bsgroup.permissions.get_deal_cost_sheet_query_conditions",
    "Quotation":        "bsgroup.permissions.get_common_conditions",
    "*":                "bsgroup.utils.company_access.global_company_condition",
}
```

---

## 4. Permission System

**File:** `bsgroup/permissions.py`

### `get_common_conditions(user, doctype)`
Applies to: Lead · Opportunity · Presales Request · Quotation

| Role | Visible Records |
|---|---|
| System Manager | All |
| Sales Manager | Own + direct reports (via Employee.reports_to chain) |
| Sales User | Own only |

> For Opportunity, matches on `opportunity_owner` field instead of `owner`.

### `get_deal_cost_sheet_query_conditions(user)`

| Role | Visible Records |
|---|---|
| System Manager | All |
| Projects Manager | Submitted (docstatus = 1) only |
| Sales Manager | Submitted where owner = user OR deal_owner = user; plus all drafts owned by user |
| Sales User / Others | Own records OR deal_owner = user AND submitted |

### `get_reporting_team_users(user)`
Walks `Employee.reports_to` chain to build a team member list for Sales Manager visibility.

---

## 5. Overrides & Monkey Patches

### 5.1 Timesheet Override
**File:** `bsgroup/overrides/timesheet.py`  
**Class:** `CustomTimesheet` (extends ERPNext Timesheet)

| Method | Change |
|---|---|
| `validate_time_logs()` | Disables time-overlap restriction |
| `update_task_and_project()` | Sets task status to "Completed" only when ALL time logs for that task are completed |

### 5.2 `round_floats_in` Compatibility Patch
**File:** `bsgroup/__init__.py`

Monkey-patches `frappe.model.document.Document.round_floats_in()` to accept the `do_not_round_fields` keyword argument. Required for ERPNext 16.21.1 compatibility with Frappe 16.10.10.

### 5.3 Email Threading Patches
**File:** `bsgroup/utils/email_threading.py`  
Applied on every request via `before_request` hook.

**5-layer parent communication strategy:**
1. Exact `In-Reply-To` → `Communication.message_id`
2. `In-Reply-To` → `EmailQueue.communication`
3. `In-Reply-To` parsed as Communication name directly
4. Any Message-ID in `References` header (RFC 2822 fallback)
5. Extract document/ticket ID from subject line (pattern: `[#ACC-JV-2026-001]`)

Also patches `EmailQueue.build_message` to inject RFC 2822 `References` header, walking the `Communication.in_reply_to` chain.

---

## 6. Utility Modules

**Directory:** `bsgroup/utils/`

### `opportunity.py`
| Function | Description |
|---|---|
| `set_opportunity_owner` | Set opportunity_owner to current user if not set (before_insert) |
| `set_stage_history` | Track stage transitions — set to_date on previous entry, append new entry with changed_by |
| `update_stage_age` | Calculate days since last stage change → custom_stage_age_days |
| `set_stage_updates` | Append to custom_sales_updates when next_action/date changes |
| `set_last_updates` | Copy old next_action to last_sales_update on changes |
| `update_overdue_followup_for_all` | Daily scheduler — update custom_overdue_followup for all opportunities |

### `hd_ticket.py`
| Function | Description |
|---|---|
| `thread_email_to_existing_ticket` | After-insert: detect duplicate ticket (same subject + sender + open), move communications to original, enqueue deletion |
| `delete_duplicate_ticket` | Enqueued job — delete duplicate after transaction commits |
| `_clean_subject` | Strip Re:/Fwd: prefixes and `[#...]` ticket references |
| `_find_original_ticket` | Find existing open ticket with matching cleaned subject |

### `quotation.py`
`make_quotation(source_name, target_doc=None)` — Override of `Opportunity.make_quotation()` to copy `custom_contact_person_name` and `custom_organization_name` to the new Quotation.

### `doctype_naming.py`
`opportunity_autoname(doc, method=None)` — Generates Opportunity name as `OPP-{contact_or_customer_name}-.###`.

### `communication.py`
`hd_partner_email_threading(doc, method=None)` — Before-insert on Communication: apply Partner Email Source regex rules to extract partner ticket keys and thread emails to existing HD Tickets.

### `company_access.py`
| Function | Description |
|---|---|
| `validate_company_on_login` | Block login if user has no User Permission for any Company |
| `user_details` | Return list of companies + abbreviations accessible to the user |
| `set_user_permission` | Set company as default and update User Permissions |
| `global_company_condition` | Row-level security: append `company = <selected>` condition to all doctypes with a company Link field |

### `pdf.py`
| Function | Description |
|---|---|
| `report_to_pdf` | Whitelisted — custom PDF generation entry point |
| `_redirect_assets_to_localhost` | Rewrite asset URLs to `127.0.0.1` for wkhtmltopdf subprocess |
| `download_pdf` | Override `frappe.utils.print_format.download_pdf` with localhost redirection |

---

## 7. Client-Side Customisations (JS)

**Directory:** `bsgroup/public/js/`

### `app.js`
Persists active workspace sidebar item in `localStorage` and restores it on route change.

### `Lead.js`
- Hide default buttons: Customer, Quotation, Prospect
- Custom "Opportunity" button: calls `lead.make_opportunity()`, sets `sales_stage = "Proposal"`, copies `custom_organization_name` from `company_name`

### `opportunity.js`
- `set_lead_name(frm)` — populate `custom_contact_person_name` and `custom_organization_name` from Lead/Customer
- `hide_create_button(frm)` — hide Supplier Quotation, RFQ, Customer links
- `set_opportunity_status(frm)` — sync `status` with `sales_stage` (Lost/Won → Lost/Closed)
- Show "Presales Request" or "Deal Cost Sheet" button based on `custom_presales_required`

### `quotation.js`
- `set_customer_item(frm, cdt, cdn)` — build description from `item_name + item_code + brand` (or just `item_name` when exclude flag is set)
- `exclude_all_items(frm)` — apply `custom_apply_exclude_to_all_items` to all rows
- `apply_company_tax(frm)` — fetch and apply default Sales Taxes template for selected company
- `item_code` trigger — fetch `item_name` and `brand` from DB before building description (fixes async timing issue)
- `onload` — fetch employee `designation` and `cell_number` from current user's Employee record

### `task.js`
- `onload` — set `custom_created_by` to current user
- Custom "Timesheet" button — creates new Timesheet pre-filled with project/task references

### `project.js`
- Custom "Task" button — creates new Task with project pre-filled

### `item.js`
- Toggle display of `item_code`
- `item_group` change — if "Professional Services" or "Services", set `is_stock_item = 0`

### `timesheet.js`
- Remove Start/Resume Timer buttons
- `calc_hours` — calculate hours from `custom_from_times` / `custom_to_times` (HH:MM:SS)
- `custom_reference` change — sync `project` from reference if type is Project
- Restrict `custom_reference_type` to Project or HD Ticket

### `hd_ticket.js`
- `hdGenerateSummary()` — auto-populate summary field with status, priority, SLA, issue, next action, resolution snapshot
- `hdCheckResolution()` — gate "Refine Resolution" button on `resolution_details` content
- `hdOpenRefinePanel()` / `hdApplyRefinement()` — inline resolution refinement panel
- Auto-refresh summary every 60 seconds

---

## 8. Print Templates

**Directory:** `bsgroup/templates/`

### `bits_uae_quoatation.html` and `proposal_pdf_uae.html`
Professional UAE quotation print formats for the **Quotation** doctype.

| Section | Content |
|---|---|
| Cover Letter | Date, recipient, subject, reference#, salutation, standard proposal body, signature with designation |
| Items Table | #, Item & Description, Qty, Rate, Amount |
| Totals | Sub Total, Discount, VAT 5%, Grand Total |
| Commercial Summary | Tax detail table with VAT amount and total |
| Customer Notes | Optional notes box |
| Terms Page | 15 clauses: Prices · Payment · Delivery · Installation · Scope · Warranty · Software · Support · Site Readiness · Access · Validity · Order Confirmation · Cancellation · Force Majeure · Jurisdiction |

**Styling:** Blue color scheme (#2c70ba / #2e80b7), 11pt font, page-break-inside: avoid on item rows, letterhead handled externally by Frappe.

---

## 9. Reports

**Directory:** `bsgroup/bs_group/report/`

### Opportunity Summary Report
- **Columns:** Opportunity, Account, Scope, Order Value, Margin, Month, Year, Status (colour-coded), Action Plan
- **Filters:** from_date, to_date, account, scope, status
- **Summary row:** Total Order Value · Total Margin · Total Records

### Task Scheduler Report
- **Columns:** Task, Project, Status, Created By, Assigned To, Start Date, End Date, Progress
- **Filters:** task, project, created_by, assigned_to, from_date, to_date, schedule (Today/Next Day/Week)
- Tree hierarchy via `parent_task`; group progress = average of children

### Task Summary Report
- **Columns:** Task, Status, Priority, Start/End Date, Progress
- Hierarchical display, supports 16 project statuses, AMC status filter

### Tech Task Scheduler Report
- **Columns:** Date, Category, Project/Ticket, Task, Assigned To, Status, Activity Details
- **Filters:** date_filter (Today/Tomorrow/This Week/This Month/Custom), category, task, assigned_to, status
- JOIN resolves category display name (project_name, HD Ticket subject, or plain text)

### Customer Project Plan Report
- Customer-facing project plan view

---

## 10. Custom Pages / Dashboards

**Directory:** `bsgroup/bs_group/page/`

### Sales Management Dashboard (`sales_management_das`)

**KPIs:** Total Pipeline · Closing in Range · Overdue Follow-ups · No Updates in 7 Days

**Data sections:** Pipeline by Stage · Owner-wise Pipeline (top 10) · Overdue List (6) · Closing List (6) · Latest Updates (6) · Stuck Deals — same stage > 14 days (top 6)

**Access:** System Manager (all) · Sales Manager (self + team) · Sales User (self only)

### Presales Request Dashboard (`presales_request_das`)

**KPIs:** Total Active Requests · Total Pipeline Value · Overdue Count · Due This Period · Avg Quality Score · Completed This Month · No Updates in 7 Days

**Data sections:** Pipeline by Status · Pipeline by Priority · Owner-wise Pipeline (top 10) · Overdue List (8) · Due This Period (8) · High-Value Active (8) · Efficiency Stats by owner (actual vs. estimated hours)

**Access:** System Manager · Sales Manager · Presales Manager

### Other Pages
- `weekly_customer_das` — Weekly customer activity dashboard
- `hd_ticket_das` — Help desk ticket dashboard
- `cheque_request_das` — Cheque request tracking page

---

## 11. Workspaces

**Directory:** `bsgroup/bs_group/workspace/`

| Workspace | File |
|---|---|
| BS Group Sales | `bs_group___sales.json` |
| BS Group Helpdesk | `bs_group___helpdesk.json` |
| BS Group Project | `bs_group___project.json` |
| BS Group Approvals | `bs_group___approvals.json` |

---

## 12. Scheduler Events

| Frequency | Function | Purpose |
|---|---|---|
| Daily | `bsgroup.utils.opportunity.update_overdue_followup_for_all` | Update `custom_overdue_followup` on all open Opportunities |
| Daily | `bsgroup.bs_group.doctype.presales_request.presales_request.calculate_due_date` | Update `overdue` flag and `delay_days` on all Presales Requests |

---

## 13. Fixtures & Data Sync

```python
fixtures = [
    {"doctype": "Property Setter", "filters": [["module", "=", "BS Group"]]},
    {"doctype": "Workflow"},
    {"doctype": "Workflow Action Master"},
    {"doctype": "Workflow State"},
    {"doctype": "Role"},
]
```

Synced via `bench export-fixtures` / `bench migrate`.

---

## 14. Custom Fields on Standard DocTypes

Added via Property Setter fixtures (module = "BS Group"):

| DocType | Custom Fields |
|---|---|
| **Quotation** | custom_contact_person_name, custom_organization_name, custom_subject, custom_payment_terms, custom_delivery_terms, custom_warranty, custom_designation, custom_phone__no, custom_apply_exclude_to_all_items, custom_customer_notes, custom_scope_overview |
| **Quotation Item** | custom_customer_item_name, custom_exclude_item_name_and_brand, custom_header |
| **Opportunity** | custom_contact_person_name, custom_organization_name, custom_subject, custom_presales_required, custom_stage_history (table), custom_stage_last_changed_on, custom_stage_age_days, custom_sales_updates (table), custom_next_action, custom_next_action_date, custom_last_sales_update, custom_last_update_date, custom_margin, custom_overdue_followup, custom_external_reference |
| **Timesheet** | custom_date, custom_reference_type, custom_reference |
| **Timesheet Detail** | custom_from_times, custom_to_times, custom_reference_type, custom_reference |
| **Task** | custom_created_by |
| **HD Ticket** | custom_next_action, custom_next_action_date, custom_external_reference |
| **Communication** | custom_external_reference |
| **Employee** | cell_number |
| **Project** | custom_latest_update_log (child table) |

---

## 15. Key Business Logic Summary

### Sales Pipeline
1. Opportunity auto-assigned to creator (`opportunity_owner`) on insert
2. Stage transitions tracked with timestamp + user → `custom_stage_history` child table
3. `custom_stage_age_days` recalculated on every save
4. Sales updates appended when `custom_next_action` / `custom_next_action_date` change
5. Daily scheduler flags overdue follow-ups

### Presales Qualification
- 5 binary criteria × 20 pts = max 100 `quality_score`
- `quality_band`: 0–40 = Low · 41–70 = Medium · 71–100 = High
- Auto-updates linked Opportunity status to "Presales Request" on creation
- Daily due_date and delay_days recalculation

### Deal Costing
- Products and Professional Services tracked separately with individual GP %
- Resource costing: `persons × days × rate` or `hours × rate`
- GP = `(selling - cost) / selling × 100`
- Excel/CSV item import with column mapping
- Solution responsibility matrix: our team vs. customer deliverables
- `make_quotation()` maps deal items → Quotation items with all custom fields

### Email & Help Desk Threading
- 5-layer fallback strategy to find parent Communication for incoming emails
- Duplicate HD Ticket detection: same cleaned subject + sender + open → move communications + delete duplicate
- Partner ITSM integration via configurable regex rules in Partner Email Source
- RFC 2822 `References` header injected on outgoing emails for chain continuity
- 180-day lookback window for matching

### Timesheet
- Overlap validation disabled (explicit business decision)
- Time calculated from `custom_from_times` / `custom_to_times` (HH:MM:SS)
- Task marked "Completed" only when ALL its time logs are completed
- Reference type limited to Project or HD Ticket

### PDF Generation
- wkhtmltopdf used for print-quality PDFs
- All asset/file URLs rewritten to `127.0.0.1` so the subprocess can load them locally
- Quotation print format: cover letter + items + totals + commercial summary + 15-clause terms

---

*Generated by Claude Code analysis — 2026-06-22*
