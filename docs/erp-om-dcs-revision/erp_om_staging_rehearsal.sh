#!/usr/bin/env bash
# erp-om staging rehearsal: fix/dcs-vendor-revision @ 9aa9c3a on a STAGING COPY of erp-om.
#
# Runs on a self-hosted staging bench (e.g. BITS-ERP) whose frappe / erpnext / hrms / helpdesk / telephony
# commits match erp-om's bench group (erpOM, bench-41009). Never on Frappe Cloud production, never on
# erp.bitssecureit.com, never on erp.siteexclusive.ae (live third-party site, not staging).
#
# One phase per invocation:   bash erp_om_staging_rehearsal.sh <phase>
# Evidence: $EVID/<phase>-<ts>.log (full output) and $EVID/<phase>.result (PASS|FAIL + summary).
# A phase refuses to run unless the previous phase's .result is PASS.
#
#   0  preflight   guard the site name, record bench app commits, confirm bsgroup is at bb27213 (erp-om's main)
#   1  restore     restore the APPROVED erp-om backup into $SITE, then isolate it (scheduler, email, webhooks)
#   2  baseline    pre-migrate counts + the facts each patch depends on (read-only)
#   3  migrate     checkout 9aa9c3a, bench migrate, build; capture Patch Log + Error Log 'BSG-REL-1'; post-migrate counts
#   4  tests       the four DCS test modules, one at a time; counts again afterwards
#   5  deskcheck   BEFORE: screen3 capability for $DESK_USER on $TARGET_DCS; then do the desk steps by hand;
#                  run '5 verify' afterwards to check DCS Revision / Governance Event / Quotation
#   6  summary     final counts, diff against baseline, one-page PASS/FAIL summary
#
# Use the phase NUMBER (0..6); results are keyed by number.
# Nothing here writes to any site except $SITE.
set -euo pipefail

SITE="${SITE:-erp-om-staging.local}"
BENCH="${BENCH:-$HOME/bs_group}"
EVID="${EVID:-$HOME/erp-om-rehearsal-evidence}"
BACKUPS="${BACKUPS:-$HOME/erp-om-backup}"          # approved erp-om backup files (db / public / private)
BACKUP_DB="${BACKUP_DB:-}"                          # exact filenames from the approved Frappe Cloud backup
BACKUP_PUB="${BACKUP_PUB:-}"
BACKUP_PRIV="${BACKUP_PRIV:-}"
BASE_COMMIT=bb27213                                  # what erp-om runs today (main)
REL_COMMIT=9aa9c3a                                   # fix/dcs-vendor-revision
TARGET_DCS="${TARGET_DCS:-DCS-MUSCAT-OVERSEAS-COMPANY-LLC-003-1}"
DESK_USER="${DESK_USER:-}"                           # a user holding Presales / Sales Manager / Commercial Controller / Managing Director
NEW_COST=1013.67
REASON="Consulting charge OMR 100"
MODULES=(
	bsgroup.api.dcs.test_dcs_vendor_revision
	bsgroup.api.dcs.test_dcs_api
	bsgroup.api.dcs.test_dcs_po_scope_match
	bsgroup.api.dcs.test_dcs_rpc_binding
)

mkdir -p "$EVID"
PHASE="${1:-}"; ARG2="${2:-}"
TS=$(date +%Y%m%d-%H%M%S)
LOG="$EVID/${PHASE:-none}-$TS.log"
RESULT="$EVID/${PHASE:-none}.result"
exec > >(tee -a "$LOG") 2>&1
echo "== erp-om rehearsal phase '$PHASE' at $(date -Is) on $(hostname), site $SITE =="

