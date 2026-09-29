# erp-om: DCS Vendor/Customer Revision: readiness, rehearsal, deployment options

- **Candidate:** `fix/dcs-vendor-revision` @ `9aa9c3a` (merge-base with `main` = `bb27213`, 32 commits, 84 files)
- **Target:** erp-om (`erp-om.k.frappe.cloud`, bench group erpOM, bench-41009), which runs `bsgroup` `main` @ `bb27213` today
- **Prepared:** 29 Sep 2026, for Mohan (approver for every production step)
- **Status:** static review done. Staging rehearsal **not yet run**; see §2. **No production action has been taken.**

---

## 0. Verdict (current)

| Gate | Result | Evidence |
|---|---|---|
| G1 Static readiness review of 9aa9c3a for erp-om | **PASS, with 5 conditions** (§1.4) | this document |
| G2 Party backfill stays dry-run on `bench migrate` | **PASS** (code-verified) | §1.2 |
| G3 No hard dependency on UAE-only customisations | **PASS** for the app code. Test fixture is UAE-specific (§1.3, U-1) | §1.3 |
| G4 Staging rehearsal: migrate, 4 test modules, desk check, counts | **NOT RUN.** Needs an approved erp-om backup and a staging bench (see §2) | `erp_om_staging_rehearsal.sh` |
| **GO / NO-GO for erp-om production** | **NO-GO until G4 passes.** With G4 passing and conditions C1 to C5 accepted: **GO for option (a)** | §3, §4 |

Why G4 is not run: this work ran in an isolated cloud container. It has no Frappe Cloud credentials, no copy of an erp-om backup, and no bench. I did not create evidence for it. The runbook in this folder runs G4 end to end and writes PASS/FAIL result files. It is guarded so that it refuses production and third-party site names.

---

## 1. Readiness review of `9aa9c3a` for erp-om

### 1.1 What `bench migrate` would run against erp-om data

`bsgroup/patches.txt` on the branch, in execution order. The four legacy post-model-sync patches are already on `main`, so erp-om's Patch Log should list them and they will not run again. Rehearsal phase 2 verifies this.

| # | Stage | Patch | Reads | **Writes** | Expected on erp-om |
|---|---|---|---|---|---|
| 1 | pre-sync | `v0_1.reconcile_handover_condition_doctype` | `DocType`/`DocField` for *DCS Handover Condition*, table columns, row names | If the DocType is `custom=1` and matches the committed schema, it changes only the `DocType` row: `custom→0`, `module→BS Group`, `modified`, `migration_hash`. Also writes an Error Log entry `BSG-REL-1`. On a schema mismatch it **throws before changing anything**, and migrate aborts. | On erp-om the DocType came from the app (`main` ships it), so it is already standard. Expected result: **no-op** plus 1 log entry. |
| 2 | pre-sync | `v0_1.fold_governance_change_rows` | raw `tabDCS Governance Event Change` | Copies legacy child rows into the parent event's `changes` JSON and `change_count` (`db.set_value`, `update_modified=False`). This happens only for parents whose `changes` is empty. It deletes nothing and writes 1 Error Log summary. | `main` already has `changes` as JSON, and erp-om has no Server Scripts to write child rows. Expected: **0 rows / `empty`**. Phase 2 records the actual count. |
| (model sync) | | DocType JSON import | | See §1.1a | |
| 3 | post-sync | `migrate_tech_task_scheduler_status`, `set_missing_lead_company`, `share_existing_tech_task_scheduler_assignments`, `backfill_task_completed_on` | | Nothing if they are already in the Patch Log (they ship on `main`) | **skip** |
| 4 | post-sync | `v0_1.verify_handover_condition_doctype` | meta, columns, controller class, snapshot from #1 | Error Log only. **Throws** if the DocType is not standard, a field or column is missing, `autoname` differs, or the controller is not `DCSHandoverCondition`. | pass. The JSON is unchanged since `main`. |
| 5 | post-sync | `v0_1.drop_orphan_governance_change` | child DocType, links, row count | **Deletes the `DCS Governance Event Change` DocType** only when it has **0 rows and no links**. Otherwise it logs and keeps it. | Likely deletes it (0 rows expected). Note that the app no longer ships its JSON, so Frappe's orphan sweep would remove the metadata anyway. |
| 6 | post-sync | `v0_1.lock_pcb_until_g_pcb` | `BS Group Settings.cost_overrun_policy` | Sets **`cost_overrun_policy` to `None`** when it is not already `None`, and logs the previous value. | **Behaviour change** if erp-om uses `Warn`/`Block`: PO, PI, Expense Claim and Labor Preapproval overrun checks stop. Phase 2 records the prior value. |
| 7 | post-sync | `v0_1.backfill_party_fields` | every Presales Request and Deal Cost Sheet, their Opportunity, Customer, Lead | **No record writes** (dry run). It writes a CSV to `sites/<site>/private/files/bsg-rel-1-party-backfill-dry-run-<ts>.csv` (a file on disk, not a File doc) and 1 Error Log summary. | dry-run, `applied: 0` |
| 8 | post-sync | `v0_1.normalize_po_scope_match` | `Deal Cost Sheet.custom_po_scope_match` | Raw SQL `UPDATE` from ASCII-hyphen `Mismatch - …` to en-dash `Mismatch – …`. It changes only that column. | Expected **0 rows**, because `dcs_po_reconcile` never ran on erp-om. Phase 2 lists the values. |

