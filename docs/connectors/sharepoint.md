# SharePoint and OneDrive Connector

The connector uses Microsoft Graph drive delta to inventory files and folders for an approved site and drive.

## Permissions

Prefer application access limited to selected sites and the least-privilege read permission required for the approved drive.

Graph endpoints and replayed delta cursors must use HTTPS and a host listed in `ODG_SHAREPOINT_ALLOWED_HOSTS`.

## Collected metadata

Site, drive, and item identity; item name and web URL; MIME type and size; creator identity when available; provider creation and modification timestamps; parent path; and ETag. Raw file content is not downloaded.

Public-link permissions are not evaluated in v1.9. `public_access` remains false and `metadata.public_access_evidence` is `not-evaluated`; this is not proof that an item is private.

## Pagination and rate limits

Microsoft Graph next and delta links are returned as opaque cursors and replayed exactly. Provider throttling fails the current run and enters normal bounded retry behavior.

## Durable run

```json
{
  "account": "approved-site-id",
  "site_id": "approved-site-id",
  "drive_id": "approved-drive-id",
  "secret_ref": "env:ODG_SHAREPOINT_TOKEN",
  "max_items": 500
}
```

Submit the payload to `POST /api/v1/connectors/sharepoint/jobs`. The token value is never persisted. Imported and updated counts are recorded in connector-run and job results.
