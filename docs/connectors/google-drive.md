# Google Drive Connector

## Authentication

Use a Google Cloud service account with Drive API access. For Workspace-wide discovery, configure domain-wide delegation and specify an impersonated user.

## Collected metadata

File ID, name, MIME type, size where reported, owners, permissions summary, creation and modification timestamps, Drive/shared-drive identity, and public-link exposure.

## Run

```bash
mkdir -p secrets
cp service-account.json secrets/gdrive-service-account.json
curl -X POST http://localhost:8080/api/v1/connectors/google-drive/scan \
 -H 'Content-Type: application/json' \
 -d '{"credentials_file":"/run/secrets/gdrive-service-account.json","impersonate_user":"security@example.com","max_files":500}'
```

The connector does not download document contents in Phase 1.
