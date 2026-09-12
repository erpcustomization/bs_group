#!/usr/bin/env bash
# rel-1 staging runbook - dcs-test.local on BITS-ERP (~/bs_group)
#
# Copy this directory OUT of the app checkout before starting (phase 3 checks
# out 231ff58, which does not contain it):
#     cp -r ~/bs_group/apps/bsgroup/bsgroup/dcs/staging ~/rel1
# Run ONE phase per invocation:   bash ~/rel1/rel1_staging_runbook.sh <phase>
# Each phase writes ~/rel1-evidence/<phase>-<ts>.log (full output) and
# ~/rel1-evidence/<phase>.result (one line: PASS|FAIL|PASS-EXCEPTION + summary)
# and exits non-zero on the first failed check. A phase refuses to run unless
# the previous phase's .result is PASS (or PASS-EXCEPTION).
#
# Phases
#   0  preserve-check   read-only look at dcs-test.local; STOP for human confirmation
#   1  restore          stop workers/scheduler -> validate the approved FC backup files -> restore
#   2  baseline-a       parity baseline of the restored production data, services still stopped
#   3  isolate          email/webhooks/integrations/scheduler off, secrets masked, admin password
#                       rotated, baseline-b captured; services still stopped
#   4  baseline-commit  checkout 231ff58, migrate, build, start services, parity vs production
#   5  prefix-matrix    Section-7 probes with 231ff58 expectations (explicit PASS/FAIL)
#   6  deploy-rel1      staging DB snapshot -> checkout release HEAD -> migrate -> verify -> build
#   7  postfix-matrix   test modules + Section-7 probes with rel-1 expectations
#   8  backfill-dryrun  party backfill in dry-run mode only (signature verified first)
#   9  retire-rehearsal <script name>  disable one script through the Frappe API; 9-restore re-enables
#
# Nothing here touches production. The only production artefact used is the
# approved backup listed in backup_manifest.txt.
set -euo pipefail
SITE=dcs-test.local
BENCH=~/bs_group
EVID=~/rel1-evidence
BACKUPS=~/rel1-backup
PROD_COMMIT=231ff58
REL_BRANCH=fix/dcs-core-release-1
HERE=$(cd "$(dirname "$0")" && pwd)
# The release HEAD this cycle installs. Recorded in RELEASE_MANIFEST.sha256 next to this file.
REL_HEAD=$(cat "$HERE/RELEASE_HEAD" 2>/dev/null || true)
mkdir -p "$EVID"
PHASE="${1:-}"
ARG2="${2:-}"
TS=$(date +%Y%m%d-%H%M%S)
LOG="$EVID/${PHASE:-none}-$TS.log"
RESULT="$EVID/${PHASE:-none}.result"
exec > >(tee -a "$LOG") 2>&1
echo "== rel-1 staging runbook phase '$PHASE' at $(date -Is) on $(hostname) =="

