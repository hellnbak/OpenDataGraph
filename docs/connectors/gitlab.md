# GitLab Connector

The GitLab connector inventories projects for a group, including subgroup projects. It supports the hosted service and self-managed API URLs.

## Permissions

Use a short-lived token with read-only API access scoped to the approved group.

## Collected metadata

- group and project identity
- project URL
- visibility
- creation and last-activity timestamps
- default branch
- archived state

Repository contents are not downloaded.

## Incremental behavior

The adapter uses provider pagination and returns the next page as an opaque cursor.
