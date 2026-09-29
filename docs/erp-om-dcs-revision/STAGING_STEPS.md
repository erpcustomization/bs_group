# erp-om staging rehearsal: step by step on BITS-ERP

This guide is for the operator. Run it on BITS-ERP, the self-hosted bench at `~/bs_group`. Stop at each **⛔ STOP** until Mohan answers.

**Scope:**
- **Allowed:** a **new** local site, `erp-om-staging.local`.
- **Never touched:** `dcs-test.local` (the UAE REL-1 rehearsal site), erp-om, erp.bitssecureit.com and erp.siteexclusive.ae.

---

## Step 1: Approvals ⛔ STOP

Mohan approves, in writing:

1. **The backup to use.** In the Frappe Cloud dashboard, open Sites → `erp-om.k.frappe.cloud` → Backups. It must be taken **after 29 Sep 2026**, so that `DCS-MUSCAT-OVERSEAS-COMPANY-LLC-003-1` is in it. Note the three exact filenames (database, public files, private files).
2. **Using BITS-ERP** for this run. See the warning in Step 3.
3. **The desk-check user.** This is an erp-om user holding **Presales** or **Sales Manager** (or Commercial Controller / Managing Director). For example, Mohan's own user, if it holds one of those roles.

## Step 2: Check that the bench matches erp-om

In Frappe Cloud, open Bench Groups → **erpOM** → Apps and note each app's commit. On BITS-ERP, compare them:

```bash
cd ~/bs_group
for a in apps/*; do printf '%-16s %s\n' "$(basename $a)" "$(git -C $a log --oneline -1)"; done
```

- **frappe, erpnext and hrms** must match erp-om's commits. So must **helpdesk and telephony**, if erp-om has them.
- **erp-om has no `zoho_migration` and no `print_designer`.** It doesn't matter if they are on the bench. Just never install them on the staging site.
- **If a version differs ⛔ STOP.** Bring the bench to parity first (`git -C apps/<app> checkout <commit>`), or report the mismatch to Mohan.

## Step 3: Record the current state of BITS-ERP

> ⚠️ All sites on a bench share `apps/bsgroup`. This rehearsal moves it to `bb27213` and then to `9aa9c3a`. **Do not run it while a REL-1 test cycle on `dcs-test.local` is in progress.** Note the current commit so you can put it back afterwards (Step 11).

```bash
cd ~/bs_group
git -C apps/bsgroup log --oneline -1 | tee ~/bsgroup-commit-before-erp-om-rehearsal.txt
git -C apps/bsgroup status --short        # must be empty; stash nothing, ask if not clean
```

## Step 4: Get the code and the runbook

```bash
cd ~/bs_group/apps/bsgroup
git fetch origin main fix/dcs-vendor-revision claude/dcs-vendor-revision-erp-om-uys8c6
# copy the runbook OUT of the app checkout (the commits we check out later do not contain it)
mkdir -p ~/erp-om-rehearsal
git show origin/claude/dcs-vendor-revision-erp-om-uys8c6:docs/erp-om-dcs-revision/erp_om_staging_rehearsal.sh > ~/erp-om-rehearsal/run.sh
chmod +x ~/erp-om-rehearsal/run.sh
git checkout --detach bb27213            # what erp-om runs today
```

## Step 5: Download the approved backup

Download the three files from the Frappe Cloud dashboard into `~/erp-om-backup/`. Then set the variables below. Use them in **every** later step, in the same shell:

```bash
export SITE=erp-om-staging.local
export BENCH=~/bs_group
export BACKUPS=~/erp-om-backup
export BACKUP_DB='<exact>-database.sql.gz'
export BACKUP_PUB='<exact>-files.tar'
export BACKUP_PRIV='<exact>-private-files.tar'
export STAGING_ADMIN_PW='<new staging-only password>'
export DESK_USER='<erp-om user with Presales / Sales Manager>'
export DESK_USER_PW='<new staging-only password for that user>'
```

## Step 6: Run the rehearsal phases

Run one phase at a time, and check that each prints `PASS` before running the next.

```bash
~/erp-om-rehearsal/run.sh 0     # preflight: bench commits, bsgroup at bb27213
~/erp-om-rehearsal/run.sh 1     # restore + isolate (asks for the MariaDB root password on first site creation)
~/erp-om-rehearsal/run.sh 2     # pre-migrate baseline
```

