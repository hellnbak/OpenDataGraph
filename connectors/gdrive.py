from collections.abc import Callable, Iterator
from datetime import datetime
import json
from pathlib import Path

from .sdk import AssetRecord, ScanBatch


class GoogleDriveConnector:
    source = "google-drive"

    def __init__(
        self,
        account: str,
        credentials_info: dict,
        impersonate_user: str | None = None,
        drive_id: str | None = None,
        before_request: Callable[[], None] | None = None,
    ):
        self.account = account
        self.credentials_info = credentials_info
        self.impersonate_user = impersonate_user
        self.drive_id = drive_id
        self.before_request = before_request

    def scan(self, cursor: str | None = None, max_items: int = 500) -> ScanBatch:
        service = self._service()
        params = {
            "pageSize": min(1000, max_items),
            "pageToken": cursor,
            "q": "trashed = false",
            "fields": (
                "nextPageToken,files(id,name,mimeType,size,createdTime,modifiedTime,"
                "owners,permissions,parents,driveId,webViewLink,description,properties)"
            ),
            "supportsAllDrives": True,
            "includeItemsFromAllDrives": True,
        }
        if self.drive_id:
            params.update(corpora="drive", driveId=self.drive_id)
        if self.before_request:
            self.before_request()
        result = service.files().list(**params).execute()
        records = [_record(item, self.account) for item in result.get("files", [])[:max_items]]
        next_cursor = result.get("nextPageToken")
        return ScanBatch(records=records, next_cursor=next_cursor, complete=not next_cursor)

    def _service(self):
        try:
            from google.oauth2 import service_account
            from googleapiclient.discovery import build
        except ImportError as exc:
            raise RuntimeError("Install Google connector dependencies from requirements.txt") from exc
        scopes = ["https://www.googleapis.com/auth/drive.metadata.readonly"]
        credentials = service_account.Credentials.from_service_account_info(self.credentials_info, scopes=scopes)
        if self.impersonate_user:
            credentials = credentials.with_subject(self.impersonate_user)
        return build("drive", "v3", credentials=credentials, cache_discovery=False)


def scan_drive(
    credentials_file: str,
    impersonate_user: str | None = None,
    drive_id: str | None = None,
    max_files: int = 500,
) -> Iterator[dict]:
    credentials_info = json.loads(Path(credentials_file).read_text(encoding="utf-8"))
    account = drive_id or impersonate_user or "my-drive"
    batch = GoogleDriveConnector(account, credentials_info, impersonate_user, drive_id).scan(max_items=max_files)
    for record in batch.records:
        item = record.as_dict()
        item.pop("sample")
        yield item


def _record(item: dict, account: str) -> AssetRecord:
    owners = ",".join(
        owner.get("emailAddress") or owner.get("displayName", "unknown") for owner in item.get("owners", [])
    ) or "unknown"
    permissions = item.get("permissions", [])
    return AssetRecord(
        source="google-drive",
        source_account=item.get("driveId") or account,
        external_id=f"gdrive://{item['id']}",
        name=item["name"],
        path=item.get("webViewLink") or f"gdrive://{item['id']}",
        size_bytes=int(item.get("size", 0)),
        mime_type=item.get("mimeType", "application/octet-stream"),
        created_at=_dt(item.get("createdTime")),
        modified_at=_dt(item.get("modifiedTime")),
        owner=owners,
        encryption="Google-managed",
        public_access=any(permission.get("type") == "anyone" for permission in permissions),
        metadata={
            "parents": item.get("parents", []),
            "permissions": len(permissions),
            "description": item.get("description", ""),
            "properties": item.get("properties", {}),
        },
    )


def _dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None) if value else None
