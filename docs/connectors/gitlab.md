# GitLab Connector

The GitLab connector inventories projects for a group, including subgroup projects. It supports the hosted service and self-managed API URLs.

## Permissions

Use a short-lived token with read-only API access scoped to the approved group.

Endpoints must use HTTPS and their host must be listed in `ODG_GITLAB_ALLOWED_HOSTS`. Add only approved self-managed GitLab hosts.

## Collected metadata

Group and project identity, project URL, visibility, provider creation and last-activity timestamps, default branch, and archived state. Repository contents are not downloaded.

`public_access` is true only when the provider reports `public` visibility.

## Pagination and rate limits

The adapter requests at most 100 projects and returns the next page number as an opaque cursor. Provider rate-limit errors fail the current run and enter normal bounded retry behavior.

## Durable run

```json
{
  "account": "approved-group",
  "secret_ref": "env:ODG_GITLAB_TOKEN",
  "api_url": "https://gitlab.example.invalid/api/v4",
  "max_items": 100
}
```

Submit the payload to `POST /api/v1/connectors/gitlab/jobs`. The token value is never persisted. Imported and updated counts are recorded in connector-run and job results.
