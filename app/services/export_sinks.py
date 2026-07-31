import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import format_datetime
from urllib.parse import quote, urlsplit

from app.config import settings


@dataclass(frozen=True)
class ExportSinkAdapter:
    validate: Callable[[str], None]
    store: Callable[[str, bytes, str, str], str]


_EXPORT_SINKS: dict[str, ExportSinkAdapter] = {}


def register_export_sink(scheme: str, adapter: ExportSinkAdapter) -> None:
    normalized = scheme.strip().lower()
    if not normalized or not normalized.replace("-", "").isalnum():
        raise ValueError("Export sink scheme is invalid")
    _EXPORT_SINKS[normalized] = adapter


def validate_export_sink(uri: str) -> None:
    adapter = _adapter_for_uri(uri)
    adapter.validate(uri)


def store_export_sink(
    uri: str,
    content: bytes,
    content_type: str,
    digest: str,
) -> str:
    adapter = _adapter_for_uri(uri)
    adapter.validate(uri)
    return adapter.store(uri, content, content_type, digest)


def export_sink_schemes() -> list[str]:
    return sorted(_EXPORT_SINKS)


def _adapter_for_uri(uri: str) -> ExportSinkAdapter:
    scheme = urlsplit(uri).scheme.lower()
    adapter = _EXPORT_SINKS.get(scheme)
    if not adapter:
        supported = ", ".join(export_sink_schemes())
        raise ValueError(f"Unsupported graph export sink scheme; expected {supported}")
    return adapter


def _validate_s3(uri: str) -> None:
    parsed = urlsplit(uri)
    if parsed.scheme != "s3" or not parsed.netloc or not parsed.path.strip("/"):
        raise ValueError("Graph export S3 sink must use s3://bucket/key")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Graph export sink cannot contain credentials or query parameters")
    if parsed.netloc not in settings.graph_export_allowed_sink_buckets:
        raise ValueError("Graph export sink bucket is not allowlisted")


def _store_s3(uri: str, content: bytes, content_type: str, digest: str) -> str:
    parsed = urlsplit(uri)
    _graph_s3_client().put_object(
        Bucket=parsed.netloc,
        Key=parsed.path.lstrip("/"),
        Body=content,
        ContentType=content_type,
        Metadata={"sha256": digest},
    )
    return uri


def _validate_gcs(uri: str) -> None:
    parsed = urlsplit(uri)
    if parsed.scheme != "gs" or not parsed.netloc or not parsed.path.strip("/"):
        raise ValueError("Graph export GCS sink must use gs://bucket/key")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Graph export sink cannot contain credentials or query parameters")
    if parsed.netloc not in settings.graph_export_gcs_allowed_sink_buckets:
        raise ValueError("Graph export GCS sink bucket is not allowlisted")
    if not settings.graph_export_gcs_exchange_profile:
        raise ValueError("Graph export GCS sinks require a workload exchange profile")


def _store_gcs(uri: str, content: bytes, content_type: str, digest: str) -> str:
    import httpx

    from app.services.workload_exchange import bearer_token

    parsed = urlsplit(uri)
    token = bearer_token(settings.graph_export_gcs_exchange_profile, "gcp")
    response = httpx.post(
        f"https://storage.googleapis.com/upload/storage/v1/b/{quote(parsed.netloc, safe='')}/o",
        params={"uploadType": "media", "name": parsed.path.lstrip("/")},
        content=content,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": content_type,
            "X-Goog-Meta-SHA256": digest,
        },
        timeout=settings.graph_export_https_timeout_seconds,
        follow_redirects=False,
    )
    response.raise_for_status()
    return uri


def _validate_azure(uri: str) -> None:
    parsed = urlsplit(uri)
    parts = parsed.path.strip("/").split("/", 1)
    if (
        parsed.scheme != "azblob"
        or not parsed.netloc
        or len(parts) != 2
        or not all(parts)
        or not re.fullmatch(r"[a-z0-9]{3,24}", parsed.netloc)
        or not re.fullmatch(
            r"(?=.{3,63}$)[a-z0-9](?:[a-z0-9-]*[a-z0-9])",
            parts[0],
        )
    ):
        raise ValueError("Graph export Azure sink must use azblob://account/container/blob")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Graph export sink cannot contain credentials or query parameters")
    if f"{parsed.netloc}/{parts[0]}" not in settings.graph_export_azure_allowed_sinks:
        raise ValueError("Graph export Azure sink is not allowlisted")
    if not settings.graph_export_azure_exchange_profile:
        raise ValueError("Graph export Azure sinks require a workload exchange profile")


def _store_azure(uri: str, content: bytes, content_type: str, digest: str) -> str:
    import httpx

    from app.services.workload_exchange import bearer_token

    parsed = urlsplit(uri)
    container, blob = parsed.path.strip("/").split("/", 1)
    token = bearer_token(settings.graph_export_azure_exchange_profile, "azure")
    encoded_blob = "/".join(quote(part, safe="") for part in blob.split("/"))
    response = httpx.put(
        f"https://{parsed.netloc}.blob.core.windows.net/{quote(container, safe='')}/{encoded_blob}",
        content=content,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": content_type,
            "X-Ms-Blob-Type": "BlockBlob",
            "X-Ms-Date": format_datetime(datetime.now(UTC), usegmt=True),
            "X-Ms-Version": "2023-11-03",
            "X-Ms-Meta-SHA256": digest,
        },
        timeout=settings.graph_export_https_timeout_seconds,
        follow_redirects=False,
    )
    response.raise_for_status()
    return uri


def _validate_https(uri: str) -> None:
    parsed = urlsplit(uri)
    if parsed.scheme != "https" or not parsed.hostname or not parsed.path:
        raise ValueError("Graph export HTTPS sink must use an absolute HTTPS URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("Graph export sink cannot contain credentials or query parameters")
    if parsed.hostname.lower() not in settings.graph_export_https_allowed_hosts:
        raise ValueError("Graph export HTTPS sink host is not allowlisted")
    if not settings.graph_export_https_identity_token_file:
        raise ValueError(
            "Graph export HTTPS sinks require a mounted workload identity token file"
        )


def _store_https(
    uri: str,
    content: bytes,
    content_type: str,
    digest: str,
) -> str:
    import httpx

    from app.secrets import resolve_secret

    token_path = settings.graph_export_https_identity_token_file
    reference = token_path if token_path.startswith("file:") else f"file:{token_path}"
    token = resolve_secret(reference)
    response = httpx.put(
        uri,
        content=content,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": content_type,
            "X-Content-SHA256": digest,
        },
        timeout=settings.graph_export_https_timeout_seconds,
        follow_redirects=False,
    )
    response.raise_for_status()
    return uri


def _graph_s3_client():
    import boto3

    kwargs = {}
    if settings.graph_export_endpoint_url:
        kwargs["endpoint_url"] = settings.graph_export_endpoint_url
    if settings.graph_export_region:
        kwargs["region_name"] = settings.graph_export_region
    if settings.graph_export_s3_exchange_profile:
        from app.services.workload_exchange import boto_credentials

        kwargs.update(boto_credentials(settings.graph_export_s3_exchange_profile))
    return boto3.client("s3", **kwargs)


register_export_sink("s3", ExportSinkAdapter(_validate_s3, _store_s3))
register_export_sink("https", ExportSinkAdapter(_validate_https, _store_https))
register_export_sink("gs", ExportSinkAdapter(_validate_gcs, _store_gcs))
register_export_sink("azblob", ExportSinkAdapter(_validate_azure, _store_azure))