pass() { echo "PASS $PHASE $(date -Is) $*" | tee "$RESULT"; }
pass_exc() { echo "PASS-EXCEPTION $PHASE $(date -Is) $*" | tee "$RESULT"; }
fail() { echo "FAIL $PHASE $(date -Is) $*" | tee "$RESULT"; exit 1; }
trap 'rc=$?; if [ $rc -ne 0 ] && ! grep -qE "^(PASS|FAIL)" "$RESULT" 2>/dev/null; then echo "FAIL $PHASE $(date -Is) aborted rc=$rc (see $LOG)" | tee "$RESULT"; fi' EXIT
require_prev() { local p="$1"; grep -qE "^PASS" "$EVID/$p.result" 2>/dev/null || fail "phase $p has no PASS result - run it first"; }
require_confirm() { [ -f "$EVID/$1" ] || fail "confirmation file $EVID/$1 missing - create it only after the human decision it records"; }
sql() { cd "$BENCH" && bench --site "$SITE" mariadb -e "$1" 2>/dev/null; }
py() { cd "$BENCH/sites" && ../env/bin/python "$@"; }
services_stop() {
	cd "$BENCH"
	bench --site "$SITE" set-config pause_scheduler 1
	bench --site "$SITE" set-config maintenance_mode 1
	if command -v supervisorctl >/dev/null && sudo -n supervisorctl status >/dev/null 2>&1; then sudo -n supervisorctl stop all; SUP=1; else SUP=0; fi
	pkill -f "bench start" 2>/dev/null || true
	pkill -f "frappe.utils.bench_helper.*(worker|schedule|serve)" 2>/dev/null || true
	sleep 3
	if pgrep -f "frappe.utils.bench_helper" >/dev/null; then fail "frappe workers still running after stop"; fi
	echo "services stopped (supervisor=$SUP)"
}
services_start() {
	cd "$BENCH"
	bench --site "$SITE" set-config maintenance_mode 0
	if command -v supervisorctl >/dev/null && sudo -n supervisorctl status >/dev/null 2>&1; then sudo -n supervisorctl start all; else
		echo "no supervisor: start the web server for UI scenarios with: cd $BENCH && nohup bench serve --port 8001 >/dev/null 2>&1 &"; fi
}
parity_query() {
	sql "select concat_ws('|','DocType',count(*),max(modified)) r from \`tabDocType\` union all select concat_ws('|','CustomField',count(*),max(modified)) from \`tabCustom Field\` union all select concat_ws('|','PropertySetter',count(*),max(modified)) from \`tabProperty Setter\` union all select concat_ws('|','ServerScript',count(*),sum(disabled),max(modified)) from \`tabServer Script\` union all select concat_ws('|','ClientScript',count(*),max(modified)) from \`tabClient Script\` union all select concat_ws('|','DocPerm_DCS',count(*)) from \`tabDocPerm\` where parent='Deal Cost Sheet' union all select concat_ws('|','DocPerm_PR',count(*)) from \`tabDocPerm\` where parent='Presales Request' union all select concat_ws('|','DocPerm_PCB',count(*)) from \`tabDocPerm\` where parent='Project Cost Baseline' union all select concat_ws('|','DocPerm_GE',count(*)) from \`tabDocPerm\` where parent='DCS Governance Event' union all select concat_ws('|','DocPerm_HC',count(*)) from \`tabDocPerm\` where parent='DCS Handover Condition' union all select concat_ws('|','CustomDocPerm_all',count(*)) from \`tabCustom DocPerm\` union all select concat_ws('|','PR',count(*),sum(docstatus=2),max(modified)) from \`tabPresales Request\` union all select concat_ws('|','PR_badcustomer',count(*)) from \`tabPresales Request\` p where not exists (select 1 from \`tabCustomer\` c where c.name=p.customer) union all select concat_ws('|','PR_duedate',count(*)) from \`tabPresales Request\` where due_date is not null union all select concat_ws('|','DCS',count(*),sum(docstatus=0),sum(docstatus=1),sum(docstatus=2),max(modified)) from \`tabDeal Cost Sheet\` union all select concat_ws('|','DCS_dangling_PR',count(*)) from \`tabDeal Cost Sheet\` d where ifnull(d.presales_request,'')<>'' and not exists (select 1 from \`tabPresales Request\` p where p.name=d.presales_request) union all select concat_ws('|','GovEvent',count(*),sum(ifnull(actor,'')=''),max(modified)) from \`tabDCS Governance Event\` union all select concat_ws('|','HandoverCond',count(*),max(modified)) from \`tabDCS Handover Condition\` union all select concat_ws('|','Revision',count(*),max(modified)) from \`tabDCS Revision\` union all select concat_ws('|','AwardReversal',count(*)) from \`tabDCS Award Reversal\` union all select concat_ws('|','PCB',count(*)) from \`tabProject Cost Baseline\` union all select concat_ws('|','Opportunity',count(*)) from \`tabOpportunity\` union all select concat_ws('|','Customer',count(*)) from \`tabCustomer\` union all select concat_ws('|','Lead',count(*)) from \`tabLead\` union all select concat_ws('|','Project',count(*)) from \`tabProject\` union all select concat_ws('|','Quotation',count(*)) from \`tabQuotation\` union all select concat_ws('|','HDTicket',count(*)) from \`tabHD Ticket\` union all select concat_ws('|','Communication',count(*)) from \`tabCommunication\` union all select concat_ws('|','EmailAccount',count(*),sum(enable_outgoing),sum(enable_incoming)) from \`tabEmail Account\` union all select concat_ws('|','Webhook',count(*),sum(enabled)) from \`tabWebhook\` union all select concat_ws('|','HC_doctype',custom,module,autoname) from \`tabDocType\` where name='DCS Handover Condition' union all select concat_ws('|','BSGS',field,ifnull(value,'')) from \`tabSingles\` where doctype='BS Group Settings' and field in ('cost_overrun_policy','enable_dcs_one_active_guard','enable_dcs_governed_field_guard','enable_dcs_record_authority_guard','dcs_addtional_item');" | tail -n +2
}
# compare a captured parity file with the production baseline, ignoring lines the run legitimately changes
parity_compare() {
	local got="$1" ignore_re="$2"
	grep -v '^#' "$HERE/production_baseline_2026-09-12.psv" | grep -vE "$ignore_re" | sort > /tmp/parity.expected
	grep -v '^#' "$got" | grep -vE "$ignore_re" | sort > /tmp/parity.got
	if diff -u /tmp/parity.expected /tmp/parity.got; then echo "parity: identical on compared lines"; return 0; fi
	return 1
}

