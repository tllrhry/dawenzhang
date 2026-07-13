from collections.abc import Iterator, Sequence
from pathlib import Path
from uuid import uuid4

from openpyxl import Workbook
import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.session import get_sessionmaker
from app.models import (
    FiveArticlesMappingRow,
    FiveArticlesMappingVersion,
    NationalEconomyCatalogVersion,
    NationalEconomyIndustryChunk,
)
from app.services.technology_finance_mapping_sync import (
    MappingHeaderError,
    read_mapping_source,
    synchronize_technology_finance_mapping,
)


BILINGUAL_HEADERS = (
    "属于类别",
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
    subject: str = "高技术产业（制造业）",
    tier1: str = "医药制造业",
    tier2: str | None = "化学药品制造",
    tier3: str | None = None,
    tier4: str | None = None,
) -> tuple[object, ...]:
    return (
        "科技金融",
        subject,
        tier1,
        tier2,
        tier3,
        tier4,
        code,
        name,
    )


def _write_mapping(
    path: Path,
    rows: Sequence[Sequence[object]],
    headers: Sequence[str] = BILINGUAL_HEADERS,
) -> None:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.append(tuple(headers))
    for row in rows:
        worksheet.append(tuple(row))
    workbook.save(path)
    workbook.close()


@pytest.fixture()
def mapping_sync_context() -> Iterator[tuple[Session, Settings, str, int]]:
    session = get_sessionmaker()()
    scenario_id = f"technology_finance_test_{uuid4().hex}"
    embedding_model = f"mapping-sync-test-{uuid4().hex}"
    settings = Settings(
        _env_file=None,
        SILICONFLOW_EMBEDDING_MODEL=embedding_model,
        EMBEDDING_DIMENSION=4096,
    )
    catalog_version = NationalEconomyCatalogVersion(
        version=f"catalog-{uuid4().hex}",
        source_hash=uuid4().hex * 2,
        embedding_model=embedding_model,
        embedding_dimension=4096,
    )
    session.add(catalog_version)
    session.flush()
    catalog_version_id = catalog_version.id
    zero_embedding = [0.0] * 4096
    session.add_all(
        [
            NationalEconomyIndustryChunk(
                catalog_version_id=catalog_version_id,
                major_category_code="C27",
                major_category_name="医药制造业",
                industry_code="2710",
                industry_name="化学药品原料药制造",
                source_row=2,
                text="化学药品原料药制造定义",
                chunk_type="definition",
                embedding=zero_embedding,
            ),
            NationalEconomyIndustryChunk(
                catalog_version_id=catalog_version_id,
                major_category_code="C27",
                major_category_name="医药制造业",
                industry_code="2710",
                industry_name="化学药品原料药制造",
                source_row=2,
                text="包括化学药品原料药制造",
                chunk_type="include",
                embedding=zero_embedding,
            ),
            NationalEconomyIndustryChunk(
                catalog_version_id=catalog_version_id,
                major_category_code="C27",
                major_category_name="医药制造业",
                industry_code="2720",
                industry_name="化学药品制剂制造",
                source_row=3,
                text="化学药品制剂制造定义",
                chunk_type="definition",
                embedding=zero_embedding,
            ),
            NationalEconomyIndustryChunk(
                catalog_version_id=catalog_version_id,
                major_category_code="C30",
                major_category_name="专用设备制造业",
                industry_code="3011",
                industry_name="工业设备制造",
                source_row=4,
                text="工业设备制造定义",
                chunk_type="definition",
                embedding=zero_embedding,
            ),
        ]
    )
    session.commit()

    try:
        yield session, settings, scenario_id, catalog_version_id
    finally:
        session.rollback()
        session.execute(
            delete(FiveArticlesMappingVersion).where(
                FiveArticlesMappingVersion.scenario_id == scenario_id
            )
        )
        session.execute(
            delete(NationalEconomyCatalogVersion).where(
                NationalEconomyCatalogVersion.id == catalog_version_id
            )
        )
        session.commit()
        session.close()


