# BS Procurement — standard ERPNext documents

Implemented on `rel1-test.local` on 20 October 2026. Page build `20261020-payment-policy`, with the cash-journal and closed-PO backend fixes below.

Current BS PR, PO and Payment Order approver: **Mohan Babu (`mohan@bitssecureit.com`)**, irrespective of creator, preparer or sender, including Mohan himself. This explicit policy supersedes the earlier maker-checker and Accounts Manager approval rules described in the historical release notes below.

The BS Procurement screen now saves Purchase Requisitions as standard **Material Request** documents with purpose **Purchase**, and orders as standard **Purchase Order** documents. There are no replacement PR or PO DocTypes. Custom fields and scoped hooks add the BS approval, comparison and audit controls to those standard documents.

Route: `http://rel1-test.local:8001/desk/bs-group/bs-procurement`

## Process

1. On a submitted, Won quotation with its private Customer PO, use **Send to Procurement**. Review the awarded DCS item quantities and cost rates, choose the required date and warehouse, then create the draft requisition. Procurement can also create a manual requisition.
2. Send for approval through the existing Material Request Approval workflow. Approval submits the standard Material Request. Rejection requires a reason; revisions and resubmissions retain history.
3. Select approved PR lines, quantities and a supplier. The standard Material Request-to-Purchase Order mapper creates a draft PO with native `material_request` and `material_request_item` links.
4. Complete the PO and compare three distinct suppliers using actual private quotation attachments and prices. An explained quotation exception is allowed for manager review. Above-budget prices and deviations from the selected quote require a selection explanation.
5. Request PO approval. Approval submits the standard Purchase Order; its standard ordered quantities update the Material Request. The approved PO is available to ERPNext's Purchase Receipt and Purchase Invoice processes, subject to their normal permissions.
6. Open the approved PO PDF. The existing September **Purchase Order Print Format** and **Order Letterhead** are selected unchanged.

Each PR shows its own approval, purchasing status, progress tracker, line allocations, linked POs and history. Partial quantities and different suppliers can create multiple POs for one PR. A BS PO is restricted to one PR.

Draft, pending, rejected and submitted POs reserve quantities. A withdrawn draft remains a standard draft with BS state Cancelled, releases its reservation and cannot be revived. Cancelling a submitted PO uses standard ERPNext cancellation. Standard amendment creates a fresh draft with the original lineage retained. A PR with active POs cannot be cancelled.

## Permissions and integrity

- Buyers need Purchase User and the site's normal company/master permissions. Mohan is the sole BS PR/PO approver. His existing purchase roles are retained and the dedicated BS Procurement Approver routing role is added.
- The existing Material Request workflow is reused with BS-only transitions. Mohan can approve or reject his own BS requests; ordinary Material Requests retain their prior rules. Server checks block substitution by another manager or Administrator.
- Server checks protect both the BS screen and standard forms. Native submit, editable APIs, print, amendment and the existing Update Items override cannot bypass the applicable BS controls.
- Saved pending/approved commercial data and quotation evidence are protected. Submitted snapshots retain earlier prices, supplier, terms and comparison values.
- Parent Material Request locking and current allocation reads prevent simultaneous orders from over-allocating a line. A transaction conflict asks the second user to refresh.
- Every new PO, including one made through standard ERPNext, requires an approved BS PR. Existing ordinary drafts cannot be saved/submitted around this route. Historical submitted orders retain their original approval history; they cannot be expanded or reopened. Create replacement purchasing scope through an approved BS PR.
- Supplier exception flags for invoices without PO/receipt are locked off. All supplier outpayments require full allocation to submitted BS Payment Orders with recorded Mohan approval; native Payment Entry, supplier-debit Journal Entry and reconciliation paths enforce this rule. Historical invoice approval labels alone do not authorize new supplier payments.

## Setup and deployment

`bsgroup.procurement_setup.execute` idempotently creates the standard-document custom fields, approval routing and the legacy `BS Procurement Purchase Order` Print Format. It is also registered in `after_migrate`. The BS PDF action selects the existing September `Purchase Order Print Format`; the global default remains unchanged.

The test site's `host_name` is `http://rel1-test.local:8001`. Missing logo/stamp files in the imported September format remain missing; its layout and letterhead have not been modified.

From `/home/bitssecureit/rel1-bench/sites`, run the page deployment helper after JavaScript edits:

```sh
/home/bitssecureit/rel1-bench/env/bin/python ../apps/bsgroup/tests/bs_procurement/deploy_standard.py
```

It checks the runtime folder and JavaScript syntax, updates Page.modified, reloads the Page and clears cache so a normal browser reload receives the current code. Reports and documentation must stay outside the Page runtime directory: Frappe treats HTML files there as page templates.

## Verification

Run these independently from the same sites directory; do not run the database-mutating suites concurrently:

```sh
/home/bitssecureit/rel1-bench/env/bin/python ../apps/bsgroup/tests/bs_procurement/test_standard_documents.py
/home/bitssecureit/rel1-bench/env/bin/python ../apps/bsgroup/tests/bs_procurement/test_concurrent_orders.py
```

On 20 October 2026, all **43 backend assertions** passed. They cover standard document persistence and mapping, approval permissions, rejection/resubmission history, stale edits, native bypass prevention, actual quotation attachments, partial and multiple-vendor allocation, cancellation/amendment, printing and access restrictions. The main suite rolls back its test users and transactions.

The separate two-process concurrency test passed: one PO was saved, the competing request was blocked, and allocation stayed within the PR. Its PO was withdrawn and PR cancelled with audit retained.

Native Chrome verified creation, approval, saving, refresh persistence, matching records in the standard ERPNext form, partial order progress and the PDF action. Review records retained on the test site:

- Material Request `MAT-MR-2026-00002`: approved, four units requested, two ordered, two available.
- Purchase Order `PUR-ORD-2026-02408`: approved/submitted, two units at AED 90, total AED 180, status To Receive and Bill. Terms identify it as QC TEST ONLY — DO NOT ISSUE.

The final PDF was generated using Frappe, extracted and visually checked as a single page. Purchase Receipt and Purchase Invoice mappings were verified; actual receipt/invoice posting was outside this test.

Logs: `qa_reports/standard_documents_test.log`, `qa_reports/concurrent_orders_test.log`.
Report: `qa_reports/QA_STANDARD_DOCUMENTS_BS_Procurement_20261020.html`.

## Sales handover integration — 20 October 2026

`bsgroup.dcs.procurement.send_to_procurement` now creates a standard Material Request. It preserves the quotation, DCS revision/award, customer, project, customer PO reference and original DCS row identities. Three private source files are attached: awarded quotation, customer PO and costing sheet. File hashes and a snapshot preserve the evidence. The quotation's **View Purchase Requisition** opens that exact PR in BS Procurement.

Sales Manager, Commercial Controller and Managing Director authority is checked against the source documents and company. The sender receives a read-only share of their PR, without purchasing approval rights. No email or supplier message is sent. The PR starts as Draft; Procurement requests its normal independent approval.

Warehouse choices are limited to the source company and explicit user restrictions, without granting general warehouse access to Sales. A dedicated Sales Customer field is used because ERPNext clears its standard Customer field for Purchase-purpose Material Requests. The inherited DCS budget is preserved rather than replaced by a default buying price list.

Repeated sends for the same award return the existing PR. Source locks and a unique award key prevent simultaneous sends from creating duplicates. DCS revision/award changes block subsequent purchasing. Source references, quantities and budget are protected; source evidence cannot be detached or deleted. Cancelling an approved PR keeps the quotation backlink as history while retaining the existing active-PO cancellation guard.

The four earlier DCS Purchase Request packets remain read-only historical evidence; new sends do not create that DocType. The restored historical controller allows those records to remain accessible.

Verification: **30 handover assertions + 43 purchasing regression assertions passed**, plus a real two-process send collision test. Native Chrome created `MAT-MR-2026-00007` from `SAL-QTN-2026-01213`, retained the correct AED 1,000 budget, opened its saved costing PDF, and verified the quotation-to-PR return link. The review PR remains Draft. Concurrency test PRs were cancelled with evidence retained. Temporary test users were rolled back.

Logs: `qa_reports/sales_handover_test.log`, `qa_reports/standard_documents_after_handover.log`, `qa_reports/concurrent_handover_test.log`, `qa_reports/handover_delivery_verified.json`.

Deploy changed quotation/page scripts with `tests/bs_procurement/deploy_handover.py` from the bench's sites directory. This helper is restricted to the test site, refreshes quotation metadata caching and invokes the standard procurement page deployment.

## Accounting continuity review — 20 October 2026

Actual Purchase Receipts, Purchase Invoices, Sales Orders, Sales Invoices and Payment Entries were submitted in rolled-back test transactions. All **39 accounting continuity assertions**, **43 procurement regressions** and **30 sales handover regressions** passed. Invoice and payment GL entries balance; stock receipts post stock ledger entries. Tests cover split suppliers, partial delivery/billing/payment, accounting approval roles, source-row links, project attribution, cancellation and over-receipt/over-billing rejection.