case "$PHASE" in
0|preserve-check)
	cd "$BENCH"
	echo "-- sites"; ls sites; echo "currentsite: $(cat sites/currentsite.txt 2>/dev/null || echo none)"
	if [ ! -d "sites/$SITE" ]; then pass "site $SITE does not exist - nothing to preserve"; exit 0; fi
	echo "-- apps"; bench --site "$SITE" list-apps
	echo "-- bsgroup commit on this bench"; git -C apps/bsgroup log --oneline -1
	echo "-- record counts and latest modified on $SITE"
	sql "select 'DCS',count(*),max(modified) from \`tabDeal Cost Sheet\` union all select 'PR',count(*),max(modified) from \`tabPresales Request\` union all select 'GovEvent',count(*),max(modified) from \`tabDCS Governance Event\` union all select 'Customer',count(*),max(modified) from \`tabCustomer\` union all select 'Project',count(*),max(modified) from \`tabProject\` union all select 'User',count(*),max(modified) from \`tabUser\` union all select 'File',count(*),max(modified) from \`tabFile\` union all select 'ServerScript',count(*),max(modified) from \`tabServer Script\` union all select 'ErrorLog',count(*),max(modified) from \`tabError Log\`;"
	echo "-- rows created or modified on $SITE in the last 60 days"
	sql "select 'DCS',count(*) from \`tabDeal Cost Sheet\` where modified > now() - interval 60 day union all select 'PR',count(*) from \`tabPresales Request\` where modified > now() - interval 60 day union all select 'Customer',count(*) from \`tabCustomer\` where modified > now() - interval 60 day union all select 'File',count(*) from \`tabFile\` where creation > now() - interval 60 day;"
	echo "-- users who logged in during the last 60 days (someone may be using this site)"
	sql "select name, last_login from \`tabUser\` where last_login > now() - interval 60 day order by last_login desc limit 20;"
	du -sh "sites/$SITE/private/files" "sites/$SITE/public/files" 2>/dev/null || true
	pass "read-only inventory captured; HUMAN DECISION REQUIRED: touch $EVID/CONFIRM_OVERWRITE_dcs-test.local only if nothing above must be kept"
	;;
