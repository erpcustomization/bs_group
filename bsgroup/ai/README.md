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
| No automatic bypass | A block is cleared only when the caller passes the matching explicit flag, holds the authority for it, **and** supplies `override_reason` (min length enforced). Missing-cost / tax overrides need `System Manager` / `Sales Manager`; an **approval** override needs an **approval-level authority** (`System Manager` / `Managing Director`) — a Sales Manager cannot wave through a commercial-approval block, matching the DCS approval model. Every applied override records its reason. |
| Override auditing atomic | The audit note recording the override + reason is written in the same savepoint as the insert; if it can't be written, the whole thing rolls back. |
| Submitted-DCS validation | A draft or cancelled Deal Cost Sheet is refused (`dcs_status`) — never overridable. |
| Atomic draft + atomic override audit | Items, taxes, all charges and AI narrative are inserted in one `insert`, and the audit note (which records any applied override) is written in the **same savepoint**; if the insert *or* the audit fails, everything rolls back — an override never persists unaudited (`TestAtomicRollback`, incl. a real rollback after an actual write). |
| Company-specific taxes | Resolved per company from the **enabled** templates (default → sole → warn). An unresolved template **blocks** generation (`tax_unresolved`) unless explicitly overridden. Never a hardcoded UAE template. |
| Complete tax-row copy | Tax rows are copied via ERPNext's own `get_taxes_and_charges`, preserving `charge_type`, `row_id` (On Previous Row Amount/Total), `rate`, `tax_amount` (Actual) and print flags — not a hand-picked subset that would break dependent/Actual templates. |
| Preserve all additional charges | Each additional-charge row becomes its **own** quotation line (description + amount). If the charges cannot be mapped to a valid, existing item, generation is **hard-blocked** (`charge_item_unmapped`, never overridable) — charges are never silently dropped. |
| Enforce calculations | Figures are computed from the DCS (rates, qty, amounts, additional charges, currency). |
| Supported model | Default model is `claude-sonnet-4-5` (the site's configured model); the settings value always takes precedence. A provider "model" / 404 error surfaces as "check the Model Name". |
| Sanitised logs & controlled errors | Failures log only the exception **type** (plus HTTP status / provider error-type code) — never the prompt, customer data, response body, config, key, or a traceback. The user sees the underlying message only for deliberately chosen safe validation types (mandatory / link / permission); every other unexpected error returns a generic controlled message. |
| Flag missing costs, never invent | `narrative.detect_missing_costs` reports zero/blank item and resource costs; by default this **stops** generation. The model is told to emit `[NEEDS INPUT: …]` rather than fabricate, and any such marker is stripped and reported, never written to the customer document. |
| Figures not sourced from the model, prose still reviewed | The model is sent descriptive fields only (no cost/selling/margin/GP/quantity) and instructed to write prose without figures — but this is **not** claimed as a guarantee. Any money-shaped text in the returned narrative is flagged for review, and the draft **always** carries an "AI-generated narrative — read and verify before sending" note. A human reviews every draft. |
| Save as draft (human review) | The result is always a Quotation at `docstatus 0`; nothing is submitted or sent, so a person reviews and edits before it goes out. |

## Endpoints

- `preview_dcs_readiness(source_name)` — read-only; returns block reason and
  missing-cost flags. Creates nothing.
- `generate_quotation_from_dcs(source_name, instructions=None,
  overwrite_narrative=0, override_approval=0, ignore_missing_costs=0,
  override_tax=0, override_reason=None)` — creates the draft. An `override_*`
  flag takes effect only for a caller with the authority for that block
  (approval needs approval-level authority) and only with a non-empty
  `override_reason`, which is audited.

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