Two corrections were made:

- The PR's custom header project now reaches the standard PO header before validation, including the native MR-to-PO form path. It remains protected against removal or substitution. PO approval snapshots also include header project/cost center and row expense/cost-center dimensions.
- `bsgroup.utils.project_cost_baseline` now counts only unbilled PO net value as commitment, using company currency and row project attribution. Invoice submission replaces the corresponding commitment rather than adding its full value again. An exact-budget invoice and a genuinely additional over-budget PO were tested under Block policy; invoice cancellation restores commitment and reduces actual cost.

Run `tests/bs_procurement/test_accounts_continuity.py` from the bench's sites directory. It uses the existing clearly labelled review quotation/PR and rolls back all changes. `verify_accounts_continuity.py` confirms the original review records, absence of temporary fixtures and restored site policy. Logs: `qa_reports/accounts_continuity_test.log`, `standard_documents_after_accounts.log`, `handover_after_accounts.log`. Report: `qa_reports/QA_CONTINUITY_BS_Procurement_20261020.html`.

At the time of that initial audit, matching requirements and project overrun blocking were off. The Payment Order release below supersedes those findings. Sales invoicing remains a separate explicit Sales Order → Sales Invoice → customer receipt flow; Send to Procurement does not post customer invoices.

## Payment Order release — 20 October 2026

BS Procurement now contains **Purchase Requisition**, **Purchase Order**, and **Payment Order**. A Payment Order is the BS view of one standard Purchase Invoice (supplier/vendor invoice). It does not create a second liability or a separate payment ledger. Receipts, invoice approval, outstanding balances and Payment Entry allocations appear in this section; PR and PO screens keep their purchasing responsibilities.

Payment Orders are listed by invoice ID, vendor invoice number, supplier, due date, approval, payment status, total and outstanding. The detail view includes source POs, invoiced items, matched receipt lines and permitted Payment Entry records. A shared bank payment displays only the allocation against the selected invoice. Draft/cancelled invoices do not display a payable balance. Released allocations remain identifiable after invoice cancellation through server-controlled source history.

**New Payment Order** prepares an unsaved native Purchase Invoice from a submitted receipt, or from non-stock/non-asset lines of an approved BS PO. Users review the vendor's invoice number, date, taxes, attachments and terms in the standard form before saving. **Record payment** prepares a native Payment Entry against an approved outstanding invoice for review. No payments are automatically submitted or transferred.

The existing Purchase Invoice workflow is retained: Draft → Send for Approval → Pending Approval → Accounts Manager approval. Accounts User cannot approve. Existing document/company permissions control all invoice, receipt and payment data. Accounts User and Accounts Manager can access the procurement page; this adds no permissions to the underlying documents.

Explicitly activated on **rel1-test.local only**:

- Buying Settings: PO required **Yes**, receipt required **Yes**.
- Price matching remains enabled with **Stop**, no override role.
- BS Group Settings: cost overrun policy **Block**.
- BS receipt/invoice rows must preserve the approved PO row, PR row and project. Invoice receipt rows must match the same PO row.
- Project-linked BS POs require an approved Project Cost Baseline before requesting/receiving approval. All header and line projects participate in the transaction overrun check.

ERPNext's stock/fixed-asset receipt requirement is preserved. Non-stock services require an approved PO but not a stock receipt. Standard return/internal-transfer exceptions remain in place. Project remains optional for non-project buying. Perpetual inventory was not changed.

There are currently **zero approved project baselines** on the test site. Real project budgets must be created and approved through the existing baseline workflow; no amounts were invented.

Validation: **66 invoice/accounting/control assertions + 43 procurement regressions + 30 handover regressions = 139 passed**. Real test receipts, invoices, ledger entries and payments were rolled back. Coverage includes service and stock invoices, missing/wrong PO/receipt links, price mismatch, partial receipts/billing/payments, shared payment allocations, cancellations, access roles, over-receipt/over-billing and exact-budget/over-budget behavior. Foreign currencies, credit notes, landed costs and advance reconciliation were not newly certified by this release.

Local Chrome verified the three sections, New Payment Order → standard Purchase Invoice, saved draft, deep link and refresh. Retained QC draft `ACC-PINV-2026-09339`, vendor invoice no. `ZZTEST-PAYMENT-ORDER-20261020`, references review PO `PUR-ORD-2026-02408` for AED 180. It has no posted ledger entries or payments.

