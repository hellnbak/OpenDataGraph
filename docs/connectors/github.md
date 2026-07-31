# GitHub Connector

The GitHub connector inventories repositories as normalized catalog assets. It supports the public service and compatible enterprise API URLs.

## Permissions

Use a short-lived installation or fine-grained token limited to metadata for the approved organization. Private repository discovery requires metadata access to those repositories.

Endpoints must use HTTPS and their host must be listed in `ODG_GITHUB_ALLOWED_HOSTS`. Add only approved GitHub Enterprise hosts.

## Collected metadata

Organization and repository identity, repository URL, visibility, provider creation and update timestamps, default branch, primary language, and archived state. Repository contents are not downloaded.

`public_access` is true only when the provider reports that the repository is not private.

## Pagination and rate limits

The adapter requests at most 100 repositories ordered by update time and returns the next page number as an opaque cursor. Provider rate-limit errors fail the current run and enter normal bounded retry behavior.

## Durable run

```json
{
  "account": "approved-organization",
  "secret_ref": "env:ODG_GITHUB_TOKEN",
  "api_url": "https://api.github.com",
  "max_items": 100
}
```

Submit the payload to `POST /api/v1/connectors/github/jobs`. The token value is never persisted. Imported and updated counts are recorded in connector-run and job results.
