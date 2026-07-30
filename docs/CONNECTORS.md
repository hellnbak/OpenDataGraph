# Live Connectors

## AWS S3

Uses the normal AWS credential provider chain. Prefer a read-only assumed role granting `s3:ListBucket` and `s3:GetObject*` only for approved buckets.

```bash
curl -X POST http://localhost:8080/api/v1/connectors/s3/scan \
 -H 'Content-Type: application/json' \
 -d '{"bucket":"example-bucket","prefix":"","region":"us-east-1","max_objects":500}'
```

OpenDataGraph does not claim S3 `LastModified` is last access. Unknown access timestamps remain explicitly unknown.

## Google Drive

Enable Drive API, create a service account, and share a folder/shared drive with it. For Workspace-wide discovery, configure domain-wide delegation and provide `impersonate_user`.

```bash
curl -X POST http://localhost:8080/api/v1/connectors/google-drive/scan \
 -H 'Content-Type: application/json' \
 -d '{"credentials_file":"/run/secrets/gdrive.json","impersonate_user":"security@example.com","max_files":500}'
```

The default scope is metadata read-only. Public sharing is inferred from `anyone` permissions. Raw file content is not downloaded in this release.