Runtime: `bsgroup/procurement_accounts.py`; schema: `bsgroup/procurement_setup.py`; idempotent installation: `tests/bs_procurement/install_payment_orders.py`. `enable_matching_controls.py` is a separate, explicit test-site activation and is never run automatically by migration. `verify_payment_orders.py` verifies persisted settings, test counts and review invoice state.

Evidence: `qa_reports/payment_order_test.log`, `standard_after_payment_orders.log`, `handover_after_payment_orders.log`, `matching_controls_activation.json`, `payment_orders_verified.json`, and `QA_PAYMENT_ORDERS_BS_Procurement_20261020.html`.

## Remaining scope

- DCS Item rows become PR lines, including purchasable service Items. Labour/resource and additional-charge tables remain in the attached costing evidence and are explicitly identified in the handover preview; they are not silently converted into purchasable Items.
- A separate Service Entry Sheet document is not part of the clarified invoice-based Payment Order scope.
- Comparison prices use the selected PO currency and purchase UOM. Enter an approved transaction exchange rate; configure Item UOM conversions first. All three quotations must use that same currency and unit basis.
- Supplier quotations are preserved as comparison data and private File attachments on the standard PO; this release does not create separate Supplier Quotation documents.
- Supplier contact/address, tax templates and payment schedules are maintained through the standard Purchase Order form. Supplier/master data completeness remains operational setup.
- Only BS-managed requisitions are listed. Previous browser-only preview records were not ERP transactions and were not migrated.
- Production was not deployed or changed.

The former preview is archived as `docs/bs_procurement/archive_qc4_screen.js`. Legacy preview tests are disabled under tests/bs_procurement/archive; sample-PDF endpoints were removed in the QC hardening release below.


## QC hardening release — 20 October 2026

Build `20261020-standard-2` addresses report G-01 through G-25. This supersedes the old matching-activation and comparison-currency notes above. `procurement_setup.execute` now reapplies the required settings on migration; row-level BS controls remain effective even if global allowances are later relaxed.

- A creator, preparer or sender cannot approve their PR, PO or supplier invoice, including Administrator. A separate authorised user is required. The participant history is server-controlled and intentionally conservative across revisions.
- Pending and approved POs lock business fields, including descriptions, addresses, contacts, tax treatment and accounting dimensions. Only explicit fulfilment/lifecycle counters and regenerated tax presentation are excluded.
- File guards run before core file deletion or privacy moves. Three quotations must be distinct nonempty uploaded files of an allowed document type, checked against actual bytes.
- Manual PRs cannot claim an awarded quotation or DCS budget; use Send to Procurement. An existing ordinary MR or PO cannot be converted by changing its BS flag. Sales handover descriptions, item names and required dates are frozen.
- Each above-budget or selected-quotation price variance needs its own explanation of at least 15 characters. Supplier address, contact and explicit tax template are required before PO submission for approval. No tax rate or TRN is invented. The PDF button uses the existing September `Purchase Order Print Format` and `Order Letterhead`, unchanged, as explicitly requested. It retains Tax %, Tax, delivery, terms, signature area and its original E-Approved line. Missing test-site logo/stamp files remain missing; no replacement artwork or template changes were made. The new BS template remains installed but is no longer forced by the PDF button. Actual approver identity remains in the PO audit history.
- A closed PO retains the greater of received and billed quantity; its remaining balance can be re-sourced. Reopening checks the remaining PR allocation. Withdrawn draft POs have a distinct indicator and filter. Standard draft reports still follow ERPNext docstatus; use the BS approval filter to exclude withdrawals.
- BS receipt and invoice rows require their approved PO and row, enforce quantity/rate limits and configured UOM conversions, and require accepted receipts for stock/assets. Non-stock services remain invoiceable against their approved PO. Standard return exceptions are retained.
- PR summaries and Payment Order headers are batched; payment audit associations use an indexed table. The PO list is independently paginated and searched on the server.
- Cancellation reasons are mandatory on the server. The screen avoids duplicating ERP validation popups. UI tests execute the actual page with controlled server responses.
- Setup appends hooks, scopes BS send transitions and preserves locally customised print formats. Old sample-PDF endpoints are removed.

### Verification and operation

Run the standard-document, QC-gap, accounts-continuity and sales-handover Python suites sequentially from the bench sites directory. Their business transactions roll back. `test_concurrent_orders.py` requires independent committed transactions; it withdraws the winning PO and cancels the PR, retaining audit evidence. It uses the designated approver and never disables Mohan. Never run these suites on production.

