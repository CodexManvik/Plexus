from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://postgres:postgres@localhost:5432/plexus"
    llama_base_url: str = "http://localhost:8080/v1"
    llama_model: str = "models/Llama-3.2-3B-Instruct-Q4_K_M"
    llama_api_key: str = "local-execution"
    embedding_model_path: str = "models/bge-large-en-v1.5-q4_k_m"
    embedding_device: str = "cpu"
    embedding_batch_size: int = 16
    init_db: bool = False

    model_config = SettingsConfigDict(env_prefix="PLEXUS_", case_sensitive=False)


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
