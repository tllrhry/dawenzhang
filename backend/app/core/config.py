from functools import lru_cache

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


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

    mysql_host: str = Field(default="127.0.0.1", validation_alias=AliasChoices("MYSQL_HOST"))
    mysql_port: int = Field(default=3306, validation_alias=AliasChoices("MYSQL_PORT"))
    mysql_database: str = Field(default="dawenzhang", validation_alias=AliasChoices("MYSQL_DATABASE"))
    mysql_user: str = Field(default="dawenzhang_app", validation_alias=AliasChoices("MYSQL_USER"))
    mysql_password: str = Field(default="", validation_alias=AliasChoices("MYSQL_PASSWORD"))
    mysql_pool_pre_ping: bool = Field(default=True, validation_alias=AliasChoices("MYSQL_POOL_PRE_PING"))

    redis_host: str = Field(default="127.0.0.1", validation_alias=AliasChoices("REDIS_HOST"))
    redis_port: int = Field(default=6379, validation_alias=AliasChoices("REDIS_PORT"))
    redis_db: int = Field(default=1, validation_alias=AliasChoices("REDIS_DB"))
    redis_password: str | None = Field(default=None, validation_alias=AliasChoices("REDIS_PASSWORD"))
    redis_key_prefix: str = Field(default="dawenzhang:", validation_alias=AliasChoices("REDIS_KEY_PREFIX"))

    ai_base_url: str | None = Field(default=None, validation_alias=AliasChoices("AI_BASE_URL"))
    ai_api_key: str | None = Field(default=None, validation_alias=AliasChoices("AI_API_KEY"))

    @field_validator("mysql_database")
    @classmethod
    def validate_mysql_database(cls, value: str) -> str:
        if value != "dawenzhang":
            raise ValueError("MYSQL_DATABASE must be 'dawenzhang'; refusing to connect to another database")
        return value

    @field_validator("redis_db")
    @classmethod
    def validate_redis_db(cls, value: int) -> int:
        if value != 1:
            raise ValueError("REDIS_DB must be 1; db0 is reserved for the existing ai_tag_fix project")
        return value

    @field_validator("redis_key_prefix")
    @classmethod
    def validate_redis_key_prefix(cls, value: str) -> str:
        if not value.startswith("dawenzhang:") or not value.endswith(":"):
            raise ValueError("REDIS_KEY_PREFIX must use the dawenzhang: namespace")
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def sqlalchemy_database_url(self) -> str:
        from sqlalchemy.engine import URL

        return URL.create(
            "mysql+pymysql",
            username=self.mysql_user,
            password=self.mysql_password,
            host=self.mysql_host,
            port=self.mysql_port,
            database=self.mysql_database,
        ).render_as_string(hide_password=False)


@lru_cache
def get_settings() -> Settings:
    return Settings()
