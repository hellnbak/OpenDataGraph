# SharePoint and OneDrive Connector

The SharePoint connector uses Microsoft Graph drive delta to inventory files and folders for an approved site and drive.

## Permissions

Prefer application access limited to selected sites. Grant only the read permission required for the approved drive.

## Collected metadata

- site, drive, and item identity
- item name and web URL
- MIME type and size
- creator identity when available
- creation and modification timestamps
- parent path and ETag

Raw file content is not downloaded.

## Incremental behavior

Microsoft Graph next and delta links are returned as opaque cursors. Store and replay the cursor exactly as received.
