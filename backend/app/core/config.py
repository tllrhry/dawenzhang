from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

# PostgreSQL is the only supported runtime database. pgvector stores the
# national-economy retrieval fragments, so a SQLite fallback is not offered.
_ALLOWED_DB_BACKENDS = {"postgresql", "postgres"}


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

    # PostgreSQL + pgvector. Use the psycopg (v3) driver.
    database_url: str = Field(
        default="postgresql+psycopg://dawenzhang:dawenzhang@127.0.0.1:5432/dawenzhang",
        validation_alias=AliasChoices("DATABASE_URL"),
    )
    db_pool_size: int = Field(default=5, validation_alias=AliasChoices("DB_POOL_SIZE"))
    db_max_overflow: int = Field(default=5, validation_alias=AliasChoices("DB_MAX_OVERFLOW"))
    db_pool_timeout_seconds: float = Field(
        default=30.0, validation_alias=AliasChoices("DB_POOL_TIMEOUT_SECONDS")
    )

    upload_dir: Path = Field(default=Path("./data/uploads"), validation_alias=AliasChoices("UPLOAD_DIR"))
    export_dir: Path = Field(default=Path("./data/exports"), validation_alias=AliasChoices("EXPORT_DIR"))

    # Raw GB/T 4754-2017 catalog Excel. The file is the single source of truth
    # for catalog synchronization and is mounted, never committed.
    national_economy_catalog_path: Path | None = Field(
        default=None, validation_alias=AliasChoices("NATIONAL_ECONOMY_CATALOG_PATH")
    )
    national_economy_template_path: Path = Field(
        default=Path("模板文件/国民经济/国民经济类别模版.docx"),
        validation_alias=AliasChoices("NATIONAL_ECONOMY_TEMPLATE_PATH"),
    )
    technology_finance_template_path: Path = Field(
        default=Path("模板文件/五篇大文章/科技金融模版 .docx"),
        validation_alias=AliasChoices("TECHNOLOGY_FINANCE_TEMPLATE_PATH"),
    )
    technology_finance_mapping_path: Path = Field(
        default=Path("五篇大文章映射/科技金融.xlsx"),
        validation_alias=AliasChoices("TECHNOLOGY_FINANCE_MAPPING_PATH"),
    )
    green_finance_template_path: Path = Field(
        default=Path("模板文件/五篇大文章/绿色金融模版.docx"),
        validation_alias=AliasChoices("GREEN_FINANCE_TEMPLATE_PATH"),
    )
    green_finance_mapping_path: Path = Field(
        default=Path("五篇大文章映射/绿色金融.xlsx"),
        validation_alias=AliasChoices("GREEN_FINANCE_MAPPING_PATH"),
    )
    digital_finance_template_path: Path = Field(
        default=Path("模板文件/五篇大文章/数字金融模版.docx"),
        validation_alias=AliasChoices("DIGITAL_FINANCE_TEMPLATE_PATH"),
    )
    digital_finance_mapping_path: Path = Field(
        default=Path("五篇大文章映射/数字金融.xlsx"),
        validation_alias=AliasChoices("DIGITAL_FINANCE_MAPPING_PATH"),
    )
    pension_finance_template_path: Path = Field(
        default=Path("模板文件/五篇大文章/养老金融模版.docx"),
        validation_alias=AliasChoices("PENSION_FINANCE_TEMPLATE_PATH"),
    )
    pension_finance_mapping_path: Path = Field(
        default=Path("五篇大文章映射/养老金融.xlsx"),
        validation_alias=AliasChoices("PENSION_FINANCE_MAPPING_PATH"),
    )

    # Shared HTTP connect timeout for the cloud model clients.
    http_connect_timeout_seconds: float = Field(
        default=10.0, validation_alias=AliasChoices("HTTP_CONNECT_TIMEOUT_SECONDS")
    )

    # SiliconFlow: embedding + rerank.
    siliconflow_base_url: str = Field(
        default="https://api.siliconflow.cn/v1",
        validation_alias=AliasChoices("SILICONFLOW_BASE_URL"),
    )
    siliconflow_api_key: str | None = Field(
        default=None, validation_alias=AliasChoices("SILICONFLOW_API_KEY")
    )
    siliconflow_embedding_model: str = Field(
        default="Qwen/Qwen3-Embedding-8B",
        validation_alias=AliasChoices("SILICONFLOW_EMBEDDING_MODEL"),
    )
    siliconflow_rerank_model: str = Field(
        default="Qwen/Qwen3-Reranker-8B",
        validation_alias=AliasChoices("SILICONFLOW_RERANK_MODEL"),
    )
    embedding_dimension: int = Field(
        default=4096, validation_alias=AliasChoices("EMBEDDING_DIMENSION")
    )
    siliconflow_timeout_seconds: float = Field(
        default=30.0, validation_alias=AliasChoices("SILICONFLOW_TIMEOUT_SECONDS")
    )
    siliconflow_embedding_batch_size: int = Field(
        default=32, validation_alias=AliasChoices("SILICONFLOW_EMBEDDING_BATCH_SIZE")
    )

    # DeepSeek: constrained single-result classification.
    deepseek_base_url: str = Field(
        default="https://api.deepseek.com/v1",
        validation_alias=AliasChoices("DEEPSEEK_BASE_URL"),
    )
    deepseek_api_key: str | None = Field(
        default=None, validation_alias=AliasChoices("DEEPSEEK_API_KEY")
    )
    deepseek_model: str = Field(
        default="deepseek-v4-flash", validation_alias=AliasChoices("DEEPSEEK_MODEL")
    )
    deepseek_timeout_seconds: float = Field(
        default=120.0, validation_alias=AliasChoices("DEEPSEEK_TIMEOUT_SECONDS")
    )

    # End-to-end synchronous classification budget (nginx/uvicorn must stay >= this).
    classification_timeout_seconds: float = Field(
        default=180.0, validation_alias=AliasChoices("CLASSIFICATION_TIMEOUT_SECONDS")
    )

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        backend = make_url(value).get_backend_name()
        if backend not in _ALLOWED_DB_BACKENDS:
            raise ValueError("DATABASE_URL must use PostgreSQL (pgvector) for this application")
        return value

    @field_validator(
        "http_connect_timeout_seconds",
        "siliconflow_timeout_seconds",
        "deepseek_timeout_seconds",
        "classification_timeout_seconds",
        "db_pool_timeout_seconds",
    )
    @classmethod
    def validate_positive_timeout(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("timeouts must be greater than zero")
        return value

    @field_validator("embedding_dimension")
    @classmethod
    def validate_embedding_dimension(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("EMBEDDING_DIMENSION must be greater than zero")
        return value

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
