import os


def _boolean(name: str, default: bool) -> bool:
    value = os.getenv(name)
    return default if value is None else value.lower() in {"1", "true", "yes", "on"}


class Settings:
    app_name = os.getenv("ODG_APP_NAME", "OpenDataGraph")
    database_url = os.getenv("ODG_DATABASE_URL", "sqlite:///./opendatagraph.db")
    ollama_url = os.getenv("ODG_OLLAMA_URL", "http://host.docker.internal:11434")
    ollama_model = os.getenv("ODG_OLLAMA_MODEL", "qwen2.5:3b")
    classification_mode = os.getenv("ODG_CLASSIFICATION_MODE", "hybrid")
    classification_review_threshold = float(os.getenv("ODG_CLASSIFICATION_REVIEW_THRESHOLD", "0.70"))
    auto_seed_demo = _boolean("ODG_AUTO_SEED_DEMO", True)
    auth_disabled = _boolean("ODG_AUTH_DISABLED", True)
    api_keys_json = os.getenv("ODG_API_KEYS_JSON", "{}")
    oidc_issuer = os.getenv("ODG_OIDC_ISSUER", "")
    oidc_audience = os.getenv("ODG_OIDC_AUDIENCE", "")
    policy_directory = os.getenv("ODG_POLICY_DIRECTORY", "policies")


settings = Settings()
