import os
from pathlib import Path
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    backend_root: Path = Path(__file__).resolve().parents[1]

    model_config = SettingsConfigDict(
        env_file=str(backend_root / ".env"),
        extra="ignore",
    )

    app_env: str = Field(default="development", validation_alias="APP_ENV")
    app_name: str = Field(
        default="ContractLens CLM Backend API", validation_alias="APP_NAME"
    )
    app_version: str = Field(default="1.0.0", validation_alias="APP_VERSION")
    app_secret_key: str = Field(default="local-dev-key", validation_alias="APP_SECRET_KEY")
    api_prefix: str = Field(default="/api", validation_alias="API_PREFIX")

    cors_origins_raw: str = Field(default="*", validation_alias="CORS_ORIGINS")
    cors_origins: List[str] = Field(default_factory=lambda: ["*"])

    # Oracle 23ai — required, no fallback
    oracle_db_user: str = Field(..., validation_alias="ORACLE_DB_USER")
    oracle_db_password: str = Field(..., validation_alias="ORACLE_DB_PASSWORD")
    oracle_db_dsn: str = Field(..., validation_alias="ORACLE_DB_DSN")
    oracle_thick_mode: bool = Field(default=False, validation_alias="ORACLE_THICK_MODE")
    oracle_client_lib_dir: str | None = Field(
        default=None, validation_alias="ORACLE_CLIENT_LIB_DIR"
    )

    embedding_vector_dim: int = Field(default=384, validation_alias="EMBEDDING_VECTOR_DIM")

    # LLM provider selection and credentials
    llm_provider: str = Field(default="auto", validation_alias="LLM_PROVIDER")
    azure_openai_api_key: str | None = Field(default=None, validation_alias="AZURE_OPENAI_API_KEY")
    azure_openai_endpoint: str | None = Field(default=None, validation_alias="AZURE_OPENAI_ENDPOINT")
    azure_openai_deployment_name: str = Field(
        default="gpt-4o", validation_alias="AZURE_OPENAI_DEPLOYMENT_NAME"
    )
    azure_openai_api_version: str = Field(
        default="2024-02-15-preview", validation_alias="AZURE_OPENAI_API_VERSION"
    )
    google_ai_studio_api_key: str | None = Field(
        default=None, validation_alias="GOOGLE_AI_STUDIO_API_KEY"
    )
    google_ai_studio_model: str = Field(
        default="gemini-1.5-flash", validation_alias="GOOGLE_AI_STUDIO_MODEL"
    )

    sentence_transformer_model: str = Field(
        default="all-MiniLM-L6-v2", validation_alias="SENTENCE_TRANSFORMER_MODEL"
    )

    # Add inside class Settings(BaseSettings) in backend/app/config.py:
    
    # Cohere Credentials
    cohere_api_key: str | None = Field(default=None, validation_alias="COHERE_API_KEY")
    cohere_model: str = Field(
        default="command-r-plus", validation_alias="COHERE_MODEL"
    )
    lock_lease_minutes: int = Field(default=15, validation_alias="LOCK_LEASE_MINUTES")
    dashboard_horizon_days: int = Field(default=30, validation_alias="DASHBOARD_HORIZON_DAYS")

    # Parsing engine — set USE_MARKER_PARSER=true only when marker-pdf is manually
    # installed and GPU/CPU resources allow. Default is CPU-only PyMuPDF.
    use_marker_parser: bool = Field(default=False, validation_alias="USE_MARKER_PARSER")

    # LangGraph critic circuit-breaker: maximum re-tries before flagging MANUAL_REVIEW.
    extraction_max_critic_retries: int = Field(default=2, validation_alias="EXTRACTION_MAX_CRITIC_RETRIES")
    

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value):
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            parts = [part.strip() for part in value.split(",") if part.strip()]
            return parts or ["*"]
        return ["*"]

    @field_validator("llm_provider", mode="before")
    @classmethod
    def normalize_llm_provider(cls, value):
        if isinstance(value, str):
            normalized = value.strip().lower()
            return normalized or "auto"
        return "auto"

    def resolve_embedding_model_path(self) -> Path | None:
        raw_model_ref = (self.sentence_transformer_model or "").strip()
        if not raw_model_ref:
            return None

        raw_path = Path(raw_model_ref).expanduser()
        candidates = [raw_path]
        if raw_path.suffix.lower() != ".gguf":
            candidates.append(raw_path.with_suffix(".gguf"))

        if not raw_path.is_absolute():
            for root in (self.backend_root, self.backend_root.parent):
                rooted = (root / raw_path).expanduser()
                candidates.append(rooted)
                if raw_path.suffix.lower() != ".gguf":
                    candidates.append(rooted.with_suffix(".gguf"))

        seen: set[str] = set()
        for candidate in candidates:
            candidate_key = str(candidate)
            if candidate_key in seen:
                continue
            seen.add(candidate_key)
            try:
                if candidate.exists():
                    return candidate
            except OSError:
                continue

        return None

    def resolved_embedding_backend(self) -> str:
        model_path = self.resolve_embedding_model_path()
        raw_model_ref = (self.sentence_transformer_model or "").strip().lower()
        if model_path and model_path.suffix.lower() == ".gguf":
            return "llama_cpp"
        if raw_model_ref.endswith(".gguf"):
            return "llama_cpp"
        return "sentence_transformers"

    def resolved_database_url(self) -> str:
        return (
            "oracle+oracledb_async://"
            f"{self.oracle_db_user}:{self.oracle_db_password}"
            f"@/?dsn={self.oracle_db_dsn}"
        )


settings = Settings(
    cors_origins=os.getenv("CORS_ORIGINS", "*"),
)