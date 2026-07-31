from datetime import datetime
from collections.abc import Callable, Iterable
from urllib.parse import quote

from .security import validate_https_url
from .sdk import AssetRecord, ScanBatch


class SharePointConnector:
    source = "sharepoint"

    def __init__(
        self,
        site_id: str,
        drive_id: str,
        token: str,
        allowed_hosts: Iterable[str] = ("graph.microsoft.com",),
        before_request: Callable[[], None] | None = None,
    ):
        self.account = site_id
        self.site_id = site_id
        self.drive_id = drive_id
        self.token = token
        self.allowed_hosts = tuple(allowed_hosts)
        self.before_request = before_request

    def scan(self, cursor: str | None = None, max_items: int = 500) -> ScanBatch:
        import httpx

        url = validate_https_url(
            cursor or f"https://graph.microsoft.com/v1.0/drives/{quote(self.drive_id)}/root/delta",
            self.allowed_hosts,
        )
        if self.before_request:
            self.before_request()
        response = httpx.get(url, headers={"Authorization": f"Bearer {self.token}"}, timeout=30)
        response.raise_for_status()
        payload = response.json()
        items = [item for item in payload.get("value", []) if "deleted" not in item][:max_items]
        records = [
            AssetRecord(
                source=self.source,
                source_account=self.site_id,
                external_id=f"sharepoint://{self.drive_id}/{item['id']}",
                name=item["name"],
                path=item.get("webUrl") or f"sharepoint://{self.drive_id}/{item['id']}",
                mime_type=item.get("file", {}).get("mimeType", "application/vnd.microsoft.folder"),
                size_bytes=item.get("size", 0),
                owner=item.get("createdBy", {}).get("user", {}).get("email", "unknown"),
                created_at=_dt(item.get("createdDateTime")),
                modified_at=_dt(item.get("lastModifiedDateTime")),
                public_access=False,
                encryption="Microsoft-managed",
                metadata={
                    "site_id": self.site_id,
                    "drive_id": self.drive_id,
                    "parent_path": item.get("parentReference", {}).get("path"),
                    "etag": item.get("eTag"),
                    "public_access_evidence": "not-evaluated",
                },
            )
            for item in items
        ]
        next_cursor = payload.get("@odata.nextLink") or payload.get("@odata.deltaLink")
        complete = "@odata.nextLink" not in payload
        return ScanBatch(records=records, next_cursor=next_cursor, complete=complete)


def _dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None) if value else None
