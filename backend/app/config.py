import os
from pathlib import Path
from typing import List, Literal

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

    database_backend: Literal["auto", "oracle26ai", "sqlite"] = Field(
        default="auto", validation_alias="DATABASE_BACKEND"
    )
    database_url: str | None = Field(default=None, validation_alias="DATABASE_URL")
    oracle_db_user: str | None = Field(default=None, validation_alias="ORACLE_DB_USER")
    oracle_db_password: str | None = Field(
        default=None, validation_alias="ORACLE_DB_PASSWORD"
    )
    oracle_db_dsn: str | None = Field(default=None, validation_alias="ORACLE_DB_DSN")
    oracle_thick_mode: bool = Field(default=False, validation_alias="ORACLE_THICK_MODE")
    oracle_client_lib_dir: str | None = Field(
        default=None, validation_alias="ORACLE_CLIENT_LIB_DIR"
    )
    sqlite_fallback_url: str = Field(
        default="sqlite+aiosqlite:///./app/fallback_development.db",
        validation_alias="SQLITE_FALLBACK_URL",
    )

    azure_openai_api_key: str = Field(default="", validation_alias="AZURE_OPENAI_API_KEY")
    azure_openai_endpoint: str = Field(
        default="", validation_alias="AZURE_OPENAI_ENDPOINT"
    )
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
        if self.database_backend == "sqlite":
            return self.resolved_sqlite_url()

        if self.database_url:
            return self.database_url

        if self.database_backend == "oracle26ai" or (
            self.oracle_db_user and self.oracle_db_password and self.oracle_db_dsn
        ):
            missing = [
                name
                for name, value in {
                    "ORACLE_DB_USER": self.oracle_db_user,
                    "ORACLE_DB_PASSWORD": self.oracle_db_password,
                    "ORACLE_DB_DSN": self.oracle_db_dsn,
                }.items()
                if not value
            ]
            if missing:
                raise ValueError(
                    "Oracle 26ai backend requires: " + ", ".join(missing)
                )
            return (
                "oracle+oracledb_async://"
                f"{self.oracle_db_user}:{self.oracle_db_password}@/?dsn={self.oracle_db_dsn}"
            )

        return self.resolved_sqlite_url()

    def resolved_sqlite_url(self) -> str:
        prefix = "sqlite+aiosqlite:///"
        if not self.sqlite_fallback_url.startswith(prefix):
            return self.sqlite_fallback_url

        path_part = self.sqlite_fallback_url.removeprefix(prefix)
        is_windows_absolute = len(path_part) > 1 and path_part[1] == ":"
        is_posix_absolute = path_part.startswith("/")
        if is_windows_absolute or is_posix_absolute:
            return self.sqlite_fallback_url

        relative_path = path_part[2:] if path_part.startswith("./") else path_part
        absolute_path = (self.backend_root / relative_path).resolve()
        return f"{prefix}{absolute_path.as_posix()}"


settings = Settings(
    cors_origins=os.getenv("CORS_ORIGINS", "*"),
)
