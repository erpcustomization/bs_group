# DCS quotation: prepared, ready, issued

A Quotation generated from a Deal Cost Sheet (DCS) moves through three states:
- **prepared** while it is a draft;
- **approved/ready** once it is submitted;
- **issued** once it is documented as sent (pipeline `Sent`/`Follow-up`).

Drafts may differ commercially from the DCS while sales works on them. Nothing that
reaches the customer as an offer may differ from the approved DCS position.

## Gates

| Path | Rule |
|---|---|
| Draft save | Saves with commercial differences. Identity, company/party, currency, finite/positive figures, malformed mappings, and cancelled/unsubmitted/superseded sheets are refused. The server records `custom_dcs_alignment`. |
| Revision made after the draft was prepared | The draft keeps the revision it was prepared against and shows **Stale** until someone runs **DCS > Review DCS Revision** (`review_revision`). That re-validates the draft and records a timeline comment. An unrelated save never acknowledges it. BOQ-revision sync with *update quotation* counts as an explicit review. |
| Submit (approved/ready) | Exact row-mapped match to the current revision. Plus the existing commercial authority: `authorised_position` on revision ≥ 1, and the same policy on the sheet's own totals for revision 0 (below). |
| `Sent` / `Follow-up` | Only a submitted quotation can be marked Sent. It must still be issuable at that moment, so a superseded or now-unapproved offer is refused. Only the move into these stages is checked. |
| Sales Order / `make_sales_order` | Unchanged strict gate plus authority. A pre-mapping record with migration evidence keeps the exact old rule. |
| Print view, PDF download, `attach_print` (non-beta formats) | `pdf_body_html` wraps the site's renderer (Frappe, or Print Designer, which is called unchanged). For an unissuable DCS quotation, interactive output gets a visible banner and watermark. Attachment/system output (`ignore_print_permissions`) is refused. Any template naming cost/margin/DCS internals is refused for DCS quotations. |
| Print Format Builder (beta) formats | Rendered by WeasyPrint outside `before_print`/`pdf_body_html`. The print permission is denied for unissuable DCS quotations (`has_permission` hook), and `on_print_pdf` refuses the PDF. |
| Email from the desk (`communication.email.make`) | Overridden: with a print attached, an unissuable DCS quotation is refused before any Communication exists. Client-supplied `print_html` is never attached for DCS quotations. |
| Confidential fields | `custom_cost_rate` (Quotation Item) and `custom_gp` (Quotation) are `print_hide`. |

## Authority (no exemptions)

* Revision ≥ 1: the existing `commercial_authority.authorised_position`.
* Revision 0 (legacy sheets submitted before living positions):
  * `custom_approval_state` Rejected or Returned refuses, and so does Blocked (stored or computed).
  * A required approval must be on record for exactly the current totals (`custom_approved_by` and approved cost/selling).
  * The requirement is computed by the existing `negotiation.requirement(0, margin)`, so the 20% floor applies.
  * Clear states (`""`, `Not Started`, `In Negotiation`) authorise only when nothing is required.
  * Any other state, or no positive selling, refuses.
* No role, threshold or approver changed.

## Source mapping

* `Deal Cost Item.source_key` / `Additional Charges Item.source_key` (hidden, `no_copy`):
  the row name on first save, carried into amendments, dropped on "duplicate". Legacy
  rows without a key are identified by row name.
* `Quotation Item.custom_dcs_source_rows`: the comma-separated source keys a line presents.
  It is set at generation, by BOQ-revision sync, or in **DCS > Map DCS Rows**.
  * Labels show the DCS row number, customer description, quantity and unit, e.g. `Row 1: Business laptop - 2 Nos`.
  * Charges show only their charge type.
  * Suggestions are offered only when exactly one candidate exists.