For UI tests, run `npm ci --prefix tests/bs_procurement/ui` then `node tests/bs_procurement/test_ui.cjs` from the app repository. The exact dev dependency and lockfile are checked in. `test_deployment.py` checks setup idempotency and restores its temporary print customization. `test_pdf.py` generates a QC-only PDF from a rolled-back approval.

The complete per-gap closure report and validation counts are recorded in `docs/bs_procurement/QC_CLOSURE_standard-2.html`. Business fixtures require the existing labelled test Items, suppliers and source review quotation/PR described above.

### Deployment and rollback

Current execution is restricted to `rel1-test.local`. Production deployment remains a separate activity. Take a full database and private/public files backup before a production migration; review vendor master data, tax templates, project baselines and independent approver assignments first. Deploy the exact reviewed commit, run the normal site migration, rebuild assets and restart the application.

The release commit is the source checkpoint. A source revert alone does not reverse schema, settings, workflow changes, source history or accounting transactions. Restore a matched predeployment database/files backup for a full rollback, or use a separately reviewed forward correction. Preserve operational records and audit evidence.

Foreign-currency PO creation and configured Box/UOM allocation are tested; cross-currency settlement, credit-note exceptions, landed costs and advance reconciliation are not newly certified by this release. Three quotations are attached evidence and comparison records, not separate Supplier Quotation documents.

## Designated Mohan approval — 20 October 2026

All BS Purchase Requisitions and Purchase Orders now require Mohan Babu (`mohan@bitssecureit.com`) for Approve and Reject. The initiator has no effect on routing; Mohan may decide his own PR/PO. Other Purchase Managers and Administrator cannot substitute through BS actions or native document saves/submission. Preparers and decision actors remain recorded for audit. The two detail screens display the approver's name and account.

The shared Material Request workflow has separate BS decision transitions using the dedicated `BS Procurement Approver` role, assigned to Mohan. Open pending BS PR workflow actions are rerouted without rewriting completed decisions. Ordinary Material Request transitions and invoice maker-checker restrictions are preserved. PO decisions use the existing BS controls on standard Purchase Orders.

`deploy_mohan_approval.py` applied this authorised change on **rel1-test.local** and enabled Mohan's previously disabled test-site account without a welcome email. No passwords or existing company permissions were changed. Routine migrations install routing and role membership but do not reactivate an intentionally disabled account. Fixed identity checks still reject another user if the dedicated role is accidentally granted to them.

`test_mohan_approval.py` exercises buyer-, manager-, Administrator- and Mohan-initiated PR/PO creation, rejection, resubmission and approval; workflow routing; native bypass attempts; identity substitution; and invoice separation. Business transactions are rolled back. Existing regression suites now use the designated approver for purchase decisions. Evidence: `qa_reports/mohan_approval_test.log`, `mohan_deployment.log`, `mohan_regressions.log` and per-suite `mohan_*.log`.

Verification: **302 checks passed** — 90 designated-approver scenarios/assertions, 43 standard purchasing, 67 accounting continuity, 34 sales handover, 43 adversarial controls, 19 UI and 6 deployment checks. Local Chrome also confirmed the displayed approver inside the saved PR and PO. Test business transactions were rolled back; completed historical approvals retain their original actors.

## Manual PR quotations and direct invoice evidence — 20 October 2026

**New Purchase Requisition** offers **Purchase** and **Utility bill / direct invoice**. Create a draft, then complete the supporting-documents section inside that PR:

- Manual Purchase: attach three distinct quotations from three enabled suppliers, or tick **No three quotations required** and enter mandatory explanatory notes. One or two quotations alone cannot satisfy the requirement.
- Utility bill / direct invoice: attach one or more invoice copies, tick **No three quotations required**, and enter the explanation. Invoice copies alone do not bypass the quotation requirement.
- A warehouse is optional for non-stock services/utility bills and remains required for stock items. Existing purchase/service Items are used; no free-form item or expense account is invented.
- **Save supporting documents** preserves draft work. **Send for Approval** saves current evidence and notes before requesting Mohan's decision. Missing requirements block both the BS action and native Material Request workflow.

The standard Material Request stores server-controlled supporting evidence. Attachments must be private, nonempty files on that exact PR. Quotation and invoice duplicate content is checked. Pending/approved evidence is locked; rejection permits a revised submission, while original files and snapshots remain protected in the audit history. Mohan sees the files, suppliers, request type and explanation inside the PR.