1|restore)
	require_prev 0; require_confirm CONFIRM_OVERWRITE_dcs-test.local
	[ -f "$HERE/backup_manifest.txt" ] || fail "backup_manifest.txt missing (exact approved filenames + sizes)"
	grep -q "FILL-EXACT" "$HERE/backup_manifest.txt" && fail "backup_manifest.txt still has placeholder filenames"
	# bench app parity with production (production_apps_2026-09-12.txt)
	while read -r app repo branch commit rest; do
		case "$app" in \#*|"") continue;; zoho_migration) continue;; esac
		[ -d "$BENCH/apps/$app" ] || fail "app $app missing from the bench (production has it at $commit)"
		have=$(git -C "$BENCH/apps/$app" rev-parse --short=7 HEAD)
		[ "$have" = "$commit" ] || [ "$app" = "bsgroup" ] || fail "app $app is at $have, production is at $commit - bring the bench to parity first"
	done < "$HERE/production_apps_2026-09-12.txt"
	cd "$BACKUPS" || fail "$BACKUPS missing"
	# manifest lines: <kind> <exact filename> <size_bytes_from_frappe_cloud>   kind in db|public|private
	DB=$(awk '$1=="db"{print $2}' "$HERE/backup_manifest.txt"); PUB=$(awk '$1=="public"{print $2}' "$HERE/backup_manifest.txt"); PRIV=$(awk '$1=="private"{print $2}' "$HERE/backup_manifest.txt")
	[ -n "$DB" ] && [ -n "$PUB" ] && [ -n "$PRIV" ] || fail "manifest incomplete"
	for kind in db public private; do
		f=$(awk -v k=$kind '$1==k{print $2}' "$HERE/backup_manifest.txt"); expect=$(awk -v k=$kind '$1==k{print $3}' "$HERE/backup_manifest.txt")
		[ -f "$f" ] || fail "approved file not present: $f"
		actual=$(stat -c %s "$f")
		# Frappe Cloud shows sizes in MB with two decimals: allow +-1%
		# the dashboard shows MB with two decimals; MB-vs-MiB ambiguity is under 5%, so a 6% band still rejects any other backup
		awk -v a="$actual" -v e="$expect" 'BEGIN{d=(a>e?a-e:e-a); if (d > e*0.06) exit 1}' || fail "$f size $actual bytes differs from the approved $expect by more than 6%"
		echo "$kind $f size=$actual ok"
	done
	gzip -t "$DB" || fail "database dump is not a valid gzip"
	tar -tf "$PUB" >/dev/null || fail "public files tar unreadable"
	tar -tf "$PRIV" >/dev/null || fail "private files tar unreadable"
	( set +o pipefail; zcat "$DB" | head -c 400000 | grep -q "tabDocType" ) || fail "database dump does not look like a Frappe dump"
	sha256sum "$DB" "$PUB" "$PRIV" | tee "$EVID/backup-checksums.sha256"
	services_stop
	cd "$BENCH"
	bench --site "$SITE" restore "$BACKUPS/$DB" --with-public-files "$BACKUPS/$PUB" --with-private-files "$BACKUPS/$PRIV" --force
	# the restored data carries live email/webhook/integration config: keep services stopped until phase 3
	bench --site "$SITE" set-config pause_scheduler 1
	bench --site "$SITE" set-config maintenance_mode 1
	# DOCUMENTED STAGING DEVIATION: Zoho Migration (TridotsTech/ZohoMigration, private) is installed on
	# production but its source is not available on BITS-ERP. It is outside the DCS scope; the site's
	# installed-apps list is trimmed so migrate can run. Its DocTypes/tables stay in the database untouched.
	if [ ! -d "$BENCH/apps/zoho_migration" ]; then
		bench --site "$SITE" remove-from-installed-apps zoho_migration || true
		echo "DEVIATION: zoho_migration removed from installed apps on staging (source unavailable)" | tee -a "$EVID/deviations.txt"
	fi
	pass "restored $DB / $PUB / $PRIV into $SITE with services stopped"
	;;
2|baseline-a)
	require_prev 1
	pgrep -f "frappe.utils.bench_helper" >/dev/null && fail "workers are running; baseline-a must be captured with services stopped"
	parity_query | tee "$EVID/baseline-a-restored.psv"
	# expected differences at this point: none in metadata/data (same dump); ServerScript modified identical
	if parity_compare "$EVID/baseline-a-restored.psv" '^(PR\|)'; then pass "restored data identical to production baseline (PR max(modified) excluded: nightly scheduler bump)"; else fail "restored data differs from the production baseline"; fi
	;;
