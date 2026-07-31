import hashlib
import re

from app.config import settings


def store_evidence(
    tenant_id: str,
    evidence_id: str,
    content: bytes,
    content_type: str = "application/octet-stream",
) -> tuple[str, str]:
    if len(content) > settings.evidence_max_bytes:
        raise ValueError(f"Evidence exceeds the {settings.evidence_max_bytes}-byte limit")
    digest = hashlib.sha256(content).hexdigest()
    object_key = _object_key(tenant_id, evidence_id)
    if settings.evidence_backend == "local":
        root = settings.evidence_local_directory.resolve()
        path = (root / object_key).resolve()
        if not path.is_relative_to(root):
            raise ValueError("Invalid local evidence path")
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_bytes(content)
        temporary.replace(path)
        return f"local://{object_key}", digest
    if settings.evidence_backend == "s3":
        if not settings.evidence_bucket:
            raise RuntimeError("ODG_EVIDENCE_BUCKET is required for S3 evidence storage")
        _s3_client().put_object(
            Bucket=settings.evidence_bucket,
            Key=object_key,
            Body=content,
            ContentType=content_type,
            Metadata={"sha256": digest},
        )
        return f"s3://{settings.evidence_bucket}/{object_key}", digest
    raise RuntimeError(f"Unsupported evidence backend: {settings.evidence_backend}")


def load_evidence(storage_uri: str) -> bytes:
    if storage_uri.startswith("local://"):
        object_key = storage_uri.removeprefix("local://")
        path = (settings.evidence_local_directory / object_key).resolve()
        root = settings.evidence_local_directory.resolve()
        if not path.is_relative_to(root):
            raise ValueError("Invalid local evidence path")
        content = path.read_bytes()
        if len(content) > settings.evidence_max_bytes:
            raise ValueError("Stored evidence exceeds the configured size limit")
        return content
    if storage_uri.startswith("s3://"):
        bucket_and_key = storage_uri.removeprefix("s3://")
        bucket, object_key = bucket_and_key.split("/", 1)
        content = _s3_client().get_object(Bucket=bucket, Key=object_key)["Body"].read(
            settings.evidence_max_bytes + 1
        )
        if len(content) > settings.evidence_max_bytes:
            raise ValueError("Stored evidence exceeds the configured size limit")
        return content
    raise ValueError("Unsupported evidence URI")


def evidence_health() -> dict:
    if settings.evidence_backend == "local":
        try:
            settings.evidence_local_directory.mkdir(parents=True, exist_ok=True)
            return {"backend": "local", "ok": True}
        except OSError as exc:
            return {"backend": "local", "ok": False, "error": type(exc).__name__}
    if settings.evidence_backend == "s3":
        try:
            _s3_client().head_bucket(Bucket=settings.evidence_bucket)
            return {"backend": "s3", "ok": True}
        except Exception as exc:
            return {"backend": "s3", "ok": False, "error": type(exc).__name__}
    return {"backend": settings.evidence_backend, "ok": False, "error": "unsupported_backend"}


def _object_key(tenant_id: str, evidence_id: str) -> str:
    safe_tenant = re.sub(r"[^A-Za-z0-9_.-]", "_", tenant_id)
    prefix = settings.evidence_prefix.strip("/")
    return "/".join(part for part in (prefix, safe_tenant, evidence_id) if part)


def _s3_client():
    import boto3

    kwargs = {}
    if settings.evidence_endpoint_url:
        kwargs["endpoint_url"] = settings.evidence_endpoint_url
    if settings.evidence_region:
        kwargs["region_name"] = settings.evidence_region
    return boto3.client("s3", **kwargs)