Sales-handover PRs continue to use their awarded quotation/customer PO/costing packet and are not reclassified as manual PRs. Existing completed approvals are preserved. This release handles PR evidence and approval; downstream PO creation and supplier-invoice/Payment Order matching retain their current rules.

Setup: `bsgroup.procurement_setup.execute` creates the `custom_bsp_request_evidence` field idempotently. `tests/bs_procurement/install_pr_evidence.py` is the explicit test-site installer. Runtime: `bsgroup/procurement_requests.py`, the Material Request hooks in `bsgroup/procurement.py`, and the BS Procurement page.

Focused verification: `test_pr_supporting.py` exercises missing/partial/duplicate quotations, explained exceptions, invoice copies, no-warehouse service requests, stale saves, permission checks, native workflow bypasses, file privacy/deletion protection and rejection/resubmission history. Transactions and temporary files are rolled back/removed. UI coverage uses the actual page with controlled API responses. Logs: `qa_reports/pr_evidence_test.log`, `pr_evidence_ui.log`, `pr_evidence_regressions.log`, and per-suite `pr_evidence_*.log`.

Final verification: **347 checks passed** — 37 manual PR evidence, 27 UI, 90 Mohan approval, 43 standard purchasing, 67 accounting continuity, 34 sales handover, 43 adversarial controls and 6 deployment checks. Local Chrome verified the request-type selector, optional service warehouse and creation instructions. No new QC business records were retained.

## Required purchasing and supplier-payment controls — 20 October 2026

This policy supersedes the earlier Accounts Manager approval and payment-unlinking behavior:

- Every new Purchase Order requires a submitted, approved BS PR and Mohan's PO approval. The standard form, mapper and existing ordinary drafts cannot bypass it. Historical submitted ordinary POs retain their history, but cannot be expanded or reopened; create new scope through a BS PR.
- Payment Orders remain standard supplier Purchase Invoices. Their BS workflow routes Approve/Reject to Mohan only, including when he initiated the invoice. Other Accounts Managers, a user given the routing role, and Administrator cannot substitute. The Payment Order shows the designated approver and the recorded approval identity/time.
- Both Supplier exceptions for invoices without PO/receipt are set to zero, read-only, and guarded on the server. The PR's separate three-quotation exception remains available with its mandatory explanation.
- Supplier Payment Entries require full positive allocation to submitted BS Payment Orders bearing server-recorded Mohan approval. Supplier, company and payable account must match. Partial payments and payments covering several approved invoices remain supported; overpayment is blocked using a locked current invoice balance.
- Supplier-debit Journal Entries follow the same rule. Inline cash payments and applying advances while preparing invoices are blocked; first approve the Payment Order, then record its payment.
- Submitted edits and reconciliation cannot leave money unallocated or remove the approval requirement. Native Unreconcile Payment is blocked for active supplier payments because it removes links directly. Cancel/reverse the payment, then recreate it against the correct approved Payment Order. A Payment Order with an active linked payment cannot be cancelled first.

Migration recovers existing BS invoice lineage and reroutes pending reviews; it does **not** invent historical Mohan approvals. Previously approved invoices without recorded Mohan approval cannot authorize new payments under this policy. Resolve them through the controlled cancellation/amendment and approval process, reversing linked payments first where required. Existing posted accounting and historical approval actors are not rewritten.

Runtime: `bsgroup/procurement_payments.py`, standard document hooks, shared approval controls, and idempotent `procurement_setup.execute`. Explicit test-site installer: `tests/bs_procurement/install_payment_policy.py`. The September PO print format/letterhead remain selected unchanged.

`test_payment_policy.py` covers four invoice initiators, rejection/resubmission, role/identity substitution, approval forgery, ordinary PO bypasses, supplier exceptions, advances, journal settlement, allocation changes, native unreconciliation and reversal. All test business records and ledger entries roll back. Credit-note netting and foreign-currency settlement have not been newly certified; no production rollout is included.

Final verification: **453 checks passed** — 88 payment-policy, 43 standard purchasing, 90 designated-approver, 37 manual PR evidence, 69 accounting continuity, 34 quotation handover, 44 adversarial controls, 9 migration, 9 September print-format and 30 UI checks. Local Chrome confirmed Mohan's name/account inside the existing draft Payment Order and the absence of a payment action before approval. All 717 suppliers have both exception flags off. Logs: `qa_reports/payment_policy_test_*.log`, `payment_policy_ui.log`, `payment_policy_deploy_standard.log`.

