import os
from pathlib import Path

from .version import VERSION


def _boolean(name: str, default: bool) -> bool:
    value = os.getenv(name)
    return default if value is None else value.lower() in {"1", "true", "yes", "on"}


def _integer(name: str, default: int) -> int:
    value = os.getenv(name)
    return default if value is None else int(value)


class Settings:
    app_name = os.getenv("ODG_APP_NAME", "OpenDataGraph")
    version = VERSION
    environment = os.getenv("ODG_ENVIRONMENT", "development")
    database_url = os.getenv("ODG_DATABASE_URL", "sqlite:///./opendatagraph.db")
    auto_create_schema = _boolean("ODG_AUTO_CREATE_SCHEMA", database_url.startswith("sqlite"))
    ollama_url = os.getenv("ODG_OLLAMA_URL", "http://host.docker.internal:11434")
    ollama_model = os.getenv("ODG_OLLAMA_MODEL", "qwen2.5:3b")
    classification_mode = os.getenv("ODG_CLASSIFICATION_MODE", "hybrid")
    classification_review_threshold = float(os.getenv("ODG_CLASSIFICATION_REVIEW_THRESHOLD", "0.70"))
    auto_seed_demo = _boolean("ODG_AUTO_SEED_DEMO", True)
    default_tenant = os.getenv("ODG_DEFAULT_TENANT", "default")
    auth_disabled = _boolean("ODG_AUTH_DISABLED", True)
    api_keys_json = os.getenv("ODG_API_KEYS_JSON", "{}")
    oidc_issuer = os.getenv("ODG_OIDC_ISSUER", "")
    oidc_audience = os.getenv("ODG_OIDC_AUDIENCE", "")
    oidc_jwks_url = os.getenv("ODG_OIDC_JWKS_URL", "")
    oidc_providers_json = os.getenv("ODG_OIDC_PROVIDERS_JSON", "{}")
    oidc_discovery_cache_seconds = _integer("ODG_OIDC_DISCOVERY_CACHE_SECONDS", 3600)
    oidc_http_timeout_seconds = float(os.getenv("ODG_OIDC_HTTP_TIMEOUT_SECONDS", "5"))
    scim_bearer_token = os.getenv("ODG_SCIM_BEARER_TOKEN", "")
    scim_tokens_json = os.getenv("ODG_SCIM_TOKENS_JSON", "{}")
    scim_bulk_max_operations = _integer("ODG_SCIM_BULK_MAX_OPERATIONS", 100)
    policy_directory = os.getenv("ODG_POLICY_DIRECTORY", "policies")
    search_backend = os.getenv("ODG_SEARCH_BACKEND", "database").lower()
    opensearch_url = os.getenv("ODG_OPENSEARCH_URL", "")
    opensearch_index_prefix = os.getenv("ODG_OPENSEARCH_INDEX_PREFIX", "opendatagraph")
    opensearch_required = _boolean("ODG_OPENSEARCH_REQUIRED", False)
    evidence_backend = os.getenv("ODG_EVIDENCE_BACKEND", "local").lower()
    evidence_local_directory = Path(os.getenv("ODG_EVIDENCE_LOCAL_DIRECTORY", "./evidence"))
    evidence_bucket = os.getenv("ODG_EVIDENCE_BUCKET", "")
    evidence_prefix = os.getenv("ODG_EVIDENCE_PREFIX", "evidence")
    evidence_endpoint_url = os.getenv("ODG_EVIDENCE_ENDPOINT_URL", "")
    evidence_region = os.getenv("ODG_EVIDENCE_REGION", "")
    evidence_max_bytes = _integer("ODG_EVIDENCE_MAX_BYTES", 10 * 1024 * 1024)
    evidence_default_retention_days = _integer("ODG_EVIDENCE_DEFAULT_RETENTION_DAYS", 365)
    evidence_disposition_approval_required = _boolean(
        "ODG_EVIDENCE_DISPOSITION_APPROVAL_REQUIRED",
        False,
    )
    secret_file_roots = tuple(
        Path(item.strip()).expanduser().resolve()
        for item in os.getenv("ODG_SECRET_FILE_ROOTS", "/run/secrets,./secrets").split(",")
        if item.strip()
    )
    github_allowed_hosts = tuple(
        item.strip().lower()
        for item in os.getenv("ODG_GITHUB_ALLOWED_HOSTS", "api.github.com").split(",")
        if item.strip()
    )
    gitlab_allowed_hosts = tuple(
        item.strip().lower()
        for item in os.getenv("ODG_GITLAB_ALLOWED_HOSTS", "gitlab.com").split(",")
        if item.strip()
    )
    sharepoint_allowed_hosts = tuple(
        item.strip().lower()
        for item in os.getenv("ODG_SHAREPOINT_ALLOWED_HOSTS", "graph.microsoft.com").split(",")
        if item.strip()
    )
    integration_allowed_hosts = tuple(
        item.strip().lower()
        for item in os.getenv("ODG_INTEGRATION_ALLOWED_HOSTS", "").split(",")
        if item.strip()
    )
    integration_timeout_seconds = float(os.getenv("ODG_INTEGRATION_TIMEOUT_SECONDS", "10"))
    worker_poll_seconds = float(os.getenv("ODG_WORKER_POLL_SECONDS", "2"))
    worker_claim_timeout_seconds = _integer("ODG_WORKER_CLAIM_TIMEOUT_SECONDS", 900)
    worker_schedule_batch_size = _integer("ODG_WORKER_SCHEDULE_BATCH_SIZE", 50)
    graph_max_depth = _integer("ODG_GRAPH_MAX_DEPTH", 5)
    graph_max_export_edges = _integer("ODG_GRAPH_MAX_EXPORT_EDGES", 10_000)
    log_level = os.getenv("ODG_LOG_LEVEL", "INFO").upper()
    log_format = os.getenv("ODG_LOG_FORMAT", "json").lower()
    metrics_enabled = _boolean("ODG_METRICS_ENABLED", True)
    otel_service_name = os.getenv("OTEL_SERVICE_NAME", "opendatagraph")
    otel_exporter_otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")


settings = Settings()
