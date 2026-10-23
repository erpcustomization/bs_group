# DCS quotation: draft vs issue

A Quotation generated from a Deal Cost Sheet (DCS) is **prepared** while it is a draft
and **issued** when it is submitted. Drafts may differ commercially from the DCS while
sales works on them. Nothing that reaches the customer as an offer may differ from the
approved DCS position.

## What changed

| Path | Before | Now |
|---|---|---|
| Draft save | Strict match: any bundle, redistribution, cut or quantity change was refused | Saves. Identity, company/party, currency, finite/non-negative figures, malformed mappings, cancelled/unsubmitted/superseded sheet are still refused. The server records `custom_dcs_alignment`. |
| Submit | `(item_code, qty, rate)` multiset + `total` | Row-mapped match (below) + **existing** `authorised_position` on revision ≥ 1 |
| Sales Order / `make_sales_order` | Strict + authority | Unchanged gate; mapped quotations use the row-mapped match |
| Pipeline `Sent` / `Follow-up` on a draft | Allowed | Moving a DCS draft into Sent/Follow-up requires it to be issuable |
| Print / PDF | Always allowed | Allowed; unaligned drafts carry the formats' existing **NOT FOR CUSTOMER ISSUE** notice; unknown custom formats refuse such drafts |
| Email attachment (`frappe.attach_print`) | Allowed | Refused for an unaligned or unauthorised draft |
| DCS status on draft save | `Quoted` (Server Script *Quotation - Link Back to DCS and Close Presales*) | Stays `Submitted to Sales` with the `custom_quotation` link (prepared). `Quoted` once a quotation is submitted, back when the last issued one is cancelled |
| Generation | Inserted with `ignore_mandatory`, Payment Terms blank, so the first form save failed. The form then rewrote contact/designation fields, leaving the new draft dirty. | Payment Terms come from the user or the party's existing Payment Terms Template; generation is refused when neither exists. Contact, organisation and designation are set the way the form derives them. |

## Source mapping

* `Deal Cost Item.source_key` / `Additional Charges Item.source_key`: hidden, set to the
  row name on first save. Copied into amendments (client amend, `frappe.copy_doc`);
  dropped on "duplicate". Legacy rows without a key are identified by row name.
* `Quotation Item.custom_dcs_source_rows`: the comma-separated source keys a line
  presents. Set at generation and by BOQ-revision sync, and editable only through
  **DCS > Map DCS Rows**. That dialog offers suggestions only when exactly one
  candidate exists; it never auto-maps ambiguous `Generic` rows.
* Rules (`bsgroup/dcs/quote_alignment_core.py`):
  * Every item row, and every additional charge with selling > 0, is presented exactly once.
    Unknown, duplicate or internal (cost-only) references are scope changes.
  * A single-source line keeps its item code and its **stock** quantity
    (`qty × conversion_factor`), so UOM changes are allowed.
  * A bundle line may only use an item code from its sources (or the configured additional-charge item).
  * Line amount = sum of the sources' selling; `amount` must equal `qty × rate`.
  * Every discount path counts: line discount or price-list difference → repriced.
    Document discount, `additional_discount_percentage`, or fixed/negative tax rows → total changed.
    `net_total` and `total` must both equal the DCS selling total.
  * Stale: DCS revision changed, sheet superseded or not submitted, or the living selling total
    differs from the BOQ rows.
  * States can coexist: `matching`, `bundled`, `repriced`, `total_changed`, `scope_changed`, `stale`.
* Descriptions and order are never compared.
* Legacy: a quotation with no mapping is judged by the previous multiset rule. An
  **already-submitted** unmapped quotation keeps the exact previous Sales Order rule,
  so no historical record is invalidated. Nothing is back-filled automatically.

## Confidentiality

* `alignment_summary` and `source_rows` return no cost, margin, GP, resources or
  internal-expense rows. DCS selling figures appear only for users with DCS read access
  at permlevel 1 (where the item selling fields sit).
