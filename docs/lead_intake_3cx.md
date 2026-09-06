# Lead Intake & 3CX Integration

The **Lead Intake** DocType (module *BS Group*) is the canonical staging record
for every inbound interaction — website chat, WhatsApp, calls, email, web forms
and manual/API entry. Integrations write **only** to Lead Intake; an ERPNext
`Lead` is created solely by the conversion step, and only from a *Qualified*
intake. This gives one place to normalize, de-duplicate and enrich before
anything reaches the CRM.

## Data flow

```
3CX / chat / web form
        │  (whitelisted API, authenticated, idempotent)
        ▼
   Lead Intake  ──normalize──▶ normalized_email / normalized_phone
        │        ──match─────▶ matched_lead / matched_contact / duplicate_of
        │        ──enqueue───▶ background AI placeholder (ai_status)
        │
        ▼  convert_to_lead()  (only when status = Qualified)
   ERPNext Lead   (company = "Bits Secure IT Infrastructure LLC - AE")
```

## Idempotency

Every interaction carries `external_system` (default `3CX`) and
`external_interaction_id`. These are combined into a unique
`idempotency_key = "<external_system>:<external_interaction_id>"`. Re-posting the
same interaction updates the existing record instead of creating a duplicate;
an unchanged re-delivery (same payload hash) is a no-op.

## Normalization

- **Email** — trimmed and lower-cased into `normalized_email`.
- **Phone** — converted to `+<country><national>` (E.164-style) in
  `normalized_phone`. A leading `+` or `00` is treated as international; a
  national number (optionally with a trunk `0`) is expanded using `country`
  (default `AE`). UAE (`971`) and Oman (`968`) are supported alongside other
  Gulf/international codes.

Duplicate matching uses the normalized values against prior Lead Intakes,
ERPNext Leads (`mobile_no` / `phone` / `whatsapp_no` / `email_id`) and Contacts.

## Authentication & permissions

- All endpoints require a **normal Frappe API login**. `Guest` is rejected.
- Writes rely on the **calling API user's** permissions — the user needs a role
  with create/write on *Lead Intake* (e.g. **Sales User**, **Sales Manager**,
  or **System Manager**).
- Create an API key/secret for a dedicated integration user via
  *User → Settings → API Access* (do **not** hard-code secrets), and call with:

  ```
  Authorization: token <API_KEY>:<API_SECRET>
  ```

- Writes are restricted to `POST`; `lookup` and `get_intake_status` also accept
  `GET`. Endpoints are rate-limited (per-interaction / per-IP) using Frappe's
  `rate_limit` facility.

## API routes

Base: `https://<your-site>/api/method/bsgroup.integrations.threecx.<method>`

| Method | HTTP | Purpose |
| --- | --- | --- |
| `lookup` | GET/POST | Screen-pop / de-dupe by phone or email |
| `create_contact` | POST | Stage a contact captured in 3CX |
| `chat_journal` | POST | Record a chat / WhatsApp interaction |
| `call_journal` | POST | Record a phone-call interaction |
| `get_intake_status` | GET/POST | Status of a previously journaled interaction |

### `lookup`

```bash
curl -sG "https://<your-site>/api/method/bsgroup.integrations.threecx.lookup" \
  -H "Authorization: token <API_KEY>:<API_SECRET>" \
  --data-urlencode "phone=+971501234567"
```

Response:

```json
{
  "message": {
    "ok": true,
    "normalized_phone": "+971501234567",
    "normalized_email": null,
    "matched": true,
    "lead": "CRM-LEAD-2026-00042",
    "contact": null,
    "lead_intake": { "name": "LI-2026-00007", "status": "New", "full_name": "Jane Doe", "converted_lead": null }
  }
}
```

### `call_journal`

```bash
curl -s "https://<your-site>/api/method/bsgroup.integrations.threecx.call_journal" \
  -H "Authorization: token <API_KEY>:<API_SECRET>" \
  -H "Content-Type: application/json" \
  -d '{
        "external_system": "3CX",
        "external_interaction_id": "3CX-CALL-000123",
        "direction": "Inbound",
        "phone": "+971501234567",
        "full_name": "Jane Doe",
        "agent_extension": "101",
        "agent_name": "Sales Agent",
        "interaction_started_on": "2026-09-06 10:00:00",
        "interaction_ended_on": "2026-09-06 10:04:30",
        "subject": "Enquiry about CCTV",
        "transcript": "<call notes / transcript>",
        "request_id": "<optional-idempotency-request-id>"
      }'
```

### `chat_journal`

```bash
curl -s "https://<your-site>/api/method/bsgroup.integrations.threecx.chat_journal" \
  -H "Authorization: token <API_KEY>:<API_SECRET>" \
  -H "Content-Type: application/json" \
  -d '{
        "external_system": "3CX",
        "external_interaction_id": "3CX-CHAT-000456",
        "source_channel": "WhatsApp",
        "direction": "Inbound",
        "phone": "+971501234567",
        "email": "jane.doe@example.com",
        "subject": "Pricing question",
        "transcript": "<chat transcript>"
      }'
```

### `create_contact`

```bash
curl -s "https://<your-site>/api/method/bsgroup.integrations.threecx.create_contact" \
  -H "Authorization: token <API_KEY>:<API_SECRET>" \
  -H "Content-Type: application/json" \
  -d '{
        "external_interaction_id": "3CX-CONTACT-000789",
        "full_name": "Jane Doe",
        "organization_name": "Example LLC",
        "email": "jane.doe@example.com",
        "phone": "+971501234567",
        "country": "AE"
      }'
```

### `get_intake_status`

```bash
curl -sG "https://<your-site>/api/method/bsgroup.integrations.threecx.get_intake_status" \
  -H "Authorization: token <API_KEY>:<API_SECRET>" \
  --data-urlencode "external_interaction_id=3CX-CALL-000123" \
  --data-urlencode "external_system=3CX"
```

Every write returns a stable envelope:

```json
{
  "message": {
    "ok": true,
    "created": true,
    "intake": "LI-2026-00008",
    "idempotency_key": "3CX:3CX-CALL-000123",
    "status": "New",
    "ai_status": "Queued",
    "duplicate_of": null,
    "matched_lead": null,
    "matched_contact": null
  }
}
```

## AI enrichment (placeholder)

On create, a background job (`run_ai_placeholder`) is enqueued. It requires **no
AI key**: it sets `ai_status`, a short PII-light `ai_summary`, a heuristic
`ai_qualification` and `ai_next_action`. Swap in a real model later by editing
that one function. If the broker is unavailable the write still succeeds and the
intake is left `Queued` for a later retry.

## Conversion to Lead

`convert_to_lead()` (button on the form, or `frm.call`) creates or links an
ERPNext Lead **only** when `status = Qualified`. It is idempotent — once
`converted_lead` is set it is returned unchanged — and reuses an already-matched
Lead rather than creating a duplicate. Company context
`Bits Secure IT Infrastructure LLC - AE` is preserved on the Lead when that
Company exists.

## Logging & privacy

Each write emits a redacted **Integration Request** log containing only
non-sensitive metadata (endpoint, external ids, request id, source channel,
booleans for has_email/has_phone, transcript length). Transcripts, subjects,
names, emails and phone numbers are **never** written to logs.
