from collections.abc import Iterator, Sequence
from pathlib import Path
from uuid import uuid4

from openpyxl import Workbook
import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.session import get_sessionmaker
from app.models import (
    FiveArticlesMappingRow,
    FiveArticlesMappingVersion,
    NationalEconomyCatalogVersion,
    NationalEconomyIndustryChunk,
)
from app.services.scenario_registry import (
    DIGITAL_FINANCE_REGISTRATION,
    GREEN_FINANCE_REGISTRATION,
    PENSION_FINANCE_REGISTRATION,
    ScenarioRegistration,
)
from app.services.technology_finance_mapping_sync import synchronize_scenario_mapping


SCENARIO_PROFILES = (
    GREEN_FINANCE_REGISTRATION,
    DIGITAL_FINANCE_REGISTRATION,
    PENSION_FINANCE_REGISTRATION,
)
REQUIRED_HEADERS = (
    "主题\nSubject",
    "第一层名称\nTier1_Name",
    "第二层名称\nTier2_Name",
    "第三层名称\nTier3_Name",
    "第四层名称\nTier4_Name",
    "国民经济行业代码\nNEIC_Code",
    "国民经济行业名称\nNEIC_Name",
)


def _mapping_row(
    code: object,
    name: str,
    *,
    subject: str = "场景主题",
    tier1: str = "场景一级标签",
) -> tuple[object, ...]:
    return (subject, tier1, None, None, None, code, name)


def _write_mapping(
    path: Path,
    rows: Sequence[Sequence[object]],
    *,
    category: str | None = None,
) -> None:
    workbook = Workbook()
    worksheet = workbook.active
    if category is None:
        worksheet.append(REQUIRED_HEADERS)
        for row in rows:
            worksheet.append(tuple(row))
    else:
        worksheet.append(("属于类别", *REQUIRED_HEADERS))
        for row in rows:
            worksheet.append((category, *row))
    workbook.save(path)
    workbook.close()


@pytest.fixture()
def scenario_mapping_context() -> Iterator[tuple[Session, str]]:
    session = get_sessionmaker()()
    embedding_model = f"multi-scenario-mapping-{uuid4().hex}"
    catalog_version = NationalEconomyCatalogVersion(
        version=f"catalog-{uuid4().hex}",
        source_hash=uuid4().hex * 2,
        embedding_model=embedding_model,
        embedding_dimension=4096,
    )
    session.add(catalog_version)
    session.flush()
    session.add_all(
        [
            NationalEconomyIndustryChunk(
                catalog_version_id=catalog_version.id,
                major_category_code="C27",
                major_category_name="医药制造业",
                industry_code="2710",
                industry_name="化学药品原料药制造",
                source_row=2,
                text="化学药品原料药制造定义",
                chunk_type="definition",
                embedding=[0.0] * 4096,
            ),
            NationalEconomyIndustryChunk(
                catalog_version_id=catalog_version.id,
                major_category_code="C27",
                major_category_name="医药制造业",
                industry_code="2720",
                industry_name="化学药品制剂制造",
                source_row=3,
                text="化学药品制剂制造定义",
                chunk_type="definition",
                embedding=[0.0] * 4096,
            ),
        ]
    )
    session.flush()
    try:
        yield session, embedding_model
    finally:
        session.rollback()
        session.close()


def _settings_for(
    profile: ScenarioRegistration,
    path: Path,
    embedding_model: str,
) -> Settings:
    assert profile.mapping_path_setting is not None
    return Settings(
        _env_file=None,
        SILICONFLOW_EMBEDDING_MODEL=embedding_model,
        EMBEDDING_DIMENSION=4096,
        **{profile.mapping_path_setting.upper(): path},
    )


@pytest.mark.parametrize("profile", SCENARIO_PROFILES, ids=lambda item: item.id)
def test_scenario_profile_mapping_publishes_valid_two_and_four_digit_rows(
    profile: ScenarioRegistration,
    tmp_path: Path,
    scenario_mapping_context: tuple[Session, str],
) -> None:
    session, embedding_model = scenario_mapping_context
    path = tmp_path / f"{profile.id}.xlsx"
    category = profile.name if profile is GREEN_FINANCE_REGISTRATION else None
    _write_mapping(
        path,
        (
            _mapping_row("27\u3000", " 医药制造业 "),
            _mapping_row(2710.0, "化学药品原料药制造", subject="另一主题"),
        ),
        category=category,
    )

    result = synchronize_scenario_mapping(
        session, profile, _settings_for(profile, path, embedding_model)
    )

    assert result.reused is False
    assert result.version.scenario_id == profile.id
    assert result.version.status == "published"
    assert result.version.validation_report["valid"] is True
    assert result.version.validation_report["published_row_count"] == 2
    rows = session.scalars(
        select(FiveArticlesMappingRow)
        .where(FiveArticlesMappingRow.mapping_version_id == result.version.id)
        .order_by(FiveArticlesMappingRow.source_row)
    ).all()
    assert [(row.neic_code, row.code_level) for row in rows] == [("27", 2), ("2710", 4)]
    assert {row.scenario_id for row in rows} == {profile.id}


