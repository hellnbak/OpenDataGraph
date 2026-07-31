# Evidence Storage

OpenDataGraph v1.2 stores approved audit evidence outside the relational database.

## Backends

- `local`: bounded objects under `ODG_EVIDENCE_LOCAL_DIRECTORY`
- `s3`: an S3-compatible bucket configured by `ODG_EVIDENCE_BUCKET`, optional endpoint, region, and prefix

The database stores tenant, evidence ID, category, subject, filename, content type, object URI, byte size, SHA-256 digest, metadata, creator, and timestamp.

## API

- `POST /api/v1/evidence`
- `GET /api/v1/evidence`
- `GET /api/v1/evidence/{evidence_id}/download`

Uploads use multipart form data and are limited by `ODG_EVIDENCE_MAX_BYTES`. Data-owner access is required to upload; auditor access is required to list or download.

## Safety

- Upload only approved audit material.
- Do not use evidence storage as a general source-content repository.
- Do not place credentials, tokens, prompts, or unnecessary personal data in evidence or metadata.
- Enable S3 versioning, encryption, public-access blocking, retention controls, and access logging.
- Evidence deletion and legal hold workflows are not included in v1.2.