def test_valid_mapping_uses_headers_normalizes_values_and_publishes_all_rows(
    tmp_path: Path,
    mapping_sync_context: tuple[Session, Settings, str, int],
) -> None:
    session, settings, scenario_id, catalog_version_id = mapping_sync_context
    path = tmp_path / "technology-finance.xlsx"
    _write_mapping(
        path,
        (
            _mapping_row("27\u3000", " 医药制造业 ", tier2="", tier3=None),
            _mapping_row(2710.0, "化学药品原料药制造"),
            _mapping_row(
                "2710",
                "化学药品原料药制造",
                subject="国家科技重大项目",
                tier1="重大新药创制",
            ),
        ),
    )

    source = read_mapping_source(path)
    result = synchronize_technology_finance_mapping(
        session, source, settings, scenario_id=scenario_id
    )
    session.commit()

    assert source.headers == (
        "属于类别",
        "主题",
        "第一层名称",
        "第二层名称",
        "第三层名称",
        "第四层名称",
        "国民经济行业代码",
        "国民经济行业名称",
    )
    assert result.reused is False
    assert result.version.status == "published"
    assert result.version.validation_report["valid"] is True
    assert result.version.validation_report["catalog_version_id"] == catalog_version_id
    assert result.version.validation_report["published_row_count"] == 3
    rows = session.scalars(
        select(FiveArticlesMappingRow)
        .where(FiveArticlesMappingRow.mapping_version_id == result.version.id)
        .order_by(FiveArticlesMappingRow.source_row)
    ).all()
    assert [(row.neic_code, row.code_level) for row in rows] == [
        ("27", 2),
        ("2710", 4),
        ("2710", 4),
    ]
    assert rows[0].tier2 is None
    assert rows[0].tier3 is None
    assert rows[0].neic_name == "医药制造业"
    assert [row.subject for row in rows[1:]] == [
        "高技术产业(制造业)",
        "国家科技重大项目",
    ]
    assert {item["field"] for item in result.version.validation_report["normalizations"]} >= {
        "NEIC_Code",
        "NEIC_Name",
    }


def test_four_digit_name_code_conflict_creates_invalid_version(
    tmp_path: Path,
    mapping_sync_context: tuple[Session, Settings, str, int],
) -> None:
    session, settings, scenario_id, _ = mapping_sync_context
    path = tmp_path / "four-digit-conflict.xlsx"
    _write_mapping(path, (_mapping_row("2710", "化学药品制剂制造"),))

    result = synchronize_technology_finance_mapping(
        session, read_mapping_source(path), settings, scenario_id=scenario_id
    )
    session.commit()

    assert result.version.status == "invalid"
    assert result.version.validation_report["errors"] == [
        {
            "type": "name_code_conflict",
            "source_row": 2,
            "code_level": 4,
            "neic_code": "2710",
            "neic_name": "化学药品制剂制造",
            "expected_names": ["化学药品原料药制造"],
            "name_matching_codes": ["2720"],
        }
    ]


def test_two_digit_major_category_name_conflict_creates_invalid_version(
    tmp_path: Path,
    mapping_sync_context: tuple[Session, Settings, str, int],
) -> None:
    session, settings, scenario_id, _ = mapping_sync_context
    path = tmp_path / "two-digit-conflict.xlsx"
    _write_mapping(path, (_mapping_row("27", "专用设备制造业", tier2=None),))

    result = synchronize_technology_finance_mapping(
        session, read_mapping_source(path), settings, scenario_id=scenario_id
    )
    session.commit()

    error = result.version.validation_report["errors"][0]
    assert result.version.status == "invalid"
    assert error["type"] == "name_code_conflict"
    assert error["code_level"] == 2
    assert error["expected_names"] == ["医药制造业"]
    assert error["name_matching_codes"] == ["30"]


def test_nonexistent_code_creates_invalid_version(
    tmp_path: Path,
    mapping_sync_context: tuple[Session, Settings, str, int],
) -> None:
    session, settings, scenario_id, _ = mapping_sync_context
    path = tmp_path / "missing-code.xlsx"
    _write_mapping(path, (_mapping_row("9999", "不存在行业"),))

    result = synchronize_technology_finance_mapping(
        session, read_mapping_source(path), settings, scenario_id=scenario_id
    )
    session.commit()

    assert result.version.status == "invalid"
    assert result.version.validation_report["errors"][0]["type"] == "code_not_found"
    assert result.version.validation_report["errors"][0]["source_row"] == 2


def test_exact_duplicate_after_normalization_creates_invalid_version(
    tmp_path: Path,
    mapping_sync_context: tuple[Session, Settings, str, int],
) -> None:
    session, settings, scenario_id, _ = mapping_sync_context
    path = tmp_path / "duplicate.xlsx"
    _write_mapping(
        path,
        (
            _mapping_row("2710", "化学药品原料药制造", tier3=None),
            _mapping_row("2710.0", "化学药品原料药制造", tier3=""),
        ),
    )

    result = synchronize_technology_finance_mapping(
        session, read_mapping_source(path), settings, scenario_id=scenario_id
    )
    session.commit()

    duplicate = next(
        error
        for error in result.version.validation_report["errors"]
        if error["type"] == "exact_duplicate"
    )
    assert result.version.status == "invalid"
    assert duplicate["source_row"] == 3
    assert duplicate["duplicate_of_source_row"] == 2


