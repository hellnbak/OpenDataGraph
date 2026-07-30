# GitHub Connector

The GitHub connector inventories repositories as normalized catalog assets. It supports the public service and compatible enterprise API URLs.

## Permissions

Use a short-lived installation or fine-grained token limited to repository metadata for the approved organization. Private repository discovery requires metadata access to those repositories.

## Collected metadata

- organization and repository identity
- repository URL
- visibility
- creation and update timestamps
- default branch
- primary language
- archived state

Repository contents are not downloaded.

## Incremental behavior

The adapter pages repositories ordered by update time and returns the next page as an opaque cursor.
