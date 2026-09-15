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
| Enforce permissions | `has_permission` gates on DCS `read`, Quotation `create` and `write` before anything is built (`quotation_generator.py`). |
| Enforce company settings & calculations | The Quotation is built by the existing `make_quotation` on Deal Cost Sheet, so taxes, currency, additional-charge item and all line maths are the ERP's own. |
| Enforce approvals | Generation is blocked when the DCS margin gate is `Blocked`, or MD/Blocked approval is required but not recorded — overridable only by System Manager / Sales Manager (`narrative.approval_gate_block_reason`). |
| Flag missing costs, never invent | `narrative.detect_missing_costs` reports zero/blank costs, quantities and unconfigured additional-charge item; by default this **stops** generation. The model is told to emit `[NEEDS INPUT: …]` rather than fabricate, and any such marker is stripped and reported, never written to the customer document. |
| No figures to/from the model | `narrative.build_ai_context` sends descriptive fields only — no cost, selling, margin, GP or quantity. |
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

## Not included (deliberate, for a focused PR)

No desk/JS button, no new doctype, no `hooks.py`/`patches.txt`/fixtures change.
The endpoint can be wired to a DCS form button in a follow-up.
