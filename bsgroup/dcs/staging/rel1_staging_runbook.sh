#!/usr/bin/env bash
# rel-1 staging runbook - dcs-test.local on BITS-ERP (~/bs_group)
#
# FIRST copy this directory out of the app checkout (phase 3 checks out 231ff58,
# which does not contain it):   cp -r bsgroup/dcs/staging ~/rel1 && cd ~/rel1
# Run ONE PHASE AT A TIME:  bash ~/rel1/rel1_staging_runbook.sh <phase>
# Every phase prints evidence to ~/rel1-evidence/<phase>-<timestamp>.log and
# stops on the first failing check. Nothing here touches production; the only
# production interaction is downloading the Frappe Cloud backup (phase 1, by hand).
#
# Phases
#   0  preserve-check   : prove dcs-test.local holds nothing to keep (STOP if it does)
#   1  restore          : restore the FC backup (db + public + private files) into dcs-test.local
#   2  isolate          : scheduler off, email off, webhooks off, integration scripts off, dev mode off
#   3  baseline-commit  : deploy the production commit 231ff58 + migrate + build
#   4  parity           : compare the site with production_baseline_2026-09-12.psv (STOP on mismatch)
#   5  prefix-tests     : pre-fix scenarios on 231ff58 (record the OBSERVED column of Section 7)
#   6  deploy-rel1      : fetch the release branch, checkout, migrate (patches run), build
#   7  postfix-tests    : automated test modules + post-fix scenarios
#   8  backfill-dryrun  : party backfill report (dry run) - no data change
#   9  retire-rehearsal : one script at a time: disable, rerun scenario, re-enable (S-24 pattern)
set -euo pipefail
SITE=dcs-test.local
BENCH=~/bs_group
EVID=~/rel1-evidence
PROD_COMMIT=231ff58
REL_BRANCH=fix/dcs-core-release-1
HERE=$(cd "$(dirname "$0")" && pwd)
probe() { cd "$BENCH/sites" && ../env/bin/python "$HERE/prefix_probes.py" "$SITE" "$1"; }
mkdir -p "$EVID"
PHASE="${1:-}"
TS=$(date +%Y%m%d-%H%M%S)
LOG="$EVID/${PHASE:-none}-$TS.log"
exec > >(tee -a "$LOG") 2>&1
echo "== rel-1 staging runbook phase '$PHASE' at $(date -Is) on $(hostname) =="

sql() { cd "$BENCH" && bench --site "$SITE" mariadb -e "$1" 2>/dev/null; }
need() { command -v "$1" >/dev/null || { echo "MISSING: $1"; exit 2; }; }

case "$PHASE" in
0|preserve-check)
	cd "$BENCH"
	echo "-- sites"; ls sites; cat sites/currentsite.txt 2>/dev/null || true
	if [ ! -d "sites/$SITE" ]; then echo "$SITE does not exist - nothing to preserve"; exit 0; fi
	echo "-- apps on $SITE"; bench --site "$SITE" list-apps || true
	echo "-- what is on $SITE now (record counts + latest modified)"
	sql "select 'DCS',count(*),max(modified) from \`tabDeal Cost Sheet\` union all select 'PR',count(*),max(modified) from \`tabPresales Request\` union all select 'GovEvent',count(*),max(modified) from \`tabDCS Governance Event\` union all select 'Customer',count(*),max(modified) from \`tabCustomer\` union all select 'Project',count(*),max(modified) from \`tabProject\` union all select 'User',count(*),max(modified) from \`tabUser\` union all select 'File',count(*),max(modified) from \`tabFile\` union all select 'ServerScript',count(*),max(modified) from \`tabServer Script\`;" || echo "(site not queryable)"
	echo "-- rows modified in the last 30 days on $SITE (anything here is a candidate to preserve)"
	sql "select 'DCS',count(*) from \`tabDeal Cost Sheet\` where modified > now() - interval 30 day union all select 'PR',count(*) from \`tabPresales Request\` where modified > now() - interval 30 day union all select 'Customer',count(*) from \`tabCustomer\` where modified > now() - interval 30 day;" || true
	du -sh "sites/$SITE/private/files" "sites/$SITE/public/files" 2>/dev/null || true
	echo "STOP: a human confirms from this log that nothing above needs to be kept before phase 1."
	;;
