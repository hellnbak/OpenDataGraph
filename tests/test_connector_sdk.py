from connectors.sdk import AssetRecord, ScanBatch


def test_connector_sdk_preserves_cursor_and_normalized_asset():
    record = AssetRecord(
        source="github",
        source_account="example",
        external_id="github://example/catalog",
        name="catalog",
        path="https://example.invalid/catalog",
    )
    batch = ScanBatch(records=[record], next_cursor="2", complete=False)
    assert batch.records[0].as_dict()["external_id"] == "github://example/catalog"
    assert batch.next_cursor == "2"
    assert not batch.complete
