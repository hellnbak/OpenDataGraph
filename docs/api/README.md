# API Guide

Interactive documentation is available at `/docs`.

## Primary resources

- `GET /api/v1/assets`
- `GET /api/v1/assets/{id}`
- `GET /api/v1/summary`
- `GET|POST /api/v1/agents`
- `POST /api/v1/policy/evaluate`
- `GET /api/v1/policy/audit`
- `POST /api/v1/demo/generate`
- `POST /api/v1/connectors/s3/scan`
- `POST /api/v1/connectors/google-drive/scan`

Policy responses include decision, risk score, reasons, required controls, policy version, and expiration.
