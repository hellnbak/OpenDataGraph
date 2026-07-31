import argparse
import json

from connectors.registry import connector_manifests, connector_registration
from connectors.sdk import AssetRecord, Connector, ConnectorManifest, ScanBatch


def run_connector_conformance(
    connector: Connector,
    manifest: ConnectorManifest,
    max_items: int = 2,
) -> dict:
    checks = {
        "source_matches_manifest": connector.source == manifest.connector_type,
        "account_is_bounded": isinstance(connector.account, str) and 0 < len(connector.account) <= 240,
        "scan_batch": False,
        "bounded_records": False,
        "normalized_records": False,
        "cursor_is_opaque_state": False,
        "metadata_only": False,
    }
    batch = connector.scan(cursor=None, max_items=max_items)
    checks["scan_batch"] = isinstance(batch, ScanBatch)
    if not isinstance(batch, ScanBatch):
        return _report(manifest, checks)
    checks["bounded_records"] = len(batch.records) <= max_items
    checks["normalized_records"] = all(
        isinstance(record, AssetRecord)
        and record.source == manifest.connector_type
        and isinstance(record.external_id, str)
        and bool(record.external_id)
        for record in batch.records
    )
    checks["cursor_is_opaque_state"] = batch.next_cursor is None or (
        isinstance(batch.next_cursor, str) and 0 < len(batch.next_cursor) <= 2048
    )
    checks["metadata_only"] = (
        manifest.capabilities.content_access != "metadata-only"
        or all(
            not record.sample and record.metadata.get("content_retrieved") is not True
            for record in batch.records
        )
    )
    return _report(manifest, checks)


def validate_manifest(manifest: ConnectorManifest) -> dict:
    checks = {
        "versioned": bool(manifest.version),
        "sdk_versioned": bool(manifest.sdk_version),
        "permissions_declared": isinstance(manifest.permissions, tuple),
        "egress_declared": isinstance(manifest.egress_hosts, tuple),
        "content_access_declared": bool(manifest.capabilities.content_access),
        "timestamp_provenance_declared": bool(manifest.capabilities.timestamp_provenance),
        "public_access_declared": bool(manifest.capabilities.public_access_interpretation),
        "non_destructive": not manifest.capabilities.destructive_actions,
    }
    return _report(manifest, checks)


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect OpenDataGraph connector conformance")
    parser.add_argument("--connector")
    args = parser.parse_args()
    manifests = (
        [connector_registration(args.connector).manifest]
        if args.connector
        else connector_manifests()
    )
    reports = [validate_manifest(manifest) for manifest in manifests]
    print(json.dumps(reports, indent=2, sort_keys=True))
    if not all(report["conformant"] for report in reports):
        raise SystemExit(1)


def _report(manifest: ConnectorManifest, checks: dict[str, bool]) -> dict:
    return {
        "connector_type": manifest.connector_type,
        "connector_version": manifest.version,
        "manifest_digest": manifest.digest(),
        "conformant": all(checks.values()),
        "checks": checks,
    }


if __name__ == "__main__":
    main()