#### 1.1a Schema and permission changes from the model sync (not patches, but they write to erp-om)

- **Deal Cost Sheet and Presales Request**
  - New mandatory fields: `party_type`, `party` and `organisation_name`. `customer` becomes read-only and is derived from the party.
  - The DCS naming rule becomes "Expression (old style)". The controller names sheets `DCS-<organisation slug>-###`, which gives the same names as before for existing Customers.
  - The select field `custom_po_scope_match` gains the option `Mismatch – Different Scope`.
- **DCS Governance Event**
  - Adds four read-only columns: `source_event_id` (indexed), `revision_no`, `revision_reference` and `evidence_reference`.
  - `actor`, `event_timestamp`, `correlation_id` and `changes` become required.
  - **Permissions:** System Manager loses create, write and delete (read, export and print remain). Read and report are added for Sales Manager, **Commercial Controller** and **Managing Director**.
- **Project Cost Baseline:** permissions are reduced to **System Manager only**, so **Sales Manager and Project Manager lose access**. This is the G-PCB lock.
- **BS Group Settings:** the three `enable_dcs_*_guard` checkboxes are removed. The guards are now **always on**:
  - one active DCS per Opportunity (on insert and on submit)
  - the governed-field guard, which blocks Desk/REST edits to the commercial control fields
  - the record-authority guard
