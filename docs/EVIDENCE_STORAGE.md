# Evidence Storage

OpenDataGraph v1.3 stores approved audit evidence outside the relational database and applies retention, deletion, and legal-hold governance.

## Backends

- `local`: bounded objects under `ODG_EVIDENCE_LOCAL_DIRECTORY`
- `s3`: an S3-compatible bucket configured by `ODG_EVIDENCE_BUCKET`, optional endpoint, region, and prefix

The database stores tenant, evidence ID, category, subject, filename, content type, object URI, byte size, SHA-256 digest, metadata, retention date, legal-hold state, deletion audit fields, creator, and timestamp.

## API

- `POST /api/v1/evidence`
- `GET /api/v1/evidence`
- `GET /api/v1/evidence/{evidence_id}/download`
- `PATCH /api/v1/evidence/{evidence_id}/governance`
- `DELETE /api/v1/evidence/{evidence_id}`
- `POST /api/v1/evidence/retention/jobs`

Uploads use multipart form data, are limited by `ODG_EVIDENCE_MAX_BYTES`, and receive the `ODG_EVIDENCE_DEFAULT_RETENTION_DAYS` period. Data-owner access is required to upload or change governance; auditor access is required to list or download.

Deletion removes object bytes while retaining deletion time, actor, and reason. Objects under legal hold cannot be deleted manually or by retention jobs. Listing hides deleted records unless `include_deleted=true`.

## Safety

- Upload only approved audit material.
- Do not use evidence storage as a general source-content repository.
- Do not place credentials, tokens, prompts, or unnecessary personal data in evidence or metadata.
- Enable S3 versioning, encryption, public-access blocking, retention controls, and access logging.
- Align application retention with object-store lifecycle and version-retention controls.
- Treat legal-hold release and deletion as privileged, reviewed actions.
