from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables or .env."""

    model_config = SettingsConfigDict(
        env_file=(".env", "backend/.env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        populate_by_name=True,
    )

    app_name: str = Field(default="dawenzhang", validation_alias=AliasChoices("APP_NAME"))
    app_version: str = Field(default="0.1.0", validation_alias=AliasChoices("APP_VERSION"))
    environment: str = Field(default="development", validation_alias=AliasChoices("ENVIRONMENT"))
    api_v1_prefix: str = Field(default="/api/v1", validation_alias=AliasChoices("API_V1_PREFIX"))
    host: str = Field(default="127.0.0.1", validation_alias=AliasChoices("BACKEND_HOST"))
    port: int = Field(default=8000, validation_alias=AliasChoices("BACKEND_PORT"))
    cors_origins: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173",
        validation_alias=AliasChoices("CORS_ORIGINS"),
    )

    database_url: str = Field(
        default="sqlite:///./data/dawenzhang.db",
        validation_alias=AliasChoices("DATABASE_URL"),
    )
    upload_dir: Path = Field(default=Path("./data/uploads"), validation_alias=AliasChoices("UPLOAD_DIR"))
    export_dir: Path = Field(default=Path("./data/exports"), validation_alias=AliasChoices("EXPORT_DIR"))

    ai_base_url: str | None = Field(default=None, validation_alias=AliasChoices("AI_BASE_URL"))
    ai_api_key: str | None = Field(default=None, validation_alias=AliasChoices("AI_API_KEY"))
    ai_connect_timeout_seconds: float = Field(
        default=10.0, validation_alias=AliasChoices("AI_CONNECT_TIMEOUT_SECONDS")
    )
    ai_read_timeout_seconds: float = Field(
        default=90.0, validation_alias=AliasChoices("AI_READ_TIMEOUT_SECONDS")
    )

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        if make_url(value).drivername != "sqlite":
            raise ValueError("DATABASE_URL must use SQLite for the demonstration runtime")
        return value

    @field_validator("ai_connect_timeout_seconds", "ai_read_timeout_seconds")
    @classmethod
    def validate_positive_timeout(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("AI timeouts must be greater than zero")
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def database_path(self) -> Path | None:
        database = make_url(self.database_url).database
        if database is None or database == ":memory:":
            return None
        return Path(database)


@lru_cache
def get_settings() -> Settings:
    return Settings()