## Cash-journal bypass and closed-order replacement — 20 October 2026

This corrects two gaps missed by the earlier tests. A party-less Journal Entry could debit Cooling Energy Bill and credit the bank. A closed PO released quantity on the BS screen but its full quantity remained in the native MR ordered total; a replacement could either fail mapping or fail final submission.

- Cash/bank credit journals now check the actual debit accounts even when no Supplier is supplied. Direct utility/expense payments, asset purchases and unclassified clearing payments are rejected. The error directs users through the invoice-supported BS PR, approved PO, Mohan-approved Payment Order and supplier payment. Supplier settlement cannot include an extra unchecked expense debit.
- Non-cash accruals and reversals remain available. Pure bank/cash transfers remain available. Genuine statutory-tax, employee, financing/capital and customer settlements have separate category and explanation fields on the standard Journal Entry. The account/party must match the category, and only Mohan can submit; the server records his identity and time. Accounts can prepare these drafts. A utility expense cannot be exempted by selecting one of these categories, including by Mohan. Historical entries receive no fabricated approval, and submitted financial details/classification cannot be changed in place.
- A closed BS PO counts only the greater of received and billed quantity, in stock units, toward the standard MR's ordered quantity. Open POs still count their full approved quantities, and draft BS POs still reserve quantity in the BS allocation check. The native mapper, final PO submission, close/reopen and BS screen now agree. An idempotent setup repair recalculates existing closed BS orders; ordinary historical POs retain the native calculation.
- Example: PR 10 → original PO 10 → receive 3 → close original PO → create replacement PO 7 for another supplier → Mohan approves. Both orders remain linked to the same PR; attempting an extra order or reopening the original into an over-allocation is blocked. Received/invoiced scope is retained. No over-order allowance was increased.
- Replacement cancellation releases its allocation. ERPNext's standard rule requiring an open PO for receipt cancellation remains: safely reopen after releasing replacement allocations, reverse the fulfilment, then close again. The resulting balance is recalculated. Fully received orders release no quantity. Selected fully allocated lines cannot be silently omitted during BS PO creation.

Runtime additions: `procurement_journals.py` and `procurement_quantities.py`, composed into standard document hooks and the existing Purchase Order mixin. ERPNext core files are unchanged. `procurement_setup.execute` installs the Journal Entry fields and repairs closed-order MR quantities.

Focused evidence: `test_cash_and_closed_orders.py` has **87 checks** covering actual submitted replacement POs and accounting/stock postings, unit conversion, partial invoicing, safe reopen/cancellation, approval forgery and non-procurement settlement controls. `test_payment_policy.py` additionally rejects a mixed approved-supplier/utility journal. All generated business records and ledger/stock entries are rolled back. Logs: `qa_reports/gap_fix_focused.log`, `cash_close_regressions.log`, `cash_close_*.log`.

Final verification: **541 checks passed** — 87 focused gap checks, 89 supplier-payment policy, 43 standard purchasing, 90 designated-approver, 37 manual PR evidence, 69 accounting continuity, 34 quotation handover, 44 adversarial controls, 9 migration, 9 September print-format and 30 UI checks. `verify_cash_close.py` verifies the installed fields/hooks, policy settings, unchanged retained BS record counts and absence of temporary gap-test masters. The computer's existing Chrome tab reloads BS Procurement successfully. Deployment is limited to `rel1-test.local`.

## Invoicing accepted quantities after PO closure — 20 October 2026

The subsequent release-readiness test exposed a limitation not covered by the 541 checks above: after receiving three units and replacing the closed PO's remaining seven units, the original supplier's three-unit invoice could not be submitted. Custom validation rejected every closed PO, even though ERPNext supports receipt-backed invoices after closure.

Closed BS POs now permit normal supplier invoices against existing submitted, accepted Purchase Receipts. They remain closed throughout invoice approval, payment, payment reversal, invoice cancellation and corrected invoicing. Mohan's approval is still required. New receipts, stock-updating invoices, missing or mismatched receipts, returned quantities, duplicate billing and excess quantities remain blocked. A service without a prior accepted receipt cannot be newly invoiced against a closed PO.

Closing a PO retains received-but-unbilled project cost and releases only unused scope. Invoicing transfers this commitment into actual cost without double-counting. Cancelling the invoice restores the commitment; returning received units updates both the PR balance and the project baseline. Reopening checks the project budget as well as the PR's remaining quantity. Setup also refreshes baselines when repairing existing closed BS orders.