* `Quotation Item.custom_cost_rate` is now `print_hide` (it was printable).
* Resources and cost-only charges are never written to quotation lines.

## Policy notes and open questions (for Mohan)

1. **Authority at issue.** Quotation submit now applies the *existing*
   `commercial_authority.authorised_position`, which was previously checked only at Sales
   Order. No role, threshold or approver changed. Effect: a deal whose current revision
   needs approval, or was rejected or returned, cannot be issued until the existing route
   approves a revision. Revision-0 legacy sheets keep the previous behaviour. Please
   confirm this is the intended point of control.
2. **Sent on drafts.** Previously a draft could be marked `Sent`. That is now refused only
   for unaligned or unauthorised DCS drafts. Whether every DCS quotation must be
   submitted before `Sent` is a policy choice that has not been made here.
3. **Payment Terms text.** When only a Payment Terms Template default exists, its name
   becomes the customer-facing `custom_payment_terms`. Confirm template names are suitable
   customer wording, or require typed terms.
4. **Server Script.** *Quotation - Link Back to DCS and Close Presales* still writes
   `Quoted` on every save. The app corrects this in `on_change`, which runs after that
   script. Retiring the script's status write is a separate DB change for the owner.
5. **Quotation users and DCS rows.** The mapping dialog shows DCS row labels and
   quantities to anyone who can write the quotation, and selling only with DCS selling
   access. No Sangeetha-specific or role permission was added or widened.

## Merge notes

Built on `main` (4c378a0). Staging `/home/bitssecureit/rel1-bench/apps/bsgroup` was at
706cbcc on `feat/bs-procurement-screen-20261019`, plus uncommitted edits. The obligations
work (02a5036) and `release/bs-procurement-20261020` both edit `validate_quotation`.
When merging, keep their `for_update=doc.docstatus == 1` lock and their
`obligation.assert_clearance(sheet)` call on the submit branch. In the issue branch of
the new `validate_quotation`, `assert_clearance` belongs next to
`assert_issue_authority`. Hooks here are appended at the end of `hooks.py` with the same
`_prior` pattern.

## Staging commands (rel1-test.local only, never production)

```bash
cd /home/bitssecureit/rel1-bench
bench --site rel1-test.local migrate        # runs bsgroup.patches.v0_1.dcs_quote_alignment, syncs print formats and fields
bench build --app bsgroup
# isolated rules, no site needed:
python3 apps/bsgroup/bsgroup/dcs/test_quote_alignment_core.py -v
node apps/bsgroup/bsgroup/tests/js/test_quotation_dcs_alignment.js
# Frappe integration (ZZTEST fixtures, sequential):
bench --site rel1-test.local run-tests --module bsgroup.dcs.test_quote_alignment
bench --site rel1-test.local run-tests --module bsgroup.api.dcs.test_dcs_audit_controls
bench --site rel1-test.local run-tests --module bsgroup.api.dcs.test_dcs_currency
bench --site rel1-test.local run-tests --module bsgroup.api.dcs.test_dcs_boq_revision
bench --site rel1-test.local run-tests --module bsgroup.api.dcs.test_dcs_vendor_revision
bench --site rel1-test.local run-tests --module bsgroup.api.dcs.test_dcs_quotation_access
bench --site rel1-test.local run-tests --module bsgroup.dcs.test_procurement
bench --site rel1-test.local run-tests --module bsgroup.dcs.test_presales_lineage
```

Browser checks on staging:

1. Generate from a DCS. The Payment Terms dialog appears, and the draft opens clean with
   no unsaved indicator.
2. Redistribute 4500×2 / 1000. The draft saves, the banner shows **Repriced**, and Submit
   is refused.
3. Print it in *Enterprise Quotation format 2*: the notice is shown. Email with a print
   attachment: refused.
4. **DCS > Map DCS Rows**: bundle both rows on one line at 10000. Submit succeeds and the
   DCS shows `Quoted` only after submit.