3|isolate)
	require_prev 2
	pgrep -f "frappe.utils.bench_helper" >/dev/null && fail "workers are running; isolate with services stopped"
	cd "$BENCH"
	bench --site "$SITE" set-config developer_mode 0
	bench --site "$SITE" set-config pause_scheduler 1
	bench --site "$SITE" set-config mute_emails 1
	bench --site "$SITE" set-config disable_website_cache 1
	bench --site "$SITE" scheduler disable || true
	sql "update \`tabEmail Account\` set enable_outgoing=0, enable_incoming=0, awaiting_password=1;"
	sql "update \`tabWebhook\` set enabled=0;"
	sql "update \`tabServer Script\` set disabled=1 where disabled=0 and (name like 'zoho%' or name like 'Zoho%' or name like 'aira%' or name like 'AIRA%' or name like 'Outlook%' or name like 'outlook%' or name like 'Teams%' or name = 'fleet_gps_ingest' or name like 'sync_%_to_zoho' or name = 'org_chart_data' or name = 'PPM - Daily Status Update and Reminders');"
	sql "update \`tabSingles\` set value='' where field regexp 'token|secret|client_id|client_secret|api_key|password|webhook_url|refresh' and doctype not in ('System Settings','Website Settings');"
	sql "update \`tabSocial Login Key\` set enable_social_login=0;" || true
	sql "update \`tabUser\` set enabled=0 where name not in ('Administrator','Guest') and user_type='System User';"   # nobody but Administrator + ZZTEST users can sign in to staging
	PW=$(openssl rand -base64 24 | tr -d '=+/' | cut -c1-22)
	bench --site "$SITE" set-admin-password "$PW" >/dev/null
	umask 077; printf '%s\n' "$PW" > "$EVID/staging-admin.secret"; unset PW
	echo "Administrator password rotated; stored only in $EVID/staging-admin.secret (mode 600) - not printed here"
	bench --site "$SITE" clear-cache
	parity_query | tee "$EVID/baseline-b-isolated.psv"
	# differences allowed vs baseline-a: ServerScript disabled count/modified, EmailAccount flags, Webhook flags
	if parity_compare "$EVID/baseline-b-isolated.psv" '^(PR\||ServerScript\||EmailAccount\||Webhook\|)'; then :; else fail "isolation changed something outside the expected lines"; fi
	grep -E '^(ServerScript|EmailAccount|Webhook)\|' "$EVID/baseline-b-isolated.psv"
	grep -qE '^EmailAccount\|[0-9]+\|0\|0$' "$EVID/baseline-b-isolated.psv" || fail "an Email Account is still enabled"
	grep -qE '^Webhook\|[0-9]+\|0$' "$EVID/baseline-b-isolated.psv" || fail "a Webhook is still enabled"
	pass "isolated with services stopped; baseline-b captured"
	;;
4|baseline-commit)
	require_prev 3
	cd "$BENCH/apps/bsgroup"
	git fetch origin
	[ -z "$(git status --porcelain)" ] || fail "app checkout has local modifications: $(git status --porcelain | head -5)"
	git checkout --detach "$PROD_COMMIT"
	[ "$(git rev-parse --short HEAD)" = "$PROD_COMMIT" ] || fail "checkout is not $PROD_COMMIT"
	cd "$BENCH"
	bench --site "$SITE" migrate
	bench build --app bsgroup
	services_start
	parity_query | tee "$EVID/baseline-commit-231ff58.psv"
	# migrate on the production commit may re-sync DocType/Property Setter modified timestamps; metadata counts must not move
	if parity_compare "$EVID/baseline-commit-231ff58.psv" '^(PR\||ServerScript\||EmailAccount\||Webhook\||DocType\||PropertySetter\||CustomField\||ClientScript\|)'; then :; else fail "data/permission parity broken after migrate on $PROD_COMMIT"; fi
	for k in DocType CustomField PropertySetter ClientScript; do
		e=$(grep "^$k|" "$HERE/production_baseline_2026-09-12.psv" | cut -d'|' -f2); g=$(grep "^$k|" "$EVID/baseline-commit-231ff58.psv" | cut -d'|' -f2)
		[ "$e" = "$g" ] || fail "$k count moved $e -> $g after migrate on $PROD_COMMIT"
	done
	sql "select name from \`tabServer Script\` where disabled=1 order by name;" | tail -n +2 | sha256sum | tee "$EVID/disabled-scripts-231ff58.sha256"
	pass "$PROD_COMMIT deployed; metadata and data parity with production holds"
	;;
5|prefix-matrix)
	require_prev 4
	[ "$(git -C "$BENCH/apps/bsgroup" rev-parse --short HEAD)" = "$PROD_COMMIT" ] || fail "not on $PROD_COMMIT"
	if py "$HERE/prefix_probes.py" "$SITE" prefix | tee "$EVID/matrix-prefix.jsonl"; then pass "pre-fix matrix reproduced on $PROD_COMMIT as expected"; else fail "a pre-fix probe did not reproduce the expected 231ff58 behaviour"; fi
	;;
