# bsgroup.ai — server-side Claude integration for DCS → Quotation

This module adds AI-assisted **narrative** to the existing Deal Cost Sheet →
Quotation flow. It is additive and self-contained: no existing file is changed,
so it merges cleanly onto `main` and alongside `fix/dcs-core-release-1`.

## What it does

`generate_quotation_from_dcs(source_name, …)` builds a **draft** Quotation from a
Deal Cost Sheet and fills its customer-facing narrative (subject, scope
overview, customer notes, per-line descriptions) using Claude — while every
number comes from the ERP, not the model.

## Design guarantees

| Requirement | How it is met |
|---|---|
| API keys stay secure | Key lives only in `AI Provider Settings` (encrypted `Password`). Read server-side via `get_password`, never returned to the browser, logged, or put in a URL (`anthropic_client.py`). |
| Enforce permissions | `has_permission` gates on DCS `read` and Quotation `create` before anything is built, re-checked immediately before insert (`quotation_generator.py`). |
| Atomic draft creation | Items, company taxes and AI narrative are assembled in memory and written with a single `insert` inside a savepoint — no mid-flow commit, so a failure leaves no half-built draft (verified by `TestAtomicRollback`). |
| Company-specific taxes | The sales-tax template is resolved per company: the company default, else its only template, else a warning and no taxes (never a hardcoded UAE template). Works for the AE and OM companies. |
| Enforce calculations | Figures are computed from the DCS exactly as `Deal Cost Sheet.make_quotation` does (rates, qty, amounts, additional-charge item, currency). |
| Enforce approvals | Generation is blocked when the DCS margin gate is `Blocked`, MD/Blocked approval is required but not recorded, or an approval is in progress (`Pending Endorsement` / `In Negotiation`) — overridable only by System Manager / Sales Manager, and every override is audited (`narrative.approval_gate_block_reason`). |
| Supported model | Default model is `claude-sonnet-4-5` (the site's configured model); the settings value always takes precedence. A provider "model" / 404 error is surfaced as a clear "check the Model Name" message. |
| Flag missing costs, never invent | `narrative.detect_missing_costs` reports zero/blank costs, quantities and unconfigured additional-charge item; by default this **stops** generation. The model is told to emit `[NEEDS INPUT: …]` rather than fabricate, and any such marker is stripped and reported, never written to the customer document. |
| No figures to/from the model | `narrative.build_ai_context` sends descriptive fields only — no cost, selling, margin, GP or quantity. |
| Sanitised provider errors | Network / HTTP / parse failures return a generic message to the user; the detail is logged server-side only, and the API key never appears in a return value, log, error or URL. |
| Save as draft | The result is always a Quotation at `docstatus 0`; nothing is submitted or sent. |

## Endpoints

- `preview_dcs_readiness(source_name)` — read-only; returns block reason and
  missing-cost flags. Creates nothing.
- `generate_quotation_from_dcs(source_name, instructions=None,
  overwrite_narrative=0, ignore_missing_costs=0)` — creates the draft.

## Layout

- `anthropic_client.py` — secure provider config + HTTPS call (frappe + requests).
- `narrative.py` — pure, framework-free policy (redaction, missing-cost
  detection, approval gate, response parsing, write-back selection).
- `quotation_generator.py` — orchestration + whitelisted endpoints.
- `test_narrative.py` — pure unit tests (`python -m unittest`).
- `test_quotation_generator.py` — Frappe integration tests (network patched).

## DCS form button

An **AI Quotation Draft** button is added to the Deal Cost Sheet form (in the
`Create` group, submitted DCS only), next to the existing `Create Quotation`.
It calls `preview_dcs_readiness` first, shows any approval block, missing-cost
or tax warnings, then calls `generate_quotation_from_dcs` and routes to the new
draft. Added in `deal_cost_sheet.js` only — no `hooks.py` change.

## Not included (deliberate)

No new doctype and no `hooks.py`/`patches.txt`/fixtures change, so the branch
stays additive and conflict-neutral with `fix/dcs-core-release-1`.

## Testing

Run the integration tests on a **non-production** bench (e.g. `dcs-test.local`):
`bench --site dcs-test.local run-tests --module bsgroup.ai.test_quotation_generator`.
Pure unit tests need no bench: `python -m unittest bsgroup.ai.test_narrative`.
