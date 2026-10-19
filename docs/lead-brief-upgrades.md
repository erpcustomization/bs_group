# Lightweight Lead view — upgrade boundaries

17 October 2026. UI source: bsgroup/public/js/Lead.js, loaded by the existing bsgroup Lead form hook. No Frappe/ERPNext core file, schema, global theme, permission or AI provider configuration was changed.

## Loading and readability

The overview shows contact identity, native processing/classification/confidence/review badges, the requirement summary and next action first. Native details elements progressively disclose extracted facts, model reasoning/audit, original enquiry/source and recent links. AI & Routing opens extracted facts and reasoning by default. No polling, timers, animation packages, remote fonts or UI dependencies were added. Native ERP color variables and components are used; the responsive grid is scoped to the brief.

Creating enquiries load as one full record. History reads 8 metadata fields for at most 20 records, excluding transcript and model JSON. A matched-only Lead requests one selected full enquiry after metadata; it never loads full detail for every history row. Existing Frappe permission checks remain active. No new AI request is made by viewing or refreshing the screen. These are structural payload improvements; no latency percentage is claimed.

## Upgrade approach

Keep the customization in the version-controlled app and promote the merged source branch during future normal releases. Current production is a selected-bench dynamic script patch; no broad asset build or database migration is needed for this file. To roll back this UI enhancement while keeping the earlier blank-tab repair, restore Lead.before-visibility-upgrade.js, not the obsolete enterprise presentation script.

The mount adapter targets the first native form tab and the existing bsi_ai_tab (with a bsi_ai_section fallback). If native tab markup changes, adapt that one mount function rather than modifying core. Parsing, read orchestration and rendering are separate helpers. Missing or denied reads produce explicit states; new records and stale responses are guarded. Future schema/permission changes should be checked against the explicit field lists and existing API, without bypassing access checks.

Before any ERP upgrade, verify: Details/AI after refresh and reopen; disclosure keyboard operation; 390px requested narrow viewport and normal desktop layout; original message/source accessibility; review vs confidence labels; linked support/careers separation; missing/denied reads; new Lead cleanup and late-response protection; native fields and Opportunity organization mapping. Re-run focused checks and the browser smoke walkthrough. No claim of compatibility with untested future ERP versions is made.

## Shared sales queue

The brief derives its Assigned team line from the native form docinfo active assignments (with Lead `_assign` fallback), using existing user names when available. A blank lead_owner is valid for the shared queue. Rendering adds no data requests or permission changes. If no assignments exist, the explicit Lead owner/unassigned fallback remains. Shared assignment, malformed storage and HTML escaping are covered in the 50 focused checks.


## Production branch repair - 19 October 2026

The live UAE bench uses main. Earlier repairs on fix/dcs-core-release-1 were absent after a normal main deployment. Keep this file, tests/lead_customer_brief.test.cjs and bsgroup/public/js/Lead.js on main. Run `node tests/lead_customer_brief.test.cjs` (50 checks). The app hook is authoritative; disabling the database Client Script alone does not disable app-loaded Lead code. Avoid restoring hide_empty_sections or enterprise layout injection. Verify both native tabs after a hard refresh, customer summary/source, active assignments and reviewed state. No guest access or permission changes are needed for this UI repair.
