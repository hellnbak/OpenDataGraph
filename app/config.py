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
    workload_identity_providers_json = os.getenv(
        "ODG_WORKLOAD_IDENTITY_PROVIDERS_JSON",
        "{}",
    )
    workload_identity_max_token_seconds = _integer(
        "ODG_WORKLOAD_IDENTITY_MAX_TOKEN_SECONDS",
        3600,
    )
    workload_exchange_profiles_json = os.getenv(
        "ODG_WORKLOAD_EXCHANGE_PROFILES_JSON",
        "{}",
    )
    workload_exchange_http_timeout_seconds = float(
        os.getenv("ODG_WORKLOAD_EXCHANGE_HTTP_TIMEOUT_SECONDS", "10")
    )
    oidc_discovery_cache_seconds = _integer("ODG_OIDC_DISCOVERY_CACHE_SECONDS", 3600)
    oidc_http_timeout_seconds = float(os.getenv("ODG_OIDC_HTTP_TIMEOUT_SECONDS", "5"))
    scim_bearer_token = os.getenv("ODG_SCIM_BEARER_TOKEN", "")
    scim_tokens_json = os.getenv("ODG_SCIM_TOKENS_JSON", "{}")
    scim_bulk_max_operations = _integer("ODG_SCIM_BULK_MAX_OPERATIONS", 100)
    service_account_credential_days = _integer("ODG_SERVICE_ACCOUNT_CREDENTIAL_DAYS", 90)
    service_account_rotation_grace_hours = _integer(
        "ODG_SERVICE_ACCOUNT_ROTATION_GRACE_HOURS",
        24,
    )
    service_account_stale_days = _integer("ODG_SERVICE_ACCOUNT_STALE_DAYS", 30)
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
    connector_plugin_allowlist = tuple(
        item.strip()
        for item in os.getenv("ODG_CONNECTOR_PLUGIN_ALLOWLIST", "").split(",")
        if item.strip()
    )
    connector_capability_policy_json = os.getenv(
        "ODG_CONNECTOR_CAPABILITY_POLICY_JSON",
        "{}",
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
    graph_async_export_max_edges = _integer("ODG_GRAPH_ASYNC_EXPORT_MAX_EDGES", 250_000)
    graph_export_max_bytes = _integer("ODG_GRAPH_EXPORT_MAX_BYTES", 100 * 1024 * 1024)
    graph_export_backend = os.getenv("ODG_GRAPH_EXPORT_BACKEND", "local").lower()
    graph_export_local_directory = Path(
        os.getenv("ODG_GRAPH_EXPORT_LOCAL_DIRECTORY", "./exports")
    )
    graph_export_bucket = os.getenv("ODG_GRAPH_EXPORT_BUCKET", "")
    graph_export_prefix = os.getenv("ODG_GRAPH_EXPORT_PREFIX", "graph-exports")
    graph_export_endpoint_url = os.getenv("ODG_GRAPH_EXPORT_ENDPOINT_URL", "")
    graph_export_region = os.getenv("ODG_GRAPH_EXPORT_REGION", "")
    graph_export_allowed_sink_buckets = tuple(
        item.strip()
        for item in os.getenv("ODG_GRAPH_EXPORT_ALLOWED_SINK_BUCKETS", "").split(",")
        if item.strip()
    )
    graph_export_https_allowed_hosts = tuple(
        item.strip().lower()
        for item in os.getenv("ODG_GRAPH_EXPORT_HTTPS_ALLOWED_HOSTS", "").split(",")
        if item.strip()
    )
    graph_export_https_identity_token_file = os.getenv(
        "ODG_GRAPH_EXPORT_HTTPS_IDENTITY_TOKEN_FILE",
        "",
    )
    graph_export_https_timeout_seconds = float(
        os.getenv("ODG_GRAPH_EXPORT_HTTPS_TIMEOUT_SECONDS", "30")
    )
    graph_export_s3_exchange_profile = os.getenv(
        "ODG_GRAPH_EXPORT_S3_EXCHANGE_PROFILE",
        "",
    )
    graph_export_gcs_allowed_sink_buckets = tuple(
        item.strip()
        for item in os.getenv("ODG_GRAPH_EXPORT_GCS_ALLOWED_SINK_BUCKETS", "").split(",")
        if item.strip()
    )
    graph_export_gcs_exchange_profile = os.getenv(
        "ODG_GRAPH_EXPORT_GCS_EXCHANGE_PROFILE",
        "",
    )
    graph_export_azure_allowed_sinks = tuple(
        item.strip().lower()
        for item in os.getenv("ODG_GRAPH_EXPORT_AZURE_ALLOWED_SINKS", "").split(",")
        if item.strip()
    )
    graph_export_azure_exchange_profile = os.getenv(
        "ODG_GRAPH_EXPORT_AZURE_EXCHANGE_PROFILE",
        "",
    )
    governance_default_sla_hours = _integer("ODG_GOVERNANCE_DEFAULT_SLA_HOURS", 48)
    governance_due_soon_hours = _integer("ODG_GOVERNANCE_DUE_SOON_HOURS", 24)
    governance_package_backend = os.getenv("ODG_GOVERNANCE_PACKAGE_BACKEND", "local").lower()
    governance_package_local_directory = Path(
        os.getenv("ODG_GOVERNANCE_PACKAGE_LOCAL_DIRECTORY", "./governance-packages")
    )
    governance_package_bucket = os.getenv("ODG_GOVERNANCE_PACKAGE_BUCKET", "")
    governance_package_prefix = os.getenv(
        "ODG_GOVERNANCE_PACKAGE_PREFIX",
        "governance-packages",
    )
    governance_package_endpoint_url = os.getenv(
        "ODG_GOVERNANCE_PACKAGE_ENDPOINT_URL",
        "",
    )
    governance_package_region = os.getenv("ODG_GOVERNANCE_PACKAGE_REGION", "")
    governance_package_max_bytes = _integer(
        "ODG_GOVERNANCE_PACKAGE_MAX_BYTES",
        100 * 1024 * 1024,
    )
    governance_package_signing_profiles_json = os.getenv(
        "ODG_GOVERNANCE_PACKAGE_SIGNING_PROFILES_JSON",
        "{}",
    )
    governance_package_verification_profiles_json = os.getenv(
        "ODG_GOVERNANCE_PACKAGE_VERIFICATION_PROFILES_JSON",
        "{}",
    )
    governance_package_default_signing_profile = os.getenv(
        "ODG_GOVERNANCE_PACKAGE_DEFAULT_SIGNING_PROFILE",
        "",
    )
    governance_package_signing_required = _boolean(
        "ODG_GOVERNANCE_PACKAGE_SIGNING_REQUIRED",
        False,
    )
    cosign_executable = os.getenv("ODG_COSIGN_EXECUTABLE", "cosign")
    cosign_timeout_seconds = float(os.getenv("ODG_COSIGN_TIMEOUT_SECONDS", "60"))
    log_level = os.getenv("ODG_LOG_LEVEL", "INFO").upper()
    log_format = os.getenv("ODG_LOG_FORMAT", "json").lower()
    metrics_enabled = _boolean("ODG_METRICS_ENABLED", True)
    otel_service_name = os.getenv("OTEL_SERVICE_NAME", "opendatagraph")
    otel_exporter_otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")


settings = Settings()
