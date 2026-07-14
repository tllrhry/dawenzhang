from pathlib import Path

import pytest
from sqlalchemy.engine import make_url

from app.core.config import Settings, get_settings


def test_pytest_uses_isolated_database() -> None:
    database_name = make_url(get_settings().database_url).database

    assert database_name is not None
    assert database_name.startswith("dawenzhang_test_")


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


def test_five_articles_mapping_source_path_has_default_and_environment_alias() -> None:
    assert Settings(_env_file=None).five_articles_mapping_source_path == Path(
        "五篇大文章映射/贷款投向-五篇大文章映射表.xlsx"
    )
    assert Settings(
        _env_file=None,
        FIVE_ARTICLES_MAPPING_SOURCE_PATH="/mnt/catalogs/five-articles.xlsx",
    ).five_articles_mapping_source_path == Path(
        "/mnt/catalogs/five-articles.xlsx"
    )


@pytest.mark.parametrize(
    ("field_name", "environment_name", "default_path"),
    (
        (
            "green_finance_template_path",
            "GREEN_FINANCE_TEMPLATE_PATH",
            "模板文件/五篇大文章/绿色金融模版.docx",
        ),
        (
            "digital_finance_template_path",
            "DIGITAL_FINANCE_TEMPLATE_PATH",
            "模板文件/五篇大文章/数字金融模版.docx",
        ),
        (
            "pension_finance_template_path",
            "PENSION_FINANCE_TEMPLATE_PATH",
            "模板文件/五篇大文章/养老金融模版.docx",
        ),
        (
            "inclusive_finance_template_path",
            "INCLUSIVE_FINANCE_TEMPLATE_PATH",
            "模板文件/五篇大文章/普惠金融模版.docx",
        ),
    ),
)
def test_new_finance_asset_paths_have_defaults_and_environment_aliases(
    field_name: str,
    environment_name: str,
    default_path: str,
) -> None:
    assert getattr(Settings(_env_file=None), field_name) == Path(default_path)

    configured_path = f"/mnt/assets/{field_name}"
    settings = Settings(_env_file=None, **{environment_name: configured_path})

    assert getattr(settings, field_name) == Path(configured_path)
