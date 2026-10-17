# Confidential DCS commercial obligations

This change manages exceptional commercial commitments separately from the delivery BOQ. It adds no permanent DCS tab and writes no confidential amount, net contribution, obligation reference, approval reason or presence flag onto the parent DCS or Quotation.

## Audience and approval

The assigned Deal Owner must hold Sales User or Sales Manager and retain read access to that DCS. Sangeetha's existing account is the named Finance & Commercial Governance authority; Managing Director is the escalation role. Ordinary Commercial Controller or System Manager membership alone does not grant confidential access. Operations, Presales and engineering roles are excluded; Manikandan's account is explicitly excluded even if another commercial role is added.

The proposal maker submits a forecast draft. Sangeetha cannot approve her own proposal. Finance approval at a forecast net margin below 20% creates Pending MD, without an approved commitment. A distinct MD must approve that current financial position. Existing DCS commercial approval rules continue to apply independently.

Every proposal edit, decision, attachment and settlement evidence entry appends a private, immutable event. Incoming document flags cannot authorize a generic save, import or forged decision. Revision tokens reject concurrent or replayed edits.

## Financial model

Delivery selling, buying, GP and margin stay unchanged. Manikandan and Operations retain the native delivery financial fields and read-only Overview.

Forecast net contribution deducts active proposed obligations, including drafts and pending approvals. Approved commitments remain separate. A revised proposal keeps the previous approved amount and approved terms visible until a new decision. Percentage proposals use current customer selling in the DCS currency; approved commitments retain the amount accepted at approval.

Currency changes are blocked while obligations exist. Financial changes invalidate decisions through a fingerprint of currency, selling, delivery cost and total forecast obligations. Award, quotation submission, Sales Order conversion/submission and delivery release check current clearance while holding the DCS row lock. Public financial projections never include this private clearance result.

Finance can record cumulative accrual and paid evidence against a current approved commitment. These records do not book accounting entries or execute payments. Paid cannot exceed accrued; accrued cannot exceed the approved amount. A proposal cannot fall below recorded settlement amounts.

## Confidential surfaces

Direct reads, lists, report queries and auxiliary records have server-side permission filters. Generic write, export, email, share and delete rights are absent. Standard Frappe print view permits an authorized reader through its read-permission fallback; unauthorized print requests must fail.

Attachments are private, checked before bytes are written, and use a guarded download implementation. File ownership, shares, attachment aliases and reassignment do not override the obligation audience. File lists omit confidential attachments; authorized users open them through the private record. Ordinary Comment, Communication, Version, ToDo, DocShare and Notification Log records cannot be created against confidential records. Dedicated event history supplies the audit trail.

Existing reports, quotations, BOQ revisions and handover documents receive only the original delivery data. No confidential values are added to their payloads.

## Migration and release constraints

No financial backfill or historical amount migration is included. Recognized legacy consulting/partner charges block creation of a separate obligation on that sheet until Finance resolves the legacy treatment, preventing double counting. Existing legacy rows and comments are not altered. Cancel/amend of sheets with obligation history is held for commercial clearance rather than silently dropping that history.

Deploy the code and synchronize the two new DocTypes in staging before review. The branch contains no production deployment automation. Production release requires explicit controlled approval, a backup/rollback plan, region-specific base verification, staged acceptance and post-release smoke checks.

Administrative privilege separation is a release prerequisite. Frappe's trusted Administrator, database/hosting operators, and an account able to modify SQL reports or server-side code can bypass ordinary application permissions. The application cannot guarantee secrecy against those powers. Manikandan must retain delivery access while those administrative powers are separated from his operational account. Do not describe normal route-denial tests as proof against a malicious infrastructure administrator.

Historical consulting disclosures require an agreed remediation before claiming confidentiality for existing sheets. Resolve the disputed agreement before any amount migration.

## Verification

The committed synthetic integration tests are in bsgroup/dcs/test_obligation.py. They cover roles, maker/checker separation, exact/below-floor routing, multiple obligations, stale decisions, delivery invariance, quotation output, private files, audit records, concurrency tokens, currency and settlement controls. Run them on staging only. Native browser/HTTP evidence and wider existing DCS regression logs belong in the restricted release evidence package, not this public repository.