6|deploy-rel1)
	require_prev 5
	[ -n "$REL_HEAD" ] || fail "RELEASE_HEAD file missing next to the runbook"
	cd "$BENCH"
	# staging snapshot immediately before the migration that converts DCS Handover Condition
	bench --site "$SITE" backup 2>&1 | tee "$EVID/pre-migrate-snapshot.txt"
	SNAP=$(ls -t "sites/$SITE/private/backups/"*database.sql.gz | head -1); sha256sum "$SNAP" | tee -a "$EVID/pre-migrate-snapshot.txt"
	sql "select custom,module from \`tabDocType\` where name='DCS Handover Condition'; select count(*) from \`tabDCS Handover Condition\`;" | tee "$EVID/hc-before-migrate.txt"
	cd "$BENCH/apps/bsgroup"
	if ! git fetch origin "$REL_BRANCH" 2>/dev/null; then
		[ -f "$HERE/fix-dcs-core-release-1.bundle" ] || fail "branch not on origin and no bundle next to the runbook"
		sha256sum -c --ignore-missing "$HERE/RELEASE_MANIFEST.sha256" || fail "bundle checksum mismatch"
		git fetch "$HERE/fix-dcs-core-release-1.bundle" "$REL_BRANCH:$REL_BRANCH"
	fi
	git checkout "$REL_BRANCH"
	[ "$(git rev-parse HEAD)" = "$REL_HEAD" ] || fail "checked-out HEAD $(git rev-parse HEAD) is not the recorded release HEAD $REL_HEAD"
	git log --oneline -14
	cd "$BENCH"
	bench --site "$SITE" migrate 2>&1 | tee "$EVID/migrate-rel1.log"
	if grep -qE "Traceback \(most recent call last\)|frappe\.exceptions\.|Exception:" "$EVID/migrate-rel1.log"; then fail "migrate log contains an exception"; fi
	sql "select name from \`tabPatch Log\` where patch like 'bsgroup.patches.v0_1%' order by creation;" | tee "$EVID/patch-log-rel1.txt"
	for p in reconcile_handover_condition_doctype verify_handover_condition_doctype drop_orphan_governance_change lock_pcb_until_g_pcb backfill_party_fields; do grep -q "$p" "$EVID/patch-log-rel1.txt" || fail "patch $p not recorded in Patch Log"; done
	sql "select creation, left(replace(error,'\n',' / '),300) from \`tabError Log\` where method='BSG-REL-1' order by creation;" | tee "$EVID/bsg-rel-1-log.txt"
	sql "select custom,module from \`tabDocType\` where name='DCS Handover Condition'; select count(*) from \`tabDCS Handover Condition\`;" | tee "$EVID/hc-after-migrate.txt"
	grep -qE '^0\s+BS Group' "$EVID/hc-after-migrate.txt" || fail "DCS Handover Condition is not standard/BS Group after migrate"
	[ "$(tail -1 "$EVID/hc-before-migrate.txt")" = "$(tail -1 "$EVID/hc-after-migrate.txt")" ] || fail "Handover Condition row count changed across the migrate"
	grep -q "party backfill summary" "$EVID/bsg-rel-1-log.txt" && grep -q '"mode": "dry-run"' "$EVID/bsg-rel-1-log.txt" || fail "party backfill did not run in dry-run mode"
	bench build --app bsgroup
	bench restart 2>/dev/null || services_start
	pass "rel-1 $REL_HEAD installed; patches applied; Handover Condition reconciled without row loss; backfill dry-run only"
	;;