@pytest.mark.parametrize("profile", SCENARIO_PROFILES, ids=lambda item: item.id)
def test_scenario_profile_mapping_reuses_the_same_source_hash(
    profile: ScenarioRegistration,
    tmp_path: Path,
    scenario_mapping_context: tuple[Session, str],
) -> None:
    session, embedding_model = scenario_mapping_context
    path = tmp_path / f"{profile.id}-reuse.xlsx"
    _write_mapping(path, (_mapping_row("2710", "化学药品原料药制造"),))
    settings = _settings_for(profile, path, embedding_model)

    first = synchronize_scenario_mapping(session, profile, settings)
    second = synchronize_scenario_mapping(session, profile, settings)

    assert first.reused is False
    assert second.reused is True
    assert second.version.id == first.version.id
    assert session.scalar(
        select(func.count(FiveArticlesMappingVersion.id)).where(
            FiveArticlesMappingVersion.scenario_id == profile.id,
            FiveArticlesMappingVersion.source_hash == first.version.source_hash,
        )
    ) == 1


@pytest.mark.parametrize("profile", SCENARIO_PROFILES, ids=lambda item: item.id)
def test_scenario_profile_mapping_rejects_a_nonexistent_code(
    profile: ScenarioRegistration,
    tmp_path: Path,
    scenario_mapping_context: tuple[Session, str],
) -> None:
    session, embedding_model = scenario_mapping_context
    path = tmp_path / f"{profile.id}-missing-code.xlsx"
    _write_mapping(path, (_mapping_row("9999", "不存在行业"),))

    result = synchronize_scenario_mapping(
        session, profile, _settings_for(profile, path, embedding_model)
    )

    assert result.version.status == "invalid"
    assert result.version.validation_report["errors"][0]["type"] == "code_not_found"
    assert result.version.validation_report["published_row_count"] == 0


@pytest.mark.parametrize("profile", SCENARIO_PROFILES, ids=lambda item: item.id)
def test_scenario_profile_mapping_rejects_a_name_code_conflict(
    profile: ScenarioRegistration,
    tmp_path: Path,
    scenario_mapping_context: tuple[Session, str],
) -> None:
    session, embedding_model = scenario_mapping_context
    path = tmp_path / f"{profile.id}-name-conflict.xlsx"
    _write_mapping(path, (_mapping_row("2710", "化学药品制剂制造"),))

    result = synchronize_scenario_mapping(
        session, profile, _settings_for(profile, path, embedding_model)
    )

    error = result.version.validation_report["errors"][0]
    assert result.version.status == "invalid"
    assert error["type"] == "name_code_conflict"
    assert error["name_matching_codes"] == ["2720"]


@pytest.mark.parametrize("profile", SCENARIO_PROFILES, ids=lambda item: item.id)
def test_scenario_profile_mapping_rejects_exact_duplicates(
    profile: ScenarioRegistration,
    tmp_path: Path,
    scenario_mapping_context: tuple[Session, str],
) -> None:
    session, embedding_model = scenario_mapping_context
    path = tmp_path / f"{profile.id}-duplicate.xlsx"
    _write_mapping(
        path,
        (
            _mapping_row("2710", "化学药品原料药制造"),
            _mapping_row("2710.0", "化学药品原料药制造"),
        ),
    )

    result = synchronize_scenario_mapping(
        session, profile, _settings_for(profile, path, embedding_model)
    )

    errors = result.version.validation_report["errors"]
    assert result.version.status == "invalid"
    assert next(error for error in errors if error["type"] == "exact_duplicate") == {
        "type": "exact_duplicate",
        "source_row": 3,
        "duplicate_of_source_row": 2,
        "neic_code": "2710",
        "neic_name": "化学药品原料药制造",
        "taxonomy": ["场景主题", "场景一级标签", None, None, None],
    }


@pytest.mark.parametrize("profile", SCENARIO_PROFILES, ids=lambda item: item.id)
def test_scenario_profile_mapping_rejects_a_mismatched_nonempty_category(
    profile: ScenarioRegistration,
    tmp_path: Path,
    scenario_mapping_context: tuple[Session, str],
) -> None:
    session, embedding_model = scenario_mapping_context
    path = tmp_path / f"{profile.id}-category-mismatch.xlsx"
    _write_mapping(
        path,
        (_mapping_row("2710", "化学药品原料药制造"),),
        category="其他金融",
    )

    result = synchronize_scenario_mapping(
        session, profile, _settings_for(profile, path, embedding_model)
    )

    assert result.version.status == "invalid"
    assert result.version.validation_report["published_row_count"] == 0
    assert result.version.validation_report["errors"] == [
        {
            "type": "category_mismatch",
            "source_row": 2,
            "expected": profile.name,
            "actual": "其他金融",
        }
    ]
    assert session.scalar(
        select(func.count(FiveArticlesMappingRow.id)).where(
            FiveArticlesMappingRow.mapping_version_id == result.version.id
        )
    ) == 0
