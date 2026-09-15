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
| Enforce permissions & mandatory fields | `has_permission` gates on DCS `read` and Quotation `create`; the Quotation is inserted **with permission checks and mandatory-field validation on** (no `ignore_permissions` / `ignore_mandatory`). A denied user or a missing mandatory field fails and rolls back. |
| No automatic bypass | A block (approval, missing costs, tax) is cleared only when the caller **both** holds an override role **and** passes the matching explicit flag (`override_approval` / `ignore_missing_costs` / `override_tax`). Holding the role is never enough; each applied override is audited. |
| Submitted-DCS validation | A draft or cancelled Deal Cost Sheet is refused (`dcs_status`) — never overridable. |
| Atomic draft creation | Items, taxes, all charges and AI narrative are assembled in memory and written with a single `insert` inside a savepoint; a failure after the write rolls back with no orphan draft (`TestAtomicRollback`, real and forced). |
| Company-specific taxes | Resolved per company (default → sole template → warn). An unresolved template **blocks** generation (`tax_unresolved`) unless explicitly overridden. Never a hardcoded UAE template. |
| Preserve all additional charges | Each additional-charge row becomes its **own** quotation line (description + amount), not one collapsed total. |
| Enforce calculations | Figures are computed from the DCS (rates, qty, amounts, additional charges, currency). |
| Supported model | Default model is `claude-sonnet-4-5` (the site's configured model); the settings value always takes precedence. A provider "model" / 404 error surfaces as "check the Model Name". |
| Sanitised logs | Failures log only the exception **type** (and HTTP status / provider error-type code); never the prompt, customer data, response body, config or API key, and never a full traceback (which could carry locals in developer mode). |
| Flag missing costs, never invent | `narrative.detect_missing_costs` reports zero/blank costs, quantities and unconfigured additional-charge item; by default this **stops** generation. The model is told to emit `[NEEDS INPUT: …]` rather than fabricate, and any such marker is stripped and reported, never written to the customer document. |
| No figures to/from the model | `narrative.build_ai_context` sends descriptive fields only — no cost, selling, margin, GP or quantity. |
| Save as draft | The result is always a Quotation at `docstatus 0`; nothing is submitted or sent. |

## Endpoints

- `preview_dcs_readiness(source_name)` — read-only; returns block reason and
  missing-cost flags. Creates nothing.
- `generate_quotation_from_dcs(source_name, instructions=None,
  overwrite_narrative=0, override_approval=0, ignore_missing_costs=0,
  override_tax=0)` — creates the draft. Each `override_*` flag takes effect
  only for an override-role caller and is audited.

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