7|postfix-matrix)
	require_prev 6
	[ "$(git -C "$BENCH/apps/bsgroup" rev-parse HEAD)" = "$REL_HEAD" ] || fail "not on the release HEAD"
	cd "$BENCH"
	: > "$EVID/tests-rel1.txt"
	for m in bsgroup.bs_group.doctype.dcs_governance_event.test_dcs_governance_event bsgroup.api.dcs.test_dcs_api bsgroup.bs_group.doctype.presales_request.test_presales_request bsgroup.bs_group.doctype.deal_cost_sheet.test_deal_cost_sheet bsgroup.bs_group.doctype.dcs_handover_condition.test_dcs_handover_condition; do
		echo "=== $m" | tee -a "$EVID/tests-rel1.txt"
		if bench --site "$SITE" run-tests --module "$m" 2>&1 | tee -a "$EVID/tests-rel1.txt" | tail -5 | grep -qE '^OK'; then echo "$m OK"; else fail "test module $m did not end with OK"; fi
	done
	if py "$HERE/prefix_probes.py" "$SITE" postfix | tee "$EVID/matrix-postfix.jsonl"; then :; else fail "a post-fix probe did not meet its acceptance criterion"; fi
	sql "select 'DCS',count(*) from \`tabDeal Cost Sheet\` where name like 'DCS-ZZTEST%' union all select 'PR',count(*) from \`tabPresales Request\` where name like 'PR-ZZTEST%' union all select 'User',count(*) from \`tabUser\` where name like 'zztest-%';" | tee "$EVID/zztest-residue.txt"
	if grep -q '"status": "PASS-EXCEPTION"' "$EVID/matrix-postfix.jsonl"; then pass_exc "tests OK; post-fix matrix met (S-01 and S-19 unchanged by instruction: H-1 and ignore_links_on_delete deferred)"; else pass "tests OK; post-fix matrix met"; fi
	;;
8|backfill-dryrun)
	require_prev 7
	py - <<'PY' || fail "backfill signature is not execute(apply=None)"
import inspect, sys
sys.path.insert(0, "../apps/bsgroup")
from bsgroup.patches.v0_1 import backfill_party_fields as m
sig = inspect.signature(m.execute)
assert list(sig.parameters) == ["apply"] and sig.parameters["apply"].default is None, sig
print("signature ok:", sig)
PY
	py - "$SITE" <<'PY' | tee "$EVID/backfill-dryrun.txt"
import sys, frappe
sys.path.insert(0, "../apps/bsgroup")
frappe.init(site=sys.argv[1]); frappe.connect(); frappe.set_user("Administrator")
from bsgroup.patches.v0_1 import backfill_party_fields as m
before = frappe.db.sql("select checksum table `tabPresales Request`, `tabDeal Cost Sheet`", as_dict=True)
out = m.execute(apply=False)
frappe.db.rollback()
after = frappe.db.sql("select checksum table `tabPresales Request`, `tabDeal Cost Sheet`", as_dict=True)
print("DRY-RUN", out)
print("tables unchanged:", [b["Checksum"] for b in before] == [a["Checksum"] for a in after])
frappe.destroy()
PY
	grep -q "'mode': 'dry-run'" "$EVID/backfill-dryrun.txt" || fail "backfill did not report dry-run mode"
	grep -q "tables unchanged: True" "$EVID/backfill-dryrun.txt" || fail "backfill dry run changed a table"
	cp "$BENCH/sites/$SITE/private/files/"bsg-rel-1-party-backfill-dry-run-*.csv "$EVID/" 2>/dev/null || true
	pass "party backfill dry-run report captured; no data changed"
	;;
9|retire-rehearsal)
	[ -n "$ARG2" ] || fail "usage: $0 9 '<Server Script name>'"
	py - "$SITE" "$ARG2" 1 <<'PY' || fail "could not disable script"
import sys, frappe
frappe.init(site=sys.argv[1]); frappe.connect(); frappe.set_user("Administrator")
name, state = sys.argv[2], int(sys.argv[3])
if not frappe.db.exists("Server Script", name): raise SystemExit(f"no such Server Script: {name!r}")
frappe.db.set_value("Server Script", name, "disabled", state); frappe.db.commit(); frappe.clear_cache()
print("Server Script", name, "disabled =", frappe.db.get_value("Server Script", name, "disabled"))
frappe.destroy()
PY
	pass "script disabled on staging; rerun its scenario, then: $0 9-restore '$ARG2'"
	;;
9-restore)
	[ -n "$ARG2" ] || fail "usage: $0 9-restore '<Server Script name>'"
	py - "$SITE" "$ARG2" 0 <<'PY' || fail "could not re-enable script"
import sys, frappe
frappe.init(site=sys.argv[1]); frappe.connect(); frappe.set_user("Administrator")
name, state = sys.argv[2], int(sys.argv[3])
frappe.db.set_value("Server Script", name, "disabled", state); frappe.db.commit(); frappe.clear_cache()
print("Server Script", name, "disabled =", frappe.db.get_value("Server Script", name, "disabled"))
frappe.destroy()
PY
	pass "script re-enabled"
	;;
*)
	echo "usage: $0 <0..9|9-restore> [script name]"; exit 1;;
esac