* Rules (`bsgroup/dcs/quote_alignment_core.py`):
  * Every quotation line must name its source rows. **An empty mapping is never legacy evidence**: removing all or part of a mapping makes the line `unmapped` (scope changed).
  * Every item row, and every charge with selling > 0, is presented exactly once. Unknown, duplicate or internal references are scope changes.
  * A single-source line keeps its item code and stock quantity (`qty × conversion_factor`).
  * A bundle (several rows), or any charge line, is **one package**: qty 1 in a 1:1 unit. Multipliers and conversions (qty 4 at 2500, qty 1 of a pack of 2) are scope changes. Qty ≤ 0 is invalid.
  * Line amount = sum of its sources' selling, and `amount` = `qty × rate`.
  * Every discount path counts. Line discount or price-list difference → repriced. Document discount or fixed/negative tax rows → total changed. `net_total` and `total` must both equal the DCS selling total.
  * Stale: the revision changed since preparation, the sheet was superseded or not submitted, or the living total differs from the BOQ rows.

## Legacy records

`bsgroup.patches.v0_1.dcs_quote_alignment` records `custom_dcs_legacy_basis` on every
quotation that is already submitted, DCS-linked and wholly unmapped when the patch runs.
* Only those records keep the pre-mapping Sales Order rule, and they count as issued for the deal status.
* The field is read-only and not editable after submit. Draft saves clear it, so copies, amendments and API payloads cannot obtain it.
* Pre-migration drafts are not changed. They must be mapped (with suggestions) before submit.

## Deal status ownership

The DCS status `Quoted` is owned by `quote_alignment.sync_quote_status` (Quotation `on_change`):
* drafts and submitted-but-not-sent quotations leave the sheet at `Submitted to Sales`, with its quotation link;
* a submitted quotation at Sent/Follow-up/Won/Lost/Expired, or one with legacy evidence, makes it `Quoted`;
* Won/Lost are never touched;
* award reversal uses the same rule.

`bsgroup.patches.v0_1.dcs_quote_status_owner` removes only the two status writes from the
*Quotation - Link Back to DCS and Close Presales* Server Script:
* It acts only when the live script's sha256 equals the production version (`39be1445…840f`, 4001 bytes, stored in `dcs/server_script_export/`).
* The quotation/DCS/presales links, the presales ladder and the canonical sync are unchanged.
* A customised script is left alone and reported; the app hook still corrects the status after it.
* Revert: `bench --site <site> execute bsgroup.patches.v0_1.dcs_quote_status_owner.revert`.

## Payment terms