def test_same_source_hash_reuses_existing_version(
    tmp_path: Path,
    mapping_sync_context: tuple[Session, Settings, str, int],
) -> None:
    session, settings, scenario_id, _ = mapping_sync_context
    path = tmp_path / "idempotent.xlsx"
    _write_mapping(path, (_mapping_row("2710", "化学药品原料药制造"),))
    source = read_mapping_source(path)

    first = synchronize_technology_finance_mapping(
        session, source, settings, scenario_id=scenario_id
    )
    session.commit()
    second = synchronize_technology_finance_mapping(
        session, source, settings, scenario_id=scenario_id
    )

    assert first.reused is False
    assert second.reused is True
    assert second.version.id == first.version.id
    version_count = session.scalar(
        select(func.count(FiveArticlesMappingVersion.id)).where(
            FiveArticlesMappingVersion.scenario_id == scenario_id
        )
    )
    row_count = session.scalar(
        select(func.count(FiveArticlesMappingRow.id)).where(
            FiveArticlesMappingRow.mapping_version_id == first.version.id
        )
    )
    assert version_count == 1
    assert row_count == 1


def test_invalid_version_has_no_rows_and_is_not_a_published_query_candidate(
    tmp_path: Path,
    mapping_sync_context: tuple[Session, Settings, str, int],
) -> None:
    session, settings, scenario_id, _ = mapping_sync_context
    path = tmp_path / "invalid-not-queryable.xlsx"
    _write_mapping(path, (_mapping_row("9999", "不存在行业"),))

    result = synchronize_technology_finance_mapping(
        session, read_mapping_source(path), settings, scenario_id=scenario_id
    )
    session.commit()

    assert session.scalar(
        select(FiveArticlesMappingVersion).where(
            FiveArticlesMappingVersion.scenario_id == scenario_id,
            FiveArticlesMappingVersion.status == "published",
        )
    ) is None
    assert session.scalar(
        select(func.count(FiveArticlesMappingRow.id)).where(
            FiveArticlesMappingRow.mapping_version_id == result.version.id
        )
    ) == 0


def test_missing_bilingual_header_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "missing-header.xlsx"
    _write_mapping(
        path,
        (_mapping_row("2710", "化学药品原料药制造"),),
        headers=BILINGUAL_HEADERS[:-1],
    )

    with pytest.raises(MappingHeaderError, match="missing headers"):
        read_mapping_source(path)


def test_columns_are_read_by_normalized_header_instead_of_position(
    tmp_path: Path,
) -> None:
    path = tmp_path / "reordered.xlsx"
    _write_mapping(
        path,
        (tuple(reversed(_mapping_row("2710", "化学药品原料药制造"))),),
        headers=tuple(reversed(BILINGUAL_HEADERS)),
    )

    source = read_mapping_source(path)

    assert source.rows[0].values["国民经济行业代码"] == "2710"
    assert source.rows[0].values["国民经济行业名称"] == "化学药品原料药制造"
    assert source.rows[0].values["主题"] == "高技术产业（制造业）"


def test_sync_uses_latest_catalog_version_matching_current_model_and_dimension(
    tmp_path: Path,
    mapping_sync_context: tuple[Session, Settings, str, int],
) -> None:
    session, settings, scenario_id, original_catalog_version_id = mapping_sync_context
    latest = NationalEconomyCatalogVersion(
        version=f"latest-{uuid4().hex}",
        source_hash=uuid4().hex * 2,
        embedding_model=settings.siliconflow_embedding_model,
        embedding_dimension=settings.embedding_dimension,
    )
    session.add(latest)
    session.flush()
    latest_id = latest.id
    session.add(
        NationalEconomyIndustryChunk(
            catalog_version_id=latest_id,
            major_category_code="C27",
            major_category_name="最新医药制造业",
            industry_code="2710",
            industry_name="最新化学药品原料药制造",
            source_row=2,
            text="最新目录定义",
            chunk_type="definition",
            embedding=[0.0] * 4096,
        )
    )
    session.commit()
    path = tmp_path / "latest-catalog.xlsx"
    _write_mapping(
        path,
        (_mapping_row("2710", "最新化学药品原料药制造"),),
    )

    try:
        result = synchronize_technology_finance_mapping(
            session, read_mapping_source(path), settings, scenario_id=scenario_id
        )
        session.commit()

        assert latest_id > original_catalog_version_id
        assert result.version.status == "published"
        assert result.version.validation_report["catalog_version_id"] == latest_id
    finally:
        session.execute(
            delete(NationalEconomyCatalogVersion).where(
                NationalEconomyCatalogVersion.id == latest_id
            )
        )
        session.commit()