pass() { echo "PASS $PHASE $(date -Is) $*" | tee "$RESULT"; }
fail() { echo "FAIL $PHASE $(date -Is) $*" | tee "$RESULT"; exit 1; }
trap 'rc=$?; if [ $rc -ne 0 ] && ! grep -qE "^(PASS|FAIL)" "$RESULT" 2>/dev/null; then echo "FAIL $PHASE $(date -Is) aborted rc=$rc (see $LOG)" | tee "$RESULT"; fi' EXIT
require_prev() { grep -qE "^PASS" "$EVID/$1.result" 2>/dev/null || fail "phase $1 has no PASS result - run it first"; }
sql() { (cd "$BENCH" && bench --site "$SITE" mariadb -e "$1" 2>/dev/null) | tail -n +2; }
py() { (cd "$BENCH/sites" && ../env/bin/python -c "$1"); }

# --- hard guard: this script only ever touches a local staging site ---------------------------------
case "$SITE" in
	*erp-om.bitssecureit.com*|*erp.bitssecureit.com*|*siteexclusive*|*frappe.cloud*|*erp-om.k.*)
		fail "refusing to run against '$SITE': production / third-party site";;
esac
[[ "$SITE" == *.local || "$SITE" == *staging* ]] || fail "site name must end in .local or contain 'staging'"

count_row() {
	# count_row <label> <select ...>  -> "label|value" or "label|n/a" when the table/column does not exist (yet)
	local label="$1" q="$2" v
	v=$(sql "$q" 2>/dev/null) || v=""
	echo "$label|${v:-n/a}"
}
counts() {
	count_row DocType               "select count(*) from \`tabDocType\`"
	count_row DocType_BSGroup       "select count(*) from \`tabDocType\` where module='BS Group'"
	count_row DealCostSheet         "select concat_ws('/',count(*),sum(docstatus=0),sum(docstatus=1),sum(docstatus=2)) from \`tabDeal Cost Sheet\`"
	count_row DCSRevision           "select count(*) from \`tabDCS Revision\`"
	count_row DCSGovernanceEvent    "select count(*) from \`tabDCS Governance Event\`"
	count_row Quotation             "select concat_ws('/',count(*),sum(docstatus=0),sum(docstatus=1),sum(docstatus=2)) from \`tabQuotation\`"
	count_row PresalesRequest       "select count(*) from \`tabPresales Request\`"
	count_row DCSHandoverCondition  "select count(*) from \`tabDCS Handover Condition\`"
	count_row GovEventChangeRows    "select count(*) from \`tabDCS Governance Event Change\`"
	count_row ProjectCostBaseline   "select count(*) from \`tabProject Cost Baseline\`"
	count_row PartyBackfillRun      "select count(*) from \`tabParty Backfill Run\`"
	count_row ServerScript          "select count(*) from \`tabServer Script\`"
	count_row Role_CC_MD            "select count(*) from \`tabRole\` where name in ('Commercial Controller','Managing Director')"
	count_row CustomDocPerm_touched "select count(*) from \`tabCustom DocPerm\` where parent in ('Deal Cost Sheet','Presales Request','Project Cost Baseline','DCS Governance Event','DCS Revision')"
	count_row ErrorLog_BSG_REL_1    "select count(*) from \`tabError Log\` where method='BSG-REL-1'"
	count_row DCS_party_blank       "select count(*) from \`tabDeal Cost Sheet\` where ifnull(party,'')=''"
	count_row PR_party_blank        "select count(*) from \`tabPresales Request\` where ifnull(party,'')=''"
	count_row CostOverrunPolicy     "select ifnull(value,'(unset)') from \`tabSingles\` where doctype='BS Group Settings' and field='cost_overrun_policy'"
}