The BS Payment Order source mapper caps proposed quantities at accepted, unreturned, unbilled stock units, even if the global rejected-quantity billing option is enabled. It recalculates invoice totals and payment schedules. It does not change that global setting or ERPNext core.

`test_closed_po_invoicing.py` exercises the original failure through actual standard document workflows and ledger/stock postings: PR 10 → PO 10 at AED 90 → receive 3 → close → replacement PO 7 at AED 95 → Mohan approves both Payment Orders → both suppliers fully paid. The AED 935 project baseline remains exact. It also covers partial payments, invoice reversal/replacement, service receipts, two-unit boxes, receipt returns, overspending and unsafe reopening. Every generated transaction, stock/ledger entry and temporary master is rolled back.

Evidence: `qa_reports/closed_po_invoicing.log`, `closed_invoice_regressions.log`, `closed_invoice_*.log` and `closed_invoice_verified.json`. The regression runner executes business suites sequentially; it never runs against production.

Final verification: **647 checks passed** — 106 closed-PO invoicing checks, 511 existing business/setup/print regression checks and 30 UI checks. Read-only verification confirmed Mohan's enabled approver account, required PO/receipt matching, blocked project overruns, disabled supplier exceptions and removal of this test's temporary records. The existing Chrome tab loaded the Payment Order screen successfully. Retained-record totals are a snapshot, not an assertion that other testers were inactive.

This resolves the closed-PO billing blocker on `rel1-test.local`. It does not certify a production rollout: independent user acceptance, the treatment of older unpaid supplier invoices lacking recorded Mohan approval, production-version compatibility and a verified backup/rollback plan remain release checks.

## Independent retest corrections — 20 October 2026

The browser retest labelled `ZZQC-BSP-20261020-2122` disproved completion of five additional controls. Commit `706cbcc` contained the closed-PO corrections, but it did not contain these fixes. The earlier passing check count must not be interpreted as coverage of negative journal amounts, untyped payroll accounts, buying-price-list repricing or binary-exact attachments.

- C-1: new and previously saved draft Journal Entries reject negative or non-finite debit/credit values in both company and account currency. This runs before cash classification, so a negative bank debit or supplier credit cannot evade the payment controls. Normal positive non-cash accruals, bank transfers and cancellation remain available.
- H-3: Bank charges is a distinct Journal Entry category. Existing payroll, employee-advance, loan and bank-charge chart accounts with blank native account types can be explicitly classified through an Account field controlled by Mohan. Setup seeds only exact known chart-account names once. A journal still needs a matching category, account/party and explanation; only Mohan can submit, with server-recorded approval evidence. Ordinary utilities and supplier settlements do not become category exceptions.
- M-1: BS PR budgets remain the amounts entered in the requested purchasing UOM. The native buying price list is cleared before `Material Request.on_update` can overwrite those rates. Existing QC document values are not silently rewritten.
- M-2: handover reads the original customer PO as bytes and creates the attachment through the standard File document with byte content. It avoids the legacy file helper's read/decode/rewrite cycle. The copied bytes are checked against the source, and evidence hashes use binary content. Existing historical handover evidence is retained.
- L-1: PR and PO quotation exceptions need explanatory text of at least 15 characters with meaningful alphanumeric content; punctuation, whitespace and repeated-character filler cannot authorize submission.
- M-3: an authorized rejection of an unchanged pending PO can proceed despite an existing project overrun. Approval and financial changes remain subject to the budget block.

`tests/bs_procurement/test_retest_gaps.py` reproduces the supplied QC cases on `rel1-test.local`. It reads the reported journals and original customer PO as fixtures, creates separate temporary transactions, and rolls back all new business/ledger records. The 70 focused checks include all five signed-journal variants, submission of old drafts, four legitimate non-procurement settlements, price-list 80 versus entered budget 100, exact 1,443-byte PDF copying, inadequate exception notes, and rejection of an over-budget pending PO. The original `ZZQC-BSP-20261020-2122` records remain available for independent inspection.

Release integration starts from main `4c378a0` and retains its Lead screen and 50 regression checks. The three conflicting runtime files use the new procurement behaviour. The inherited quotation tests now exercise standard Material Requests while retaining source-document protection checks. The two-unit-box test now supplies a budget in the actual requested UOM instead of relying on automatic repricing.

Production remains on hold pending independent acceptance of this retest build, rehearsal on the intended production framework versions and an explicit transition for older unpaid invoices/open POs. New approval evidence is never fabricated for historical balances.
