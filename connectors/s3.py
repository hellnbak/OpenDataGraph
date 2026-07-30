from datetime import datetime
from typing import Iterator

def scan_bucket(bucket: str, prefix: str = "", region: str | None = None, max_objects: int = 500) -> Iterator[dict]:
    import boto3

    client = boto3.client("s3", region_name=region)
    paginator = client.get_paginator("list_objects_v2")
    seen = 0
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            head = client.head_object(Bucket=bucket, Key=key)
            yield {
                "source": "aws-s3",
                "source_account": bucket,
                "external_id": f"s3://{bucket}/{key}",
                "name": key.rsplit("/", 1)[-1] or key,
                "path": f"s3://{bucket}/{key}",
                "size_bytes": obj.get("Size", 0),
                "mime_type": head.get("ContentType", "application/octet-stream"),
                "created_at": None,
                "modified_at": obj.get("LastModified").replace(tzinfo=None) if obj.get("LastModified") else None,
                "last_accessed_at": None,
                "owner": head.get("Metadata", {}).get("owner", "unknown"),
                "encryption": head.get("ServerSideEncryption", "None detected"),
                "public_access": False,
                "metadata": {"etag": obj.get("ETag", "").strip('"'), "storage_class": obj.get("StorageClass", "STANDARD")},
            }
            seen += 1
            if seen >= max_objects:
                return
