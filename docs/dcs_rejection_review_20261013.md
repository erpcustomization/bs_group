# Rejection review correction — 13 October 2026

Base: `e506605120a38a1ecf2cd8f45b6baa5ce86742c8`, PR #9, target `fix/dcs-core-release-1`.

## Problem and resulting behavior

The merged tests explicitly permitted Reject → Revise → recovered margin → no approval → award. That conflicts with the owner's rule. Both totals-only and governed BOQ revisions now require fresh approval from the new revision's assigned immediate manager after a rejection, even at or above 20% margin or with an improved selling price. Repeated pending or Not Required revisions cannot clear that requirement. A later approved revision closes the rejection review cycle; ordinary future revisions retain their existing margin/concession rules. The concession ceiling remains unapprovable.

The implementation reads existing immutable revision decisions; it introduces no schema fields or data migration and never rewrites the rejected revision. Existing revision insertion snapshots the manager, queues the review, and retains existing governance events. Approval still validates the assigned manager, current revision and approved amounts. Authority recalculates the history requirement independently of the sheet's cached approval-required field, so an already-recorded recovery marked None is blocked from downstream use.

## Source inspection of downstream controls

| Path | Finding and correction |
| --- | --- |
| Totals revision | Margin/concession-only calculation corrected to include unresolved rejection. |
| BOQ revision | Same correction; existing manager snapshot and in-app review mechanism reused. |
| Award | Existing locked authority gate uses the corrected history-aware check. No award-path rewrite. |
| Quotation draft | Draft preparation remains allowed. |
| Quotation submission/use | Added history-aware fresh-approval gate and row lock during quotation validation. |
| Quotation link editing | Existing DCS linkage cannot be removed/repointed through normal document saves; submitted lineage guard also includes the DCS link. Governed amendment linkback remains an internal audited database write. |
| Quotation → Sales Order mapper | Existing authority check now includes rejection history. |
| Sales Order validate/before_submit | Existing checks now include rejection history. Existing DCS-linked quotation provenance cannot be removed through normal saves. |
| New unlinked quotation/order | No DCS relationship exists from which to infer a particular rejected position. These paths remain outside DCS-specific enforcement. A blanket mandatory-DCS policy is a separate scope decision. Do not claim universal coverage for standalone orders. |

Drafts can be printed outside submission workflows; this patch gates submitted quotation use, not every print/export or external communication. Direct database writes and external/legacy Server Scripts are outside the executed unit evidence. Verify active hooks and legacy endpoint disposition in staging before release.

## Executed evidence

Local Python unittest execution: **14 tests passed**, using the actual policy, authority, quotation/order and award functions with mocked Frappe boundaries. Covers recovered margin, ceiling, unchanged ordinary thresholds, repeated revisions, prior approval, current manager/amount validation, missing/unrelated/self/disabled manager, later approval, quotation submission, order conversion/validation, award refusal and link-removal refusal.

Command:

```sh
python -m unittest discover -s bsgroup/tests -p test_dcs_rejection_policy_unit.py -v
```

Python syntax compilation, JavaScript syntax and `git diff --check` passed. These are local checks, not site integration, HTTP or browser evidence.

## Written integration regressions — not executed in this review

Updated `test_dcs_manager_approval` and `test_dcs_audit_controls` replace the contrary assertions and cover fresh manager routing/tasks, unrelated/self decision refusal, exact-floor recovery, successive revisions, missing routes, preserved rejection decision fields/events, BOQ recovery and award/quotation/order gating before and after approval. The local runtime has no Frappe installation/site, so no bench test result is claimed.

## Controlled release gates

1. Review the diff and confirm the release branch has not advanced. Keep this PR unmerged until validation completes.
2. Apply the reviewed commit only to isolated staging. Run the manager approval, audit controls, BOQ revision, baseline, vendor revision, API/RPC, quotation access, governance and DCS DocType suites. Run existing UI tests and verify Reject → recovered revision → named manager → Approve → quotation/order/award in the browser.
3. Verify unchanged rejection history, a new current-revision approval event, no business email sends, manager-route error behavior and unchanged ceiling/delivery controls. Test link removal on real document saves, not just mocks.
4. Inspect the live deployed SHA read-only. PR #9's current description reports completed production deployment at e506605, contrary to the earlier pending report. That is a repository claim, not an independently verified production observation in this review.
5. Read-only inventory deals with an earlier rejection and a later recovery marked None without intervening approval, including awarded deals. Do not silently alter history, reverse awards or approve anything. Existing None recovery revisions have no manager snapshot and are intentionally blocked; use a genuine corrective governed revision and fresh approval after business review, or separately review an audited remediation migration. No automatic backfill is included.
6. Obtain/verify a current full backup, agree rollback and affected-record remediation, and approve the controlled release only after staging results are recorded. Deploy the reviewed app commit with framework versions pinned; then confirm hooks, deployed SHA and browser behavior without exercising business approvals.

No production access or mutation, merge, business approval or deployment was performed in this correction review.
