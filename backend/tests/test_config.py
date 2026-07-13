from pathlib import Path

import pytest

from app.core.config import Settings


def test_default_settings() -> None:
    settings = Settings(_env_file=None)
    assert settings.database_url.startswith("postgresql")
    assert settings.embedding_dimension == 4096
    assert settings.siliconflow_embedding_model == "Qwen/Qwen3-Embedding-8B"
    assert settings.siliconflow_rerank_model == "Qwen/Qwen3-Reranker-8B"
    assert settings.deepseek_model == "deepseek-v4-flash"
    assert settings.siliconflow_timeout_seconds == 30
    assert settings.deepseek_timeout_seconds == 120
    assert settings.classification_timeout_seconds == 180
    assert settings.national_economy_template_path == Path(
        "模板文件/国民经济/国民经济类别模版.docx"
    )


def test_rejects_non_postgres_database() -> None:
    with pytest.raises(ValueError, match="PostgreSQL"):
        Settings(_env_file=None, database_url="sqlite:///./data/dawenzhang.db")
    with pytest.raises(ValueError, match="PostgreSQL"):
        Settings(_env_file=None, database_url="mysql+pymysql://localhost/dawenzhang")


def test_rejects_non_positive_timeout() -> None:
    with pytest.raises(ValueError, match="greater than zero"):
        Settings(_env_file=None, deepseek_timeout_seconds=0)


def test_rejects_non_positive_embedding_dimension() -> None:
    with pytest.raises(ValueError, match="greater than zero"):
        Settings(_env_file=None, embedding_dimension=0)


def test_technology_finance_mapping_path_has_default_and_environment_alias() -> None:
    assert Settings(_env_file=None).technology_finance_mapping_path == Path(
        "五篇大文章映射/科技金融.xlsx"
    )
    assert Settings(
        _env_file=None,
        TECHNOLOGY_FINANCE_MAPPING_PATH="/mnt/catalogs/technology-finance.xlsx",
    ).technology_finance_mapping_path == Path(
        "/mnt/catalogs/technology-finance.xlsx"
    )
