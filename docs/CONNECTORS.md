# Connectors

OpenDataGraph v1.1 includes metadata-first adapters for:

- AWS S3
- Google Drive
- GitHub
- GitLab
- SharePoint / OneDrive

All connectors normalize source records before catalog ingestion. The connector framework records run state, imported and updated counts, safe errors, timestamps, and cursor progression where the provider supports incremental discovery.

## Credential principles

- Use short-lived credentials.
- Grant only metadata read permissions for approved accounts, organizations, groups, sites, drives, buckets, or prefixes.
- Do not place provider credentials in request examples or logs.
- Store deployment secrets in an approved external secret manager.

## Scans

AWS S3 and Google Drive retain their dedicated endpoints. GitHub, GitLab, and SharePoint use:

```text
POST /api/v1/connectors/{connector_type}/scan
```

The request accepts an account, optional cursor, maximum item count, short-lived token, and provider-specific identifiers. Tokens are not stored in connector-run history.

See [Connector SDK](CONNECTOR_SDK.md) and the provider guides under `docs/connectors/`.
