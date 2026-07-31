from collections.abc import Callable, Iterator

from .sdk import AssetRecord, ScanBatch


class S3Connector:
    source = "aws-s3"

    def __init__(
        self,
        bucket: str,
        prefix: str = "",
        region: str | None = None,
        before_request: Callable[[], None] | None = None,
    ):
        self.account = bucket
        self.bucket = bucket
        self.prefix = prefix
        self.region = region
        self.before_request = before_request

    def scan(self, cursor: str | None = None, max_items: int = 500) -> ScanBatch:
        import boto3

        client = boto3.client("s3", region_name=self.region)
        public_access, public_access_evidence = _bucket_public_access(client, self.bucket, self.before_request)
        params = {"Bucket": self.bucket, "Prefix": self.prefix, "MaxKeys": min(max_items, 1000)}
        if cursor:
            params["ContinuationToken"] = cursor
        if self.before_request:
            self.before_request()
        response = client.list_objects_v2(**params)
        records = []
        for item in response.get("Contents", []):
            key = item["Key"]
            if self.before_request:
                self.before_request()
            head = client.head_object(Bucket=self.bucket, Key=key)
            records.append(
                AssetRecord(
                    source=self.source,
                    source_account=self.bucket,
                    external_id=f"s3://{self.bucket}/{key}",
                    name=key.rsplit("/", 1)[-1] or key,
                    path=f"s3://{self.bucket}/{key}",
                    size_bytes=item.get("Size", 0),
                    mime_type=head.get("ContentType", "application/octet-stream"),
                    modified_at=item.get("LastModified").replace(tzinfo=None) if item.get("LastModified") else None,
                    owner=head.get("Metadata", {}).get("owner", "unknown"),
                    encryption=head.get("ServerSideEncryption", "None detected"),
                    public_access=public_access,
                    metadata={
                        "etag": item.get("ETag", "").strip('"'),
                        "storage_class": item.get("StorageClass", "STANDARD"),
                        "public_access_evidence": public_access_evidence,
                    },
                )
            )
        return ScanBatch(
            records=records,
            next_cursor=response.get("NextContinuationToken"),
            complete=not response.get("IsTruncated", False),
        )


def scan_bucket(
    bucket: str,
    prefix: str = "",
    region: str | None = None,
    max_objects: int = 500,
) -> Iterator[dict]:
    connector = S3Connector(bucket, prefix, region)
    batch = connector.scan(max_items=max_objects)
    for record in batch.records:
        item = record.as_dict()
        item.pop("sample")
        yield item


def _bucket_public_access(
    client,
    bucket: str,
    before_request: Callable[[], None] | None = None,
) -> tuple[bool, str]:
    if before_request:
        before_request()
    try:
        status = client.get_bucket_policy_status(Bucket=bucket)
        return bool(status.get("PolicyStatus", {}).get("IsPublic", False)), "bucket-policy-status"
    except Exception:
        return False, "unknown-insufficient-permission"
