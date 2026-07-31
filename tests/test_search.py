from app.models import DataAsset
from app.services.search import asset_document


def test_search_document_contains_metadata_not_sampled_content():
    asset = DataAsset(
        id=7,
        tenant_id="tenant-a",
        source="aws-s3",
        external_id="s3://example/report.csv",
        name="report.csv",
        path="s3://example/report.csv",
        metadata_json='{"sample": "must not be indexed"}',
    )
    document = asset_document(asset)
    assert document["tenant_id"] == "tenant-a"
    assert document["asset_id"] == 7
    assert "metadata_json" not in document
    assert "sample" not in document
