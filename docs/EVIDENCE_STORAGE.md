# Evidence Storage

OpenDataGraph stores bounded evidence objects outside the relational database and keeps tenant, subject, integrity, retention, legal-hold, object-lock, disposition, and deletion metadata in the database.

## Backends and integrity

`ODG_EVIDENCE_BACKEND=local` stores objects below `ODG_EVIDENCE_LOCAL_DIRECTORY`. `ODG_EVIDENCE_BACKEND=s3` stores objects in `ODG_EVIDENCE_BUCKET` with an optional endpoint and region.

Uploads are limited by `ODG_EVIDENCE_MAX_BYTES`. Every object receives a SHA-256 digest. Downloads recompute and compare the digest before returning content.

## Retention and legal hold

New records receive `ODG_EVIDENCE_DEFAULT_RETENTION_DAYS` when positive. Data owners may update retention and application legal hold with an auditable reason. Application legal hold blocks manual deletion, retention deletion, and approved disposition execution.

The `evidence.retention` job examines expired, unheld records. By default it preserves v1.3 behavior and deletes eligible objects. When `ODG_EVIDENCE_DISPOSITION_APPROVAL_REQUIRED=true`, it creates pending dispositions instead.

## Object Lock verification

`POST /api/v1/evidence/{evidence_id}/verify-object-lock` records current storage protection:

- local storage: `not-applicable`
- verified S3 retention mode, retain-until date, and legal-hold state
- `unavailable` when configured credentials or storage do not allow verification

S3 verification uses object metadata and Object Lock APIs without retrieving evidence content. Grant only `s3:HeadObject`, `s3:GetObjectRetention`, and `s3:GetObjectLegalHold` in addition to required evidence operations.

## Disposition approval

Data owners request deletion through `POST /api/v1/evidence/{evidence_id}/dispositions`. Administrators list, approve, or reject requests:

- `GET /api/v1/evidence/dispositions`
- `POST /api/v1/evidence/dispositions/{disposition_id}/approve`
- `POST /api/v1/evidence/dispositions/{disposition_id}/reject`

Outside development mode, the requester cannot approve the same disposition. Approval queues `evidence.disposition`. Before deletion, the worker rechecks application legal hold and S3 object retention or legal hold. The disposition and evidence record retain who requested, approved, rejected, or executed the action.

Disposition requests also create unified governance review tasks. Approval or rejection completes the task; the disposition remains the authoritative execution state. See [Governance operations](GOVERNANCE_OPERATIONS.md).

Governance evidence packages are separate metadata-only artifacts. They reference evidence integrity and lifecycle state without copying evidence bytes, filenames, or storage locations. See [Governance analytics and evidence packages](GOVERNANCE_EVIDENCE_PACKAGES.md).

## Production controls

Use private versioned buckets, encryption, public-access blocking, workload identity, narrowly scoped object permissions, lifecycle policy, backup, and restore testing. Align bucket retention with OpenDataGraph retention. Application metadata cannot shorten compliance-mode Object Lock.
