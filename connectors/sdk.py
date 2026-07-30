from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Protocol


@dataclass
class AssetRecord:
    source: str
    source_account: str
    external_id: str
    name: str
    path: str
    mime_type: str = "application/octet-stream"
    size_bytes: int = 0
    owner: str = "unknown"
    created_at: datetime | None = None
    modified_at: datetime | None = None
    last_accessed_at: datetime | None = None
    public_access: bool = False
    encryption: str = "Unknown"
    metadata: dict = field(default_factory=dict)
    sample: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass
class ScanBatch:
    records: list[AssetRecord]
    next_cursor: str | None = None
    complete: bool = True


class Connector(Protocol):
    source: str
    account: str

    def scan(self, cursor: str | None = None, max_items: int = 500) -> ScanBatch:
        ...