Payment Terms are contract wording, and generation requires the user to enter and confirm it.
* The Payment Terms Template (selected, else the party's default) drives only the schedule.
* The dialog suggests wording built from the template's actual rows (portion, due basis, early-payment discount), never its name.
* Changing the template refreshes the suggestion unless the user has edited it.

## Remaining gaps

1. Server-side Python callers of `frappe.attach_print` / `frappe.get_print` (Notifications, Auto Repeat)
   with a **beta** format bypass the `has_permission` gate, because `attach_print` renders beta formats
   without a permission check. Non-beta formats are refused in `pdf_body_html`.
2. Server-side Python callers of `communication.email.make` (not the whitelisted HTTP path) are not
   intercepted before the Communication is created. Their print attachment is still refused at render time.
3. A PDF the user downloaded earlier and re-attaches as a plain File is not inspected.
4. Print Designer must stay installed **before** bsgroup in `apps.txt` (true on production). Otherwise
   `before_print` refuses unissuable output rather than leaving it unmarked.

## Policy points (for Mohan)

1. Quotation submit applies the existing authority (previously only at Sales Order).
2. Only a submitted DCS quotation can be marked Sent (submit = approved/ready, Sent = issued).
3. Revision-0 legacy sheets are no longer exempt. An unrecognised approval state blocks issue until reviewed.
4. Quotation users see DCS row labels and quantities in the mapping dialog, and selling only with DCS
   selling read access. No permissions were added or widened.

## Merge notes

Built on `main`. The obligations work (`feat/dcs-commercial-obligation-20261017`, 02a5036) and
`release/bs-procurement-20261020` also edit `validate_quotation`. When merging, keep their
`for_update=doc.docstatus == 1` lock and their `obligation.assert_clearance(sheet)` call on the issue
branch, next to `assert_issue_authority`. Hooks here are appended with the same `_prior` pattern.
`pdf_body_html`, `on_print_pdf`, `has_permission["Quotation"]` and the `communication.email.make`
override are new keys that the release branch doesn't use.

Verified on the isolated site (2026-10-24) with a throwaway merge of this branch into
`release/bs-procurement-20261020`:
* four mechanical conflicts (`quotation_control.py`, `hooks.py`, `patches.txt`, `quotation.js`);
* `assert_clearance` stays on quotation issue, Sales Order validate and `make_sales_order`;
* `bsgroup.dcs.test_quote_alignment` passes 41/41;
* `bsgroup.dcs.test_obligation` shows a strict subset of the release branch's own failures, all
  from production-only configuration, once one test call is updated at merge time:
  `make_quotation(self.sheet.name, payment_terms="ZZTEST 100% on delivery")` in
  `test_quotation_has_only_delivery_prices`, because generation now requires confirmed wording.

## Tests

```bash
# Isolated (no site):
python3 bsgroup/dcs/test_quote_alignment_core.py -v     # rules, authority, labels, wording
python3 bsgroup/dcs/test_linkback_script.py -v          # Server Script migration transform
python3 bsgroup/dcs/test_quote_output_unit.py -v        # output guards, stub frappe
node bsgroup/tests/js/test_quotation_dcs_alignment.js   # Quotation UI functions
# Frappe integration (isolated or staging site only; never production):
bench --site <site> run-tests --module bsgroup.dcs.test_quote_alignment
bench --site <site> run-tests --module bsgroup.api.dcs.test_dcs_audit_controls
bench --site <site> run-tests --module bsgroup.api.dcs.test_dcs_currency
bench --site <site> run-tests --module bsgroup.api.dcs.test_dcs_boq_revision
bench --site <site> run-tests --module bsgroup.api.dcs.test_dcs_vendor_revision
bench --site <site> run-tests --module bsgroup.api.dcs.test_dcs_quotation_access
```

### Results on an isolated site (2026-10-24)

The site was a throwaway bench built in the review container: Frappe v16.33.0, ERPNext v16.34.1
(0b50853), HRMS v16.17.1 (e1481b5) and Print Designer 9d62227, matching production. It ran
MariaDB 10.11 with a ZZTEST company in AED and no customer data. Two production-only items
were recreated on it:
- the DB-only custom fields `Quotation.custom_deal_cost_sheet` / `custom_presales_request` and
  `Presales Request.custom_*`, copied from rel1-test.local;
- the exact link-back Server Script (sha256 `39be1445…`).

* `bsgroup.dcs.test_quote_alignment`: **41/41 OK**, both with the link-back script unconverted
  (pre-deploy) and after the patch converted it (post-deploy: 0 status writes left, audit comment
  recorded).
* Existing DCS suites with this branch versus the same suites on `main` (4c378a0) on the same site:
  * identical results, except one fixture fix (`make_quotation_for` now writes consistent line
    amounts when it falls back to a raw insert);
  * `test_dcs_manager_approval`, `test_dcs_api`, `test_dcs_currency` and `test_deal_cost_sheet` pass;
  * the remaining failures are identical on `main`. They come from production-only configuration
    absent from a fresh site: role permissions for test users, the `dcs_presales_sync` Server Script
    API, and the `AMC Entitlement Consumption` DocType.
* Real PDFs (wkhtmltopdf and Print Designer's Chrome):
  * an unapproved draft in Standard and Enterprise Quotation format 2 carries
    "NOT FOR CUSTOMER ISSUE";
  * an aligned, authorised quotation is unmarked;
  * no PDF contains cost figures;
  * `attach_print` refuses the unapproved draft.

Pre-existing install gaps found (not changed here): the repo does not define
`Quotation.custom_deal_cost_sheet` or the `AMC Entitlement Consumption` DocType, so the app cannot
be installed on a fresh site without them.

Browser checks (staging, not automated):
1. Generate: the Payment Terms dialog shows wording from the template's terms, and the confirmation is required.
2. Redistribute 4500×2 / 1000: the banner shows Repriced and Submit is refused.
3. Print in Standard, Enterprise Quotation format 2 and Quotation Modern (beta): the first two show the banner and watermark, and the beta format is refused.
4. Email with a print attached: refused.
5. Map DCS Rows: the labels distinguish Generic rows. A bundle at qty 1 submits; the DCS stays Submitted to Sales until the quotation is marked Sent.