- **New DocType:** Party Backfill Run (System Manager only).
- **Removed DocType:** DCS Governance Event Change (see #5).
- **Smaller changes:** Labor Line Item and Labor Preapproval (the mobile view) change, and `labor_preapproval.css` is added to `app_include_css`. `before_request` and `before_job` now reset the governance correlation id.
- **Fixtures:** the Property Setter fixtures are unchanged from `main`, so the re-sync adds nothing.
- **Custom DocPerm:** if erp-om has any Custom DocPerm rows on these DocTypes, they override the JSON permissions above. Phase 2 counts them.

### 1.2 Party backfill stays dry-run: confirmed from code

- The Frappe patch runner calls `execute()` with no arguments. In `backfill_party_fields.execute(apply=False)`, `apply = bool(apply)` evaluates to `False`, so there are **no `set_value` calls**. The site-config flag `bsg_apply_party_backfill` is **no longer read** by this patch.
- Only an explicit `bench execute … --kwargs '{"apply": true}'` applies the bulk path. Per the H-1 rule, that must never be run on erp-om: that path *can* clear `customer`, and its report column `customer_cleared` counts exactly that.
- The per-record manifest runner `bsgroup.utils.party_backfill`:
  - is **not** in `patches.txt` and is not whitelisted
  - runs only when a `Party Backfill Run` document is inserted by a System Manager
  - writes only in Apply/Restore mode, with `bsg_apply_party_backfill` set **and** a matching manifest SHA-256
  - removes the flag again in `finally`

  Nothing on migrate reaches it.
- **Related risk: records can change on their next ordinary save.**
  - After migrate, any **full save** of a draft DCS or Presales Request runs `apply_party_model`. That fills the party from the Opportunity and, when the Opportunity is from a **Lead**, sets `customer` to NULL. This is not the backfill; it is the new controller behaviour.
  - The dry-run CSV column `customer_cleared=1` lists exactly the records this would affect when next saved.
  - **Mohan should read that CSV from the staging run before go-live** (condition C3).

### 1.3 UAE-only assumptions

| Item | Finding |
|---|---|
| `zoho_migration` | **No reference** in any code the branch adds. The existing Quotation custom field `zoho_estimate_id` (in `bs_group/custom/quotation.json`) is unchanged from `main`, so erp-om already has it. |
| `print_designer` | **No reference** in the branch changes. The print formats are unchanged from `main`. |
| `Address.emirate` | **No reference** anywhere in the branch. |
| Server Scripts | The app code never reads or calls Server Scripts. `bsgroup/dcs/server_script_export/` holds reference exports only; nothing imports them. The client resolves every call through `DCS_METHODS` to `bsgroup.api.dcs.*`, and the bare `dcs_*` names are gone. **This is the actual fix for erp-om.** |
| Roles `Commercial Controller` and `Managing Director` | They are referenced in the role checks and in the DCS Governance Event DocPerms. If erp-om lacks them, Vendor Revision still works for **Presales / Sales Manager**, and Customer Revision works for **Sales User / Sales Manager**. **System Manager alone is refused by design**, so the desk-check user needs one of these roles. Phase 2 counts the roles. |
| **U-1: "UAE VAT 5%" template** | This lookup is pre-existing on `main` in `make_quotation` and in `quotation.js`. On erp-om it finds nothing, so no VAT is auto-filled on quotations made from a DCS. The **new test** `IntegrationTestDCSAmendmentFlow.test_cost_only_amendment_flow_…` builds a strict Quotation with that template. Because `Quotation.taxes_and_charges` is mandatory (bsgroup property setter), the test is **expected to ERROR on an erp-om copy** unless a template named `%UAE VAT 5%` exists. If it gets past that, it **skips**, because erp-om has no "Quotation - Link Back to DCS" Server Script. **Classify this as an environment result, not an app defect.** The other tests in that module and the other three modules have no UAE dependency. |
| AED in the DCS form JS | Pre-existing on `main` (the `Cost (AED)` headers in the AI-assist panel, and `currency \|\| 'AED'`). Cosmetic, and unchanged by the branch. |

### 1.4 Conditions for GO (what Mohan accepts or acts on)

- **C1:** Accept that `cost_overrun_policy` becomes `None`, and that Project Cost Baseline becomes System-Manager-only on erp-om (the G-PCB lock). Record the prior value from phase 2 so it can be restored after G-PCB.
- **C2:** Accept the always-on guards on erp-om:
  - one active DCS per Opportunity
  - no Desk edits to the governed commercial fields
  - the record-authority guard
- **C3:** Review the dry-run CSV. List every `customer_cleared=1` row and decide per record *before* anyone re-saves it. Correct those rows only through a Party Backfill Run manifest, as a separate approval.
- **C4:** Legacy **submitted** sheets have an empty `party`, because nothing is backfilled.
  - The governed services write with `db.set_value`, so revisions, approval and award are unaffected. The desk check proves this on the target sheet.
  - A Desk **"Update"** (update-after-submit) on such a sheet is expected to fail. The mandatory `party` fields are empty, and deriving them from the Opportunity changes non-`allow_on_submit` fields.
  - Rehearsal task: try one Desk update on a legacy submitted sheet in staging and record the result.
- **C5:** The desk-check user holds Presales, Sales Manager, Commercial Controller or Managing Director, plus write on Deal Cost Sheet.

---

## 2. Staging rehearsal (to be run; the runbook is ready)

**Where it runs:** on a **self-hosted staging bench**, for example BITS-ERP, whose frappe, erpnext, hrms, helpdesk and telephony commits match erp-om's bench group.

- **Not on a site in the erpOM bench group:** every site there runs the same `bsgroup` commit as production.
- **Not on Stage-BitsSecureIT / erp.siteexclusive.ae:** that is a live third-party site.
- **Frappe Cloud alternative:** use a separate new bench group that pins `bsgroup` to `fix/dcs-vendor-revision`. Restoring into it runs migrate immediately, so baseline counts must be taken by first restoring onto a bench at `bb27213`.

**Runbook:** `docs/erp-om-dcs-revision/erp_om_staging_rehearsal.sh`. Run one phase per call; results go to `~/erp-om-rehearsal-evidence/<n>.result`. The script refuses `erp-om.*`, `erp.bitssecureit.com`, `*siteexclusive*` and `*.frappe.cloud` site names.

| Phase | What it does | PASS criterion |
|---|---|---|
| 0 preflight | Records the bench app commits and checks that bsgroup is at `bb27213` | Commits recorded; Mohan compares them with the erp-om app list |
| 1 restore | Restores the **approved** erp-om backup (exact filenames plus sha256), then pauses the scheduler, mutes email, turns off webhooks, rotates the admin password and sets `allow_tests` | Restore succeeds |
| 2 baseline | Takes counts: DocTypes, Deal Cost Sheet, DCS Revision, DCS Governance Event and Quotation, plus Presales Request, Handover Condition, legacy change rows, PCB, Server Scripts, roles, Custom DocPerm, blank-party rows and `cost_overrun_policy`. Records per-patch facts, UAE-only probes and the target sheet row. | Target sheet present |
| 3 migrate | Checks out `9aa9c3a`, runs `bench migrate`, builds, captures the Patch Log and the `BSG-REL-1` log, then takes counts again | Migrate OK; party backfill `mode: dry-run`, `applied: 0`; target totals, Quotation link and status unchanged |
| 4 tests | Runs the four modules one at a time, then takes counts again | All four OK, **or** the only non-OK result is U-1 (classify it) |
| 5 deskcheck | Checks that `dcs_screen3` returns `can_vendor_side=1` for `DESK_USER`. Then **manual in the browser:** Negotiation, then Vendor Revision with new total cost **1,013.67** and reason **"Consulting charge OMR 100"**. Screenshots. Then `5 verify`. | See the expected values below |
| 6 summary | Prints the counts table (pre-migrate, post-migrate, post-tests, final) and all phase results | — |

**Expected desk-check result on `DCS-MUSCAT-OVERSEAS-COMPANY-LLC-003-1`.** These values are computed with the service's own rounding.

| Field | Before | After |
|---|---|---|
| `docstatus` | 1 | 1 (unchanged; no cancel or amend) |
| `total_cost` / `total_selling` (submitted baseline) | 913.67 / 1,659.80 | **unchanged** |
| `custom_working_total_cost` | — | **1,013.67** |
| `custom_working_total_selling` | — | 1,659.80 |
| `custom_working_margin_percent` | — (header margin 44.95%) | **38.928** (GP 646.13) |
| `custom_approval_state` / `custom_margin_gate` | — | **In Negotiation / Clear** (0% concession, margin ≥ 20% floor) |
| DCS Revision rows for the sheet | n | **n+2** if this is the sheet's first revision: R1 is the automatic "Internal" baseline and R2 is the Vendor revision. Otherwise n+1. |
| DCS Governance Event rows | m | **m+1** (`DCS_REVISION_APPLIED`, reason "Consulting charge OMR 100") |
| `custom_quotation` / `custom_deal_status` | as is | **unchanged**; the Quotation still points to this sheet |

**Count deviations to expect:**

- **DocType:** +1 (Party Backfill Run) and −1 (DCS Governance Event Change, if dropped), so net 0 or +1.
- **Error Log `BSG-REL-1`:** +5 to 7.
- **Role:** may gain Commercial Controller or Managing Director if the sync or tests create them.
- **After tests:** `ZZTEST-*` fixtures if a test commits.
- **Deal Cost Sheet, DCS Revision, DCS Governance Event and Quotation:** migrate must not change them (**0 delta**). Only the desk check adds the +2/+1 above.

---

## 3. Deployment options memo (for Mohan to choose)

### (a) Point the erpOM bench group at `fix/dcs-vendor-revision` (recommended for erp-om)

- **Reach:** erp-om only. UAE (LiveBitSecure) and Stage-BitsSecureIT stay on `main`.
- **Fit:** erp-om has **no Server Scripts**, so the double-audit risk does not exist there. This is the smallest change that fixes the defect.
- **Steps (each needs separate approval):**
  1. Take a fresh erp-om backup.
  2. Change the erpOM app source to `fix/dcs-vendor-revision` pinned at `9aa9c3a`.
  3. Deploy, which runs migrate.
  4. Check the Error Log `BSG-REL-1` entries against the staging run.
  5. Do the desk check on production: the Vendor Revision on `…-003-1`.
- **Rollback:** repoint to `main` @ `bb27213` and redeploy, or restore the pre-deploy backup. Repointing alone does **not** undo the schema and data changes:
  - the new columns
  - the `cost_overrun_policy` value
  - the folded JSON
  - the dropped empty child DocType

  The backup is the real rollback.
- **Cost:** erp-om runs a non-`main` branch until the release reaches `main`. Later fixes must land on this branch, or erp-om must be repointed. Do not rewrite or force-push the branch while erp-om tracks it.

### (b) Merge to `main`

- **Reach:** all three bench groups that deploy `bsgroup` from this repo: erpOM, **LiveBitSecure (UAE)** and **Stage-BitsSecureIT (erp.siteexclusive.ae)**. Each one gets it on its next deploy.
- **UAE:** the legacy DCS Server Scripts are still enabled there. Deploying the app alone would double-audit every governed action. The UAE needs the **bundled change in one window**:
  1. the app code
  2. retiring the 13 overlapping Server Scripts (see `bsgroup/dcs/server_script_export/script_disposition_register.csv` and `deletion_manifest.csv`)
  3. repointing "Quotation - Link Back to DCS and Close Presales" to the app endpoint
- **Stage-BitsSecureIT:** a live third-party site. It needs its own owner's agreement and its own window.
- **Conclusion:** (b) is not an erp-om fix. It is the UAE REL-1 release and should be approved and scheduled as that.

**Recommendation:**

1. Do (a) for erp-om once G4 passes.
2. Keep (b) as the separate UAE bundled release. Until it ships, pause auto-deploy on the LiveBitSecure and Stage-BitsSecureIT groups for any `main` push, so nobody merges early by accident.

---

## 4. What happens next (each step needs Mohan's approval)

1. Approve an erp-om backup for staging, and approve the staging bench.
2. Run phases 0 to 6. Send the evidence folder, including `tests.txt`, the `counts-table.txt` table, the dry-run CSV and the screenshots.
3. Re-evaluate this verdict:
   - **GO for (a)** if phases 3, 5 and 6 PASS, and phase 4 is OK apart from U-1.
   - **NO-GO** on any migrate failure, a non-zero `applied`, any change to the target sheet from migrate, or a desk-check mismatch.
4. Production (a), following the steps in §3(a).
5. First production use: the Vendor Revision on `DCS-MUSCAT-OVERSEAS-COMPANY-LLC-003-1` to 1,013.67 with the reason "Consulting charge OMR 100".

**Open housekeeping on erp-om (Mohan):**

- Untick Cancel and Amend for System Manager on Deal Cost Sheet (Role Permissions Manager, level 0).
- Submit LPRE-2026-0002 (Hormuz labour OMR 89).
