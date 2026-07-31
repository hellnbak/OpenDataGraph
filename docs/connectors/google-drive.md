# Google Drive Connector

## Authentication and permissions

Use a service account with `https://www.googleapis.com/auth/drive.metadata.readonly`. For domain-wide discovery, configure approved delegation and an impersonated user.

The queued connector expects service-account JSON through a mounted secret reference. It does not persist the JSON or secret value.

The synchronous compatibility endpoint accepts only credential files below `ODG_SECRET_FILE_ROOTS`. Queued scans are recommended for shared deployments.

## Collected metadata

File ID, name, MIME type, size where reported, owners, permission count, provider creation and modification timestamps, Drive identity, parents, description, custom properties, and public-link exposure when a permission of type `anyone` is returned.

Document bodies are not downloaded.

## Pagination

Google `nextPageToken` values are returned and replayed unchanged. Each queued execution processes one bounded page.

## Durable run

```json
{
  "account": "workspace-example",
  "secret_ref": "file:/run/secrets/google-drive-service-account.json",
  "impersonate_user": "security@example.invalid",
  "drive_id": "approved-drive-id",
  "max_items": 500
}
```

Submit the payload to `POST /api/v1/connectors/google-drive/jobs`. Imported and updated counts are recorded in connector-run and job results.