1|restore)
	# Download from Frappe Cloud > Site > Backups > "Backup on Sat, Sep 12, 2026 12:58 AM" (database, public, private)
	# into ~/rel1-backup/ first. Filenames look like: <ts>-erp_bitssecureit_com-database.sql.gz, -files.tar, -private-files.tar
	cd "$BENCH"
	DB=$(ls ~/rel1-backup/*database.sql.gz | head -1); PUB=$(ls ~/rel1-backup/*-files.tar | grep -v private | head -1); PRIV=$(ls ~/rel1-backup/*private-files.tar | head -1)
	echo "db=$DB"; echo "public=$PUB"; echo "private=$PRIV"
	sha256sum "$DB" "$PUB" "$PRIV"
	# restore destroys and recreates the site's database; phase 0 must have been accepted
	bench --site "$SITE" restore "$DB" --with-public-files "$PUB" --with-private-files "$PRIV"
	echo "restore finished $(date -Is)"
	;;
2|isolate)
	cd "$BENCH"
	bench --site "$SITE" set-config developer_mode 0
	bench --site "$SITE" set-config pause_scheduler 1
	bench --site "$SITE" scheduler disable || true
	bench --site "$SITE" set-config mute_emails 1
	bench --site "$SITE" set-config disable_website_cache 1
	# outgoing/incoming mail, webhooks, integration scripts - staging only
	sql "update \`tabEmail Account\` set enable_outgoing=0, enable_incoming=0, awaiting_password=1;"
	sql "update \`tabWebhook\` set enabled=0;"
	sql "update \`tabServer Script\` set disabled=1 where disabled=0 and (name like 'zoho%' or name like 'Zoho%' or name like 'aira%' or name like 'AIRA%' or name like 'Outlook%' or name like 'outlook%' or name like 'Teams%' or name = 'fleet_gps_ingest' or name like 'sync_%_to_zoho' or name = 'org_chart_data');"
	# staging-only credentials mask: any *Settings single holding tokens/secrets gets blanked
	sql "update \`tabSingles\` set value='' where field regexp 'token|secret|client_id|client_secret|api_key|password|webhook_url|refresh' and doctype not in ('System Settings','Website Settings');"
	bench --site "$SITE" set-admin-password admin
	bench --site "$SITE" clear-cache
	echo "-- isolation state"
	sql "select 'EmailAccount',count(*),sum(enable_outgoing),sum(enable_incoming) from \`tabEmail Account\` union all select 'Webhook',count(*),sum(enabled) from \`tabWebhook\` union all select 'ServerScript',count(*),sum(disabled) from \`tabServer Script\`;"
	cat "sites/$SITE/site_config.json" | grep -E 'developer_mode|pause_scheduler|mute_emails' || true
	;;
3|baseline-commit)
	cd "$BENCH/apps/bsgroup"
	git fetch origin
	git status --short | head -20
	git checkout --detach "$PROD_COMMIT"
	git log --oneline -1
	cd "$BENCH"
	bench --site "$SITE" migrate
	bench build --app bsgroup
	bench restart || true
	bench --site "$SITE" list-apps
	;;
4|parity)
	cd "$BENCH"
	echo "-- staging values (compare with production_baseline_2026-09-12.psv; the ServerScript disabled count will differ by the phase-2 integration disables)"
	sql "select concat_ws('|','DocType',count(*),max(modified)) r from \`tabDocType\` union all select concat_ws('|','CustomField',count(*),max(modified)) from \`tabCustom Field\` union all select concat_ws('|','PropertySetter',count(*),max(modified)) from \`tabProperty Setter\` union all select concat_ws('|','ServerScript',count(*),sum(disabled),max(modified)) from \`tabServer Script\` union all select concat_ws('|','ClientScript',count(*),max(modified)) from \`tabClient Script\` union all select concat_ws('|','DocPerm_DCS',count(*)) from \`tabDocPerm\` where parent='Deal Cost Sheet' union all select concat_ws('|','DocPerm_PR',count(*)) from \`tabDocPerm\` where parent='Presales Request' union all select concat_ws('|','DocPerm_PCB',count(*)) from \`tabDocPerm\` where parent='Project Cost Baseline' union all select concat_ws('|','DocPerm_GE',count(*)) from \`tabDocPerm\` where parent='DCS Governance Event' union all select concat_ws('|','DocPerm_HC',count(*)) from \`tabDocPerm\` where parent='DCS Handover Condition' union all select concat_ws('|','CustomDocPerm_all',count(*)) from \`tabCustom DocPerm\` union all select concat_ws('|','PR',count(*),sum(docstatus=2),max(modified)) from \`tabPresales Request\` union all select concat_ws('|','PR_badcustomer',count(*)) from \`tabPresales Request\` p where not exists (select 1 from \`tabCustomer\` c where c.name=p.customer) union all select concat_ws('|','PR_duedate',count(*)) from \`tabPresales Request\` where due_date is not null union all select concat_ws('|','DCS',count(*),sum(docstatus=0),sum(docstatus=1),sum(docstatus=2),max(modified)) from \`tabDeal Cost Sheet\` union all select concat_ws('|','DCS_dangling_PR',count(*)) from \`tabDeal Cost Sheet\` d where ifnull(d.presales_request,'')<>'' and not exists (select 1 from \`tabPresales Request\` p where p.name=d.presales_request) union all select concat_ws('|','GovEvent',count(*),sum(ifnull(actor,'')=''),max(modified)) from \`tabDCS Governance Event\` union all select concat_ws('|','HandoverCond',count(*),max(modified)) from \`tabDCS Handover Condition\` union all select concat_ws('|','Revision',count(*),max(modified)) from \`tabDCS Revision\` union all select concat_ws('|','AwardReversal',count(*)) from \`tabDCS Award Reversal\` union all select concat_ws('|','PCB',count(*)) from \`tabProject Cost Baseline\` union all select concat_ws('|','Opportunity',count(*)) from \`tabOpportunity\` union all select concat_ws('|','Customer',count(*)) from \`tabCustomer\` union all select concat_ws('|','Lead',count(*)) from \`tabLead\` union all select concat_ws('|','Project',count(*)) from \`tabProject\` union all select concat_ws('|','Quotation',count(*)) from \`tabQuotation\` union all select concat_ws('|','HDTicket',count(*)) from \`tabHD Ticket\` union all select concat_ws('|','Communication',count(*)) from \`tabCommunication\` union all select concat_ws('|','HC_doctype',custom,module,autoname) from \`tabDocType\` where name='DCS Handover Condition' union all select concat_ws('|','BSGS',field,ifnull(value,'')) from \`tabSingles\` where doctype='BS Group Settings' and field in ('cost_overrun_policy','enable_dcs_one_active_guard','enable_dcs_governed_field_guard','enable_dcs_record_authority_guard','dcs_addtional_item');"
	echo "-- disabled-name list hash (compare with production: sort names of disabled scripts, sha256)"
	sql "select name from \`tabServer Script\` where disabled=1 order by name;" | tail -n +2 | sha256sum
	echo "-- DCS Governance Event.changes fieldtype"; sql "select fieldname,fieldtype from \`tabDocField\` where parent='DCS Governance Event' and fieldname='changes';"
	echo "-- bsgroup commit"; git -C "$BENCH/apps/bsgroup" log --oneline -1
	;;
5|prefix-tests)
	cd "$BENCH"
	echo "Pre-fix scenarios on $PROD_COMMIT. Record OBSERVED behaviour; do not fix anything here."
	echo "S-14 (endpoint without permission):"; bench --site "$SITE" execute frappe.client.get_list --kwargs "{'doctype':'DCS Governance Event','limit_page_length':1}" || true
	for pr in s22_direct_governance_insert s22a_edit_delete_event s23a_presales_sync_whitelisted s04_duplicate_dcs s14_helper_permissions s01_pr_from_lead s19_handover_controller s16_scheduler_touch; do
		echo "--- probe $pr"; probe "$pr" || echo "probe $pr raised (see above)"
	done
	echo "S-16/S-18/S-19/S-21 are UI scenarios - run through the workspace as the ZZTEST users and record in Section 7."
	;;
6|deploy-rel1)
	cd "$BENCH/apps/bsgroup"
	git fetch origin "$REL_BRANCH" || { echo "branch not on origin: fetch the bundle instead: git fetch ~/rel1/fix-dcs-core-release-1.bundle $REL_BRANCH:$REL_BRANCH"; git fetch ~/rel1/fix-dcs-core-release-1.bundle "$REL_BRANCH:$REL_BRANCH"; }
	git checkout "$REL_BRANCH"
	git log --oneline -12
	cd "$BENCH"
	bench --site "$SITE" migrate 2>&1 | tee "$EVID/migrate-rel1-$TS.log"
	echo "-- patch + BSG-REL-1 logs"
	sql "select name, patch from \`tabPatch Log\` where patch like 'bsgroup.patches.v0_1%' order by creation;"
	sql "select creation, left(replace(error,'\n',' / '),400) from \`tabError Log\` where method='BSG-REL-1' order by creation;"
	sql "select custom,module,autoname from \`tabDocType\` where name='DCS Handover Condition'; select count(*) from \`tabDCS Handover Condition\`;"
	bench build --app bsgroup
	bench restart || true
	;;
7|postfix-tests)
	cd "$BENCH"
	for m in bsgroup.bs_group.doctype.dcs_governance_event.test_dcs_governance_event bsgroup.api.dcs.test_dcs_api bsgroup.bs_group.doctype.presales_request.test_presales_request bsgroup.bs_group.doctype.deal_cost_sheet.test_deal_cost_sheet bsgroup.bs_group.doctype.dcs_handover_condition.test_dcs_handover_condition; do
		echo "=== $m"; bench --site "$SITE" run-tests --module "$m" 2>&1 | tail -40
	done
	echo "--- post-fix probes (same probes as phase 5; expected outcomes flip)"
	for pr in s22_direct_governance_insert s22a_edit_delete_event s23a_presales_sync_whitelisted s04_duplicate_dcs s14_helper_permissions s01_pr_from_lead s19_handover_controller s16_scheduler_touch; do
		echo "--- probe $pr"; probe "$pr" || echo "probe $pr raised (see above)"
	done
	echo "-- ZZTEST residue (tests roll back; anything left is listed here for cleanup)"
	sql "select 'DCS',count(*) from \`tabDeal Cost Sheet\` where name like 'DCS-ZZTEST%' union all select 'PR',count(*) from \`tabPresales Request\` where name like 'PR-ZZTEST%' union all select 'Customer',count(*) from \`tabCustomer\` where name like 'ZZTEST%';"
	;;
8|backfill-dryrun)
	cd "$BENCH"
	bench --site "$SITE" execute bsgroup.patches.v0_1.backfill_party_fields.execute --kwargs "{'apply': False}"
	ls -la "sites/$SITE/private/files/" | grep bsg-rel-1-party-backfill
	echo "copy the CSV into $EVID for the go/no-go package"
	;;
9|retire-rehearsal)
	# usage: bash rel1_staging_runbook.sh 9 "<Server Script name>"
	NAME="${2:?script name}"
	cd "$BENCH"
	sql "update \`tabServer Script\` set disabled=1 where name='$NAME';"; bench --site "$SITE" clear-cache
	echo "script '$NAME' disabled on staging - rerun its scenario now (expect ONE throw / ONE event from the app copy), then:"
	echo "  bash rel1_staging_runbook.sh 9-restore \"$NAME\""
	;;
9-restore)
	NAME="${2:?script name}"; sql "update \`tabServer Script\` set disabled=0 where name='$NAME';"; cd "$BENCH" && bench --site "$SITE" clear-cache; echo "re-enabled '$NAME'"
	;;
*)
	echo "usage: $0 <0..9|9-restore> [script name]"; exit 1;;
esac
echo "== phase '$PHASE' done $(date -Is); log: $LOG =="