target_row() {
	sql "select concat_ws('|', name, docstatus, total_cost, total_selling, ifnull(custom_quotation,''), ifnull(custom_deal_status,''),
		ifnull(custom_dcs_revision_no,0), ifnull(custom_working_total_cost,''), ifnull(custom_working_total_selling,''),
		ifnull(custom_working_margin_percent,''), ifnull(custom_approval_state,''), ifnull(custom_margin_gate,''))
		from \`tabDeal Cost Sheet\` where name='$TARGET_DCS';"
}

case "$PHASE" in
0|preflight)
	cd "$BENCH"
	[ -d "sites/$SITE" ] && echo "NOTE: $SITE already exists; phase 1 will overwrite it (--force)."
	echo "-- bench app commits (must match erp-om's bench group, bench-41009)"
	for a in apps/*; do printf '%-16s %s\n' "$(basename "$a")" "$(git -C "$a" log --oneline -1 2>/dev/null)"; done | tee "$EVID/bench-apps.txt"
	have=$(git -C apps/bsgroup rev-parse --short=7 HEAD)
	[ "$have" = "$BASE_COMMIT" ] || fail "bsgroup is at $have; check out $BASE_COMMIT (erp-om's current main) before restoring"
	git -C apps/bsgroup cat-file -e "$REL_COMMIT^{commit}" || fail "$REL_COMMIT not fetched: git -C apps/bsgroup fetch origin fix/dcs-vendor-revision"
	for a in zoho_migration print_designer; do [ -d "apps/$a" ] && echo "WARN: $a is on this bench; erp-om does not have it - do not install it on $SITE"; done
	pass "bench inventory recorded; bsgroup at $BASE_COMMIT; $REL_COMMIT available. HUMAN CHECK: compare bench-apps.txt with erp-om's Frappe Cloud app list"
	;;
1|restore)
	require_prev 0
	[ -n "$BACKUP_DB" ] && [ -n "$BACKUP_PUB" ] && [ -n "$BACKUP_PRIV" ] || fail "set BACKUP_DB / BACKUP_PUB / BACKUP_PRIV to the exact approved erp-om backup filenames"
	[ -n "${STAGING_ADMIN_PW:-}" ] || fail "set STAGING_ADMIN_PW (a new staging-only Administrator password)"
	cd "$BACKUPS"
	for f in "$BACKUP_DB" "$BACKUP_PUB" "$BACKUP_PRIV"; do [ -f "$f" ] || fail "missing $f"; done
	gzip -t "$BACKUP_DB" || fail "db dump is not valid gzip"
	tar -tf "$BACKUP_PUB" >/dev/null && tar -tf "$BACKUP_PRIV" >/dev/null || fail "files tar unreadable"
	sha256sum "$BACKUP_DB" "$BACKUP_PUB" "$BACKUP_PRIV" | tee "$EVID/backup-checksums.sha256"
	cd "$BENCH"
	[ -d "sites/$SITE" ] || bench new-site "$SITE" --admin-password "$(openssl rand -hex 12)"
	bench --site "$SITE" restore "$BACKUPS/$BACKUP_DB" --with-public-files "$BACKUPS/$BACKUP_PUB" --with-private-files "$BACKUPS/$BACKUP_PRIV" --force
	# isolate before anything else can run: no scheduler, no outgoing mail, no webhooks
	bench --site "$SITE" set-config pause_scheduler 1
	bench --site "$SITE" set-config mute_emails 1
	bench --site "$SITE" set-config allow_tests 1
	sql "update \`tabEmail Account\` set enable_outgoing=0, enable_incoming=0;"
	sql "update \`tabWebhook\` set enabled=0;" || true
	# staging-only Administrator password (never a production password); supplied by the operator
	bench --site "$SITE" set-admin-password "$STAGING_ADMIN_PW" >/dev/null
	echo "installed apps on the restored site:"; bench --site "$SITE" list-apps | tee "$EVID/site-apps.txt"
	grep -qiE "zoho_migration|print_designer" "$EVID/site-apps.txt" && echo "WARN: restored site lists zoho_migration/print_designer - erp-om is not expected to"
	pass "erp-om backup restored into $SITE and isolated (scheduler paused, mail muted, webhooks off)"
	;;
2|baseline)
	require_prev 1
	counts | tee "$EVID/counts-pre-migrate.psv"
	echo "-- facts each patch depends on"
	echo "reconcile_handover_condition_doctype: DocType row (custom|module) - no-op when 0|BS Group"
	sql "select concat_ws('|',custom,module,autoname) from \`tabDocType\` where name='DCS Handover Condition';" | tee "$EVID/fact-handover-doctype.txt"
	echo "fold_governance_change_rows / drop_orphan_governance_change: legacy child rows"
	sql "select count(*) from \`tabDCS Governance Event Change\`;" 2>/dev/null | tee "$EVID/fact-gov-change-rows.txt" || echo "table absent" | tee "$EVID/fact-gov-change-rows.txt"
	echo "lock_pcb_until_g_pcb: current cost_overrun_policy (patch sets it to None; record this to restore after G-PCB)"
	sql "select ifnull(value,'(unset)') from \`tabSingles\` where doctype='BS Group Settings' and field='cost_overrun_policy';" | tee "$EVID/fact-cost-overrun-policy.txt"
	echo "normalize_po_scope_match: rows that will be rewritten (ASCII hyphen -> en dash)"
	sql "select ifnull(custom_po_scope_match,'(null)'), count(*) from \`tabDeal Cost Sheet\` group by 1;" | tee "$EVID/fact-po-scope-match.txt"
	echo "legacy post_model_sync patches already in Patch Log (expected: all 4 present, so they do not re-run)"
	sql "select patch from \`tabPatch Log\` where patch like 'bsgroup.patches.%';" | tee "$EVID/fact-patch-log-pre.txt"
	echo "UAE-only customisations (expected absent on erp-om)"
	sql "select concat_ws('|','Address.emirate',count(*)) from \`tabCustom Field\` where dt='Address' and fieldname like '%emirate%'
		union all select concat_ws('|','UAE VAT 5 templates',count(*)) from \`tabSales Taxes and Charges Template\` where name like '%UAE VAT 5%';" | tee "$EVID/fact-uae-only.txt"
	echo "target sheet (pre-migrate)"; target_row | tee "$EVID/target-pre-migrate.psv"
	[ -s "$EVID/target-pre-migrate.psv" ] || fail "$TARGET_DCS not found in the restored backup - is it the approved post-29-Sep erp-om backup?"
	pass "pre-migrate baseline captured"
	;;
3|migrate)
	require_prev 2
	cd "$BENCH"
	git -C apps/bsgroup checkout --detach "$REL_COMMIT"
	[ "$(git -C apps/bsgroup rev-parse --short=7 HEAD)" = "$REL_COMMIT" ] || fail "checkout of $REL_COMMIT failed"
	if ! bench --site "$SITE" migrate 2>&1 | tee "$EVID/migrate-output.txt"; then
		sql "select concat_ws(' | ', creation, left(replace(error, '\\n', ' '), 600)) from \`tabError Log\` where method='BSG-REL-1' order by creation;" | tee "$EVID/bsg-rel-1-log.txt" || true
		fail "bench migrate failed - see migrate-output.txt and bsg-rel-1-log.txt (a schema-mismatch abort in reconcile_handover_condition_doctype changes nothing)"
	fi
	bench build --app bsgroup >/dev/null
	sql "select patch from \`tabPatch Log\` where patch like 'bsgroup.patches.%';" | tee "$EVID/fact-patch-log-post.txt"
	echo "-- BSG-REL-1 Error Log entries written by the patches (evidence, not errors)"
	sql "select concat_ws(' | ', creation, left(replace(error, '\n', ' '), 400)) from \`tabError Log\` where method='BSG-REL-1' order by creation;" | tee "$EVID/bsg-rel-1-log.txt"
	echo "-- party backfill: must be dry-run, 0 applied"
	sql "select error from \`tabError Log\` where error like '%party backfill summary%' order by creation desc limit 1;" > "$EVID/party-backfill-summary.txt" || true
	cat "$EVID/party-backfill-summary.txt"
	grep -q '"mode": "dry-run"' "$EVID/party-backfill-summary.txt" && grep -q '"applied": 0' "$EVID/party-backfill-summary.txt" || fail "party backfill summary missing, not dry-run, or applied != 0"
	ls -la "sites/$SITE/private/files/" | grep "bsg-rel-1-party-backfill-dry-run" | tee "$EVID/party-backfill-report.txt" || true
	counts | tee "$EVID/counts-post-migrate.psv"
	target_row | tee "$EVID/target-post-migrate.psv"
	diff <(cut -d'|' -f1-7 "$EVID/target-pre-migrate.psv") <(cut -d'|' -f1-7 "$EVID/target-post-migrate.psv") || fail "migrate changed the target sheet's totals/quotation/status"
	pass "migrated to $REL_COMMIT; party backfill dry-run (applied 0); target sheet unchanged"
	;;
4|tests)
	require_prev 3
	cd "$BENCH"
	: > "$EVID/tests.txt"; failed=0
	for m in "${MODULES[@]}"; do
		echo "=== $m" | tee -a "$EVID/tests.txt"
		if bench --site "$SITE" run-tests --module "$m" 2>&1 | tee -a "$EVID/tests.txt" | tail -5 | grep -qE '^OK'; then
			echo "RESULT $m OK" | tee -a "$EVID/tests.txt"
		else
			echo "RESULT $m NOT-OK" | tee -a "$EVID/tests.txt"; failed=1
		fi
	done
	counts | tee "$EVID/counts-post-tests.psv"
	[ "$failed" = 0 ] || fail "one or more modules not OK - classify each failure in the report (see README: expected erp-om skip/fail of the strict amendment-flow test)"
	pass "all four DCS test modules OK"
	;;
5|deskcheck)
	require_prev 3
	[ -n "$DESK_USER" ] || fail "set DESK_USER to a user with Presales / Sales Manager / Commercial Controller / Managing Director (System Manager alone is refused by design)"
	if [ "$ARG2" != "verify" ]; then
		target_row | tee "$EVID/target-before-desk.psv"
		sql "select count(*) from \`tabDCS Revision\` where dcs='$TARGET_DCS';" | tee "$EVID/target-revisions-before.txt"
		sql "select count(*) from \`tabDCS Governance Event\` where dcs='$TARGET_DCS';" | tee "$EVID/target-events-before.txt"
		echo "-- screen3 capability for $DESK_USER (read-only service; must show can_vendor_side = 1)"
		py "
import frappe, json
frappe.init(site='$SITE'); frappe.connect(); frappe.set_user('$DESK_USER')
r = frappe.call('bsgroup.api.dcs.negotiation.dcs_screen3', dcs='$TARGET_DCS')
print(json.dumps(r.get('capability'), indent=1, default=str))
" | tee "$EVID/screen3-capability.json"
		grep -qE '"can_vendor_side": (1|true)' "$EVID/screen3-capability.json" || fail "$DESK_USER has no vendor-side authority - Vendor Revision will not render"
		if [ -n "${DESK_USER_PW:-}" ]; then
			(cd "$BENCH" && bench --site "$SITE" set-password "$DESK_USER" "$DESK_USER_PW" >/dev/null) \
				&& echo "staging-only password set for $DESK_USER" \
				|| echo "NOTE: set-password unavailable; as Administrator open User $DESK_USER on $SITE and set a staging password"
		fi
		cat <<MSG
NOW, IN THE BROWSER on $SITE as $DESK_USER (screenshots into $EVID):
  1. Open $TARGET_DCS. Confirm the 'Negotiation' button group shows 'Vendor Revision'.     [screenshot 1]
  2. Negotiation -> Vendor Revision. New Total Cost = $NEW_COST, Reason = "$REASON". Apply.  [screenshot 2]
  3. Expect a green 'Recorded' alert and the form to reload.                                   [screenshot 3]
  4. Open the linked Quotation: still linked to $TARGET_DCS, status unchanged.               [screenshot 4]
Then run:  bash $0 5 verify
MSG
		pass "pre-desk state captured; $DESK_USER has vendor-side authority"
	else
		before_rev=$(cat "$EVID/target-revisions-before.txt"); before_ev=$(cat "$EVID/target-events-before.txt")
		pre=$(cat "$EVID/target-before-desk.psv"); post=$(target_row | tee "$EVID/target-after-desk.psv")
		sql "select concat_ws('|',name,revision_no,source,reason,prev_total_cost,new_total_cost,prev_total_selling,new_total_selling,new_margin_percent,approval_requirement,approval_state,margin_gate)
			from \`tabDCS Revision\` where dcs='$TARGET_DCS' order by revision_no;" | tee "$EVID/target-revisions-after.psv"
		sql "select concat_ws('|',name,event_code,actor,revision_no,revision_reference,change_count,reason)
			from \`tabDCS Governance Event\` where dcs='$TARGET_DCS' order by creation;" | tee "$EVID/target-events-after.psv"
		after_rev=$(wc -l < "$EVID/target-revisions-after.psv"); after_ev=$(wc -l < "$EVID/target-events-after.psv")
		IFS='|' read -r _ ds tc ts q st rn wc ws wm ap mg <<< "$post"
		IFS='|' read -r _ _ tc0 ts0 q0 st0 rn0 _ _ _ _ _ <<< "$pre"
		ok=1
		[ "$ds" = 1 ] || { echo "FAIL docstatus $ds"; ok=0; }
		[ "$tc" = "$tc0" ] && [ "$ts" = "$ts0" ] || { echo "FAIL submitted totals moved"; ok=0; }
		[ "$q" = "$q0" ] && [ "$st" = "$st0" ] || { echo "FAIL quotation link / deal status moved ($q0/$st0 -> $q/$st)"; ok=0; }
		awk -v w="$wc" 'BEGIN{exit !(w+0 > 1013.66 && w+0 < 1013.68)}' || { echo "FAIL working cost $wc"; ok=0; }
		[ "$ap" = "In Negotiation" ] && [ "$mg" = "Clear" ] || { echo "FAIL approval/gate $ap/$mg (expected In Negotiation/Clear)"; ok=0; }
		expect_rev=$(( rn0 == 0 ? 2 : 1 ))   # first revision on a sheet also writes the R1 baseline row
		[ $((after_rev - before_rev)) = "$expect_rev" ] || { echo "FAIL DCS Revision delta $((after_rev - before_rev)), expected $expect_rev"; ok=0; }
		[ $((after_ev - before_ev)) = 1 ] || { echo "FAIL Governance Event delta $((after_ev - before_ev)), expected 1"; ok=0; }
		grep -q "DCS_REVISION_APPLIED" "$EVID/target-events-after.psv" || { echo "FAIL no DCS_REVISION_APPLIED event"; ok=0; }
		if [ -n "$q" ]; then
			sql "select concat_ws('|',name,docstatus,status,ifnull(custom_deal_cost_sheet,'')) from \`tabQuotation\` where name='$q';" | tee "$EVID/target-quotation-after.psv"
			grep -q "|$TARGET_DCS\$" "$EVID/target-quotation-after.psv" || { echo "FAIL quotation no longer points at $TARGET_DCS"; ok=0; }
		else
			echo "NOTE: $TARGET_DCS has no linked Quotation on this backup - record 'n/a' for the Quotation check"
		fi
		[ "$ok" = 1 ] || fail "desk check verification failed"
		pass "vendor revision recorded: working cost $wc, margin $wm%, +$expect_rev DCS Revision, +1 Governance Event, quotation/status unchanged"
	fi
	;;
6|summary)
	require_prev 3
	counts > "$EVID/counts-final.psv"
	echo "== counts: pre-migrate -> post-migrate -> post-tests -> final"
	join -t'|' -a1 <(sort "$EVID/counts-pre-migrate.psv" | cut -d'|' -f1,2) <(sort "$EVID/counts-post-migrate.psv" | cut -d'|' -f1,2) \
		| join -t'|' -a1 - <(sort "$EVID/counts-post-tests.psv" 2>/dev/null | cut -d'|' -f1,2) \
		| join -t'|' -a1 - <(sort "$EVID/counts-final.psv" | cut -d'|' -f1,2) | column -t -s'|' | tee "$EVID/counts-table.txt"
	echo "== phase results"; for p in 0 1 2 3 4 5 6; do cat "$EVID/$p.result" 2>/dev/null || true; done
	pass "summary written to $EVID/counts-table.txt"
	;;
*)
	echo "usage: $0 {0|1|2|3|4|5 [verify]|6}"; exit 2;;
esac
