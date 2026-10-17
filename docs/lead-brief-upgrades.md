# Lightweight Lead view — upgrade boundaries

17 October 2026. UI source: bsgroup/public/js/Lead.js, loaded by the existing bsgroup Lead form hook. No Frappe/ERPNext core file, schema, global theme, permission or AI provider configuration was changed.

## Loading and readability

The overview shows contact identity, native processing/classification/confidence/review badges, the requirement summary and next action first. Native details elements progressively disclose extracted facts, model reasoning/audit, original enquiry/source and recent links. AI & Routing opens extracted facts and reasoning by default. No polling, timers, animation packages, remote fonts or UI dependencies were added. Native ERP color variables and components are used; the responsive grid is scoped to the brief.

Creating enquiries load as one full record. History reads 8 metadata fields for at most 20 records, excluding transcript and model JSON. A matched-only Lead requests one selected full enquiry after metadata; it never loads full detail for every history row. Existing Frappe permission checks remain active. No new AI request is made by viewing or refreshing the screen. These are structural payload improvements; no latency percentage is claimed.

## Upgrade approach

Keep the customization in the version-controlled app and promote the merged source branch during future normal releases. Current production is a selected-bench dynamic script patch; no broad asset build or database migration is needed for this file. To roll back this UI enhancement while keeping the earlier blank-tab repair, restore bsgroup/public/js/Lead.js from commit 04dd77f1e2442ce5d3fde54d225029ac69c75ac6, not the obsolete enterprise presentation script.

The mount adapter targets the first native form tab and the existing bsi_ai_tab (with a bsi_ai_section fallback). If native tab markup changes, adapt that one mount function rather than modifying core. Parsing, read orchestration and rendering are separate helpers. Missing or denied reads produce explicit states; new records and stale responses are guarded. Future schema/permission changes should be checked against the explicit field lists and existing API, without bypassing access checks.

Before any ERP upgrade, verify: Details/AI after refresh and reopen; disclosure keyboard operation; 390px requested narrow viewport and normal desktop layout; original message/source accessibility; review vs confidence labels; linked support/careers separation; missing/denied reads; new Lead cleanup and late-response protection; native fields and Opportunity organization mapping. Re-run focused checks and the browser smoke walkthrough. No claim of compatibility with untested future ERP versions is made.

## Run the source regression checks

From the repository root, run `node tests/lead_customer_brief.test.cjs`. This dependency-free harness checks the rendering/data-read contract and race/error paths; it does not replace the browser walkthrough or a real salesperson login. Validate actual role permissions without widening access just to satisfy a test.