**⛔ STOP after phase 2.** Send Mohan these files from `~/erp-om-rehearsal-evidence/`:

- `counts-pre-migrate.psv`
- `fact-cost-overrun-policy.txt`: the current overrun setting, which migrate will change to None
- `fact-patch-log-pre.txt`: must list the 4 older `bsgroup.patches.*` patches
- `fact-uae-only.txt`
- `target-pre-migrate.psv`: should show cost 913.67 and selling 1659.80

```bash
~/erp-om-rehearsal/run.sh 3     # migrate to 9aa9c3a
```

If phase 3 fails, **⛔ STOP**. Send `migrate-output.txt` and `bsg-rel-1-log.txt`, and do not retry.

```bash
~/erp-om-rehearsal/run.sh 4     # the four DCS test modules
```

**Expected result of phase 4:**

- `test_dcs_api`, `test_dcs_po_scope_match` and `test_dcs_rpc_binding`: **OK**.
- `test_dcs_vendor_revision`: probably **not OK**, but only in `test_cost_only_amendment_flow_keeps_quoted_and_repoints_the_draft_quotation`. That test needs a "UAE VAT 5%" tax template, which erp-om does not have. Any **other** failure is real, so **⛔ STOP** and send `tests.txt`.

## Step 7: Desk check (the OMR 100 consulting charge)

```bash
~/erp-om-rehearsal/run.sh 5     # must show can_vendor_side = 1
cd ~/bs_group && bench serve --port 8001     # keep running in a second terminal
```

Open `http://<BITS-ERP host>:8001` in a browser and log in as `$DESK_USER` with `$DESK_USER_PW`. Take a screenshot at each step:

1. Open **DCS-MUSCAT-OVERSEAS-COMPANY-LLC-003-1**. There should be a **Negotiation** button with **Vendor Revision** in it.
2. Click Negotiation → **Vendor Revision**. Enter:
   - New Total Cost: **1013.67**
   - Reason: **Consulting charge OMR 100**

   Then click **Apply Revision**.
3. You should see a green **"Recorded"** message, and the form reloads.
4. Open the linked Quotation. It should still show this DCS, with its status unchanged.
5. **Extra check for condition C4:** open any **other**, older submitted DCS. Change one field that is editable after submit, click **Update**, and screenshot the result, whether it errors or succeeds. Then reload the form without saving anything else.

Then run:

```bash
~/erp-om-rehearsal/run.sh 5 verify
```

Expected result:

- **Working cost:** 1013.67
- **Margin:** 38.928%
- **Approval state / margin gate:** "In Negotiation" / "Clear"
- **New rows:** +2 DCS Revision and +1 Governance Event
- **Unchanged:** submitted totals 913.67 / 1659.80 and the Quotation link

## Step 8: Summary

```bash
~/erp-om-rehearsal/run.sh 6
```

## Step 9: The party dry-run report

The migrate in phase 3 wrote this report:

```bash
ls ~/bs_group/sites/erp-om-staging.local/private/files/bsg-rel-1-party-backfill-dry-run-*.csv
```

Send it to Mohan. The rows with `customer_cleared = 1` are the records whose `customer` would be cleared the next time a user saves them.

## Step 10: Send the evidence to Mohan

```bash
tar -czf ~/erp-om-rehearsal-evidence-$(date +%Y%m%d).tgz -C ~ erp-om-rehearsal-evidence
```

Add the screenshots and the CSV from Step 9. Mohan then makes the GO / NO-GO decision (README §4).

## Step 11: Clean up

Put BITS-ERP back the way it was:

```bash
cd ~/bs_group/apps/bsgroup && git checkout --detach "$(cut -d' ' -f1 ~/bsgroup-commit-before-erp-om-rehearsal.txt)"
cd ~/bs_group && bench build --app bsgroup
```

- **Keep `erp-om-staging.local`** until Mohan decides. It holds erp-om business data, so drop it afterwards: `bench drop-site erp-om-staging.local`.
- **Delete `~/erp-om-backup/`** once the decision is made.
- **Do not migrate `dcs-test.local`** as part of this cleanup.
