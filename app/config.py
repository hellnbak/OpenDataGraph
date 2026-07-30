from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "OpenDataGraph"
    database_url: str = "sqlite:///./opendatagraph.db"
    ollama_url: str = "http://host.docker.internal:11434"
    ollama_model: str = "qwen2.5:3b"
    classification_mode: str = "hybrid"
    auto_seed_demo: bool = True

    model_config = SettingsConfigDict(env_file=".env", env_prefix="ODG_", extra="ignore")


settings = Settings()
