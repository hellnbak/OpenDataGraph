import hashlib
import json
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


@dataclass(frozen=True)
class ConnectorCapabilities:
    content_access: str = "metadata-only"
    pagination: bool = True
    incremental_cursor: bool = True
    opaque_cursor: bool = True
    rate_limit_behavior: str = "provider-aware"
    timestamp_provenance: tuple[str, ...] = ()
    public_access_interpretation: str = "not-evaluated"
    destructive_actions: bool = False


@dataclass(frozen=True)
class ConnectorManifest:
    connector_type: str
    display_name: str
    version: str
    permissions: tuple[str, ...]
    egress_hosts: tuple[str, ...]
    capabilities: ConnectorCapabilities = field(default_factory=ConnectorCapabilities)
    sdk_version: str = "2.0"
    description: str = ""
    plugin: bool = False

    def as_dict(self) -> dict:
        return asdict(self)

    def digest(self) -> str:
        content = json.dumps(
            self.as_dict(),
            separators=(",", ":"),
            sort_keys=True,
        ).encode()
        return hashlib.sha256(content).hexdigest()


class Connector(Protocol):
    source: str
    account: str

    def scan(self, cursor: str | None = None, max_items: int = 500) -> ScanBatch:
        ...
