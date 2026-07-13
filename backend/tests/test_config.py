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


@pytest.mark.parametrize(
    ("field_name", "environment_name", "default_path"),
    (
        (
            "green_finance_template_path",
            "GREEN_FINANCE_TEMPLATE_PATH",
            "模板文件/五篇大文章/绿色金融模版.docx",
        ),
        (
            "green_finance_mapping_path",
            "GREEN_FINANCE_MAPPING_PATH",
            "五篇大文章映射/绿色金融.xlsx",
        ),
        (
            "digital_finance_template_path",
            "DIGITAL_FINANCE_TEMPLATE_PATH",
            "模板文件/五篇大文章/数字金融模版.docx",
        ),
        (
            "digital_finance_mapping_path",
            "DIGITAL_FINANCE_MAPPING_PATH",
            "五篇大文章映射/数字金融.xlsx",
        ),
        (
            "pension_finance_template_path",
            "PENSION_FINANCE_TEMPLATE_PATH",
            "模板文件/五篇大文章/养老金融模版.docx",
        ),
        (
            "pension_finance_mapping_path",
            "PENSION_FINANCE_MAPPING_PATH",
            "五篇大文章映射/养老金融.xlsx",
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
