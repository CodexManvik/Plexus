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

    # Azure OpenAI — required for LLM extraction and RAG
    azure_openai_api_key: str = Field(..., validation_alias="AZURE_OPENAI_API_KEY")
    azure_openai_endpoint: str = Field(..., validation_alias="AZURE_OPENAI_ENDPOINT")
    azure_openai_deployment_name: str = Field(
        default="gpt-4o", validation_alias="AZURE_OPENAI_DEPLOYMENT_NAME"
    )
    azure_openai_api_version: str = Field(
        default="2024-02-15-preview", validation_alias="AZURE_OPENAI_API_VERSION"
    )

    sentence_transformer_model: str = Field(
        default="all-MiniLM-L6-v2", validation_alias="SENTENCE_TRANSFORMER_MODEL"
    )
    lock_lease_minutes: int = Field(default=15, validation_alias="LOCK_LEASE_MINUTES")
    dashboard_horizon_days: int = Field(default=30, validation_alias="DASHBOARD_HORIZON_DAYS")

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, value):
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            parts = [part.strip() for part in value.split(",") if part.strip()]
            return parts or ["*"]
        return ["*"]

    def resolved_database_url(self) -> str:
        return (
            "oracle+oracledb_async://"
            f"{self.oracle_db_user}:{self.oracle_db_password}"
            f"@/?dsn={self.oracle_db_dsn}"
        )


settings = Settings(
    cors_origins=os.getenv("CORS_ORIGINS", "*"),
)