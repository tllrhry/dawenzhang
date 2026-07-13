from collections.abc import Iterator, Sequence
from uuid import uuid4

import pytest
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.db.session import get_sessionmaker
from app.models import FiveArticlesMappingRow, FiveArticlesMappingVersion
from app.services.technology_finance_mapping_query import (
    TechnologyFinanceMappingLookupResult,
    lookup_technology_finance_mapping,
)


@pytest.fixture
def mapping_query_context() -> Iterator[tuple[Session, str]]:
    session = get_sessionmaker()()
    scenario_id = f"technology_finance_query_{uuid4().hex}"
    try:
        yield session, scenario_id
    finally:
        session.rollback()
        session.execute(
            delete(FiveArticlesMappingVersion).where(
                FiveArticlesMappingVersion.scenario_id == scenario_id
            )
        )
        session.commit()
        session.close()


def _mapping_row(
    *,
    neic_code: str,
    neic_name: str,
    subject: str,
    tier1: str,
    source_row: int,
    tier2: str | None = None,
    tier3: str | None = None,
    tier4: str | None = None,
) -> dict[str, object]:
    return {
        "neic_code": neic_code,
        "code_level": len(neic_code),
        "neic_name": neic_name,
        "subject": subject,
        "tier1": tier1,
        "tier2": tier2,
        "tier3": tier3,
        "tier4": tier4,
        "source_row": source_row,
    }


def _add_version(
    session: Session,
    scenario_id: str,
    *,
    rows: Sequence[dict[str, object]],
    version_number: int = 1,
    status: str = "published",
    report_overrides: dict[str, object] | None = None,
) -> FiveArticlesMappingVersion:
    version = FiveArticlesMappingVersion(
        scenario_id=scenario_id,
        version=version_number,
        source_hash=uuid4().hex * 2,
        status=status,
        validation_report={},
    )
    session.add(version)
    session.flush()
    session.add_all(
        [
            FiveArticlesMappingRow(
                mapping_version_id=version.id,
                scenario_id=scenario_id,
                **row,
            )
            for row in rows
        ]
    )
    report: dict[str, object] = {
        "valid": True,
        "scenario_id": scenario_id,
        "published_row_count": len(rows),
        "errors": [],
    }
    if report_overrides is not None:
        report.update(report_overrides)
    version.validation_report = report
    session.flush()
    return version


def _lookup(
    session: Session,
    scenario_id: str,
    *,
    enterprise_four_digit_code: str = "3011",
    enterprise_major_category_code: str = "C30",
    loan_direction_four_digit_code: str = "2710",
    loan_direction_major_category_code: str = "C27",
) -> TechnologyFinanceMappingLookupResult:
    return lookup_technology_finance_mapping(
        session,
        scenario_id=scenario_id,
        enterprise_four_digit_code=enterprise_four_digit_code,
        enterprise_major_category_code=enterprise_major_category_code,
        loan_direction_four_digit_code=loan_direction_four_digit_code,
        loan_direction_major_category_code=loan_direction_major_category_code,
    )


def test_lookup_queries_enterprise_and_loan_direction_sides_separately(
    mapping_query_context: tuple[Session, str],
) -> None:
    session, scenario_id = mapping_query_context
    _add_version(
        session,
        scenario_id,
        rows=(
            _mapping_row(
                neic_code="3011",
                neic_name="工业设备制造",
                subject="企业主题",
                tier1="企业层级",
                source_row=2,
            ),
            _mapping_row(
                neic_code="2710",
                neic_name="化学药品原料药制造",
                subject="投向主题",
                tier1="投向层级",
                source_row=3,
            ),
        ),
    )

    result = _lookup(session, scenario_id)

    assert result.status == "mapping_hit"
    assert [label.subject for label in result.enterprise_labels] == ["企业主题"]
    assert [label.subject for label in result.loan_direction_labels] == ["投向主题"]


def test_four_digit_hit_does_not_invent_an_implicit_two_digit_label(
    mapping_query_context: tuple[Session, str],
) -> None:
    session, scenario_id = mapping_query_context
    _add_version(
        session,
        scenario_id,
        rows=(
            _mapping_row(
                neic_code="2710",
                neic_name="化学药品原料药制造",
                subject="高技术产业（制造业）",
                tier1="医药制造业",
                source_row=2,
            ),
        ),
    )

    result = _lookup(session, scenario_id)

    assert result.status == "mapping_hit"
    assert [(label.neic_code, label.code_level) for label in result.loan_direction_labels] == [
        ("2710", 4)
    ]


def test_explicit_two_digit_row_is_a_valid_mapping_hit(
    mapping_query_context: tuple[Session, str],
) -> None:
    session, scenario_id = mapping_query_context
    _add_version(
        session,
        scenario_id,
        rows=(
            _mapping_row(
                neic_code="27",
                neic_name="医药制造业",
                subject="大类整体主题",
                tier1="医药制造业整体",
                source_row=2,
            ),
        ),
    )

    result = _lookup(session, scenario_id)

    assert result.status == "mapping_hit"
    assert [(label.neic_code, label.code_level) for label in result.loan_direction_labels] == [
        ("27", 2)
    ]


def test_both_levels_and_multiple_themes_preserve_all_distinct_paths(
    mapping_query_context: tuple[Session, str],
) -> None:
    session, scenario_id = mapping_query_context
    _add_version(
        session,
        scenario_id,
        rows=(
            _mapping_row(
                neic_code="27",
                neic_name="医药制造业",
                subject="大类整体主题",
                tier1="医药制造业整体",
                source_row=2,
            ),
            _mapping_row(
                neic_code="2710",
                neic_name="化学药品原料药制造",
                subject="高技术产业（制造业）",
                tier1="医药制造业",
                source_row=3,
            ),
            _mapping_row(
                neic_code="2710",
                neic_name="化学药品原料药制造",
                subject="国家科技重大项目",
                tier1="重大新药创制",
                source_row=4,
            ),
        ),
    )

    result = _lookup(session, scenario_id)

    assert result.status == "mapping_hit"
    assert {
        (label.subject, label.neic_code) for label in result.loan_direction_labels
    } == {
        ("大类整体主题", "27"),
        ("高技术产业（制造业）", "2710"),
        ("国家科技重大项目", "2710"),
    }


def test_same_theme_ancestor_two_digit_label_is_removed(
    mapping_query_context: tuple[Session, str],
) -> None:
    session, scenario_id = mapping_query_context
    _add_version(
        session,
        scenario_id,
        rows=(
            _mapping_row(
                neic_code="27",
                neic_name="医药制造业",
                subject="高技术产业（制造业）",
                tier1="医药制造业",
                source_row=2,
            ),
            _mapping_row(
                neic_code="2710",
                neic_name="化学药品原料药制造",
                subject="高技术产业（制造业）",
                tier1="医药制造业",
                tier2="化学药品制造",
                source_row=3,
            ),
        ),
    )

    result = _lookup(session, scenario_id)

    assert [(label.neic_code, label.taxonomy_path) for label in result.loan_direction_labels] == [
        ("2710", ("医药制造业", "化学药品制造"))
    ]


def test_two_digit_label_is_kept_as_fallback_for_a_theme_without_four_digit_hit(
    mapping_query_context: tuple[Session, str],
) -> None:
    session, scenario_id = mapping_query_context
    _add_version(
        session,
        scenario_id,
        rows=(
            _mapping_row(
                neic_code="27",
                neic_name="医药制造业",
                subject="大类兜底主题",
                tier1="医药制造业",
                source_row=2,
            ),
            _mapping_row(
                neic_code="2710",
                neic_name="化学药品原料药制造",
                subject="四位独立主题",
                tier1="原料药",
                source_row=3,
            ),
        ),
    )

    result = _lookup(session, scenario_id)

    assert {(label.subject, label.neic_code) for label in result.loan_direction_labels} == {
        ("大类兜底主题", "27"),
        ("四位独立主题", "2710"),
    }


def test_normal_loan_direction_miss_is_not_applicable(
    mapping_query_context: tuple[Session, str],
) -> None:
    session, scenario_id = mapping_query_context
    _add_version(
        session,
        scenario_id,
        rows=(
            _mapping_row(
                neic_code="3011",
                neic_name="工业设备制造",
                subject="企业主题",
                tier1="企业层级",
                source_row=2,
            ),
        ),
    )

    result = _lookup(session, scenario_id)

    assert result.status == "not_applicable"
    assert result.loan_direction_labels == ()
    assert [label.neic_code for label in result.enterprise_labels] == ["3011"]


@pytest.mark.parametrize("status", ["draft", "invalid"])
def test_absent_published_version_needs_review(
    mapping_query_context: tuple[Session, str],
    status: str,
) -> None:
    session, scenario_id = mapping_query_context
    _add_version(
        session,
        scenario_id,
        status=status,
        rows=(
            _mapping_row(
                neic_code="2710",
                neic_name="化学药品原料药制造",
                subject="主题",
                tier1="层级",
                source_row=2,
            ),
        ),
    )

    result = _lookup(session, scenario_id)

    assert result.status == "needs_review"
    assert result.detail == "published_mapping_version_not_found"
    assert result.loan_direction_labels == ()


def test_latest_published_version_is_selected_within_the_scenario(
    mapping_query_context: tuple[Session, str],
) -> None:
    session, scenario_id = mapping_query_context
    _add_version(
        session,
        scenario_id,
        version_number=1,
        rows=(
            _mapping_row(
                neic_code="2710",
                neic_name="化学药品原料药制造",
                subject="旧主题",
                tier1="旧层级",
                source_row=2,
            ),
        ),
    )
    latest = _add_version(
        session,
        scenario_id,
        version_number=2,
        rows=(
            _mapping_row(
                neic_code="3011",
                neic_name="工业设备制造",
                subject="最新主题",
                tier1="最新层级",
                source_row=2,
            ),
        ),
    )
    _add_version(
        session,
        scenario_id,
        version_number=3,
        status="invalid",
        rows=(
            _mapping_row(
                neic_code="2710",
                neic_name="化学药品原料药制造",
                subject="不可查询主题",
                tier1="不可查询层级",
                source_row=2,
            ),
        ),
    )

    result = _lookup(session, scenario_id)

    assert result.status == "not_applicable"
    assert result.mapping_version_id == latest.id
    assert result.mapping_version == 2


@pytest.mark.parametrize(
    ("report_overrides", "expected_detail"),
    [
        (
            {"errors": [{"type": "name_code_conflict"}]},
            "published_mapping_code_name_conflict",
        ),
        ({"published_row_count": 2}, "published_mapping_row_count_conflict"),
    ],
)
def test_published_version_validation_or_completeness_conflict_needs_review(
    mapping_query_context: tuple[Session, str],
    report_overrides: dict[str, object],
    expected_detail: str,
) -> None:
    session, scenario_id = mapping_query_context
    _add_version(
        session,
        scenario_id,
        rows=(
            _mapping_row(
                neic_code="2710",
                neic_name="化学药品原料药制造",
                subject="主题",
                tier1="层级",
                source_row=2,
            ),
        ),
        report_overrides=report_overrides,
    )

    result = _lookup(session, scenario_id)

    assert result.status == "needs_review"
    assert result.detail == expected_detail
    assert result.enterprise_labels == ()
    assert result.loan_direction_labels == ()


def test_duplicate_query_key_needs_review_instead_of_choosing_a_source_row(
    mapping_query_context: tuple[Session, str],
) -> None:
    session, scenario_id = mapping_query_context
    duplicate = _mapping_row(
        neic_code="2710",
        neic_name="化学药品原料药制造",
        subject="重复主题",
        tier1="重复层级",
        source_row=2,
    )
    _add_version(
        session,
        scenario_id,
        rows=(duplicate, {**duplicate, "source_row": 3}),
    )

    result = _lookup(session, scenario_id)

    assert result.status == "needs_review"
    assert result.detail == "mapping_query_duplicate_taxonomy_code"
    assert result.loan_direction_labels == ()


def test_duplicate_latest_published_version_number_needs_review(
    mapping_query_context: tuple[Session, str],
) -> None:
    session, scenario_id = mapping_query_context
    row = _mapping_row(
        neic_code="2710",
        neic_name="化学药品原料药制造",
        subject="主题",
        tier1="层级",
        source_row=2,
    )
    _add_version(session, scenario_id, version_number=1, rows=(row,))
    _add_version(session, scenario_id, version_number=1, rows=(row,))

    result = _lookup(session, scenario_id)

    assert result.status == "needs_review"
    assert result.detail == "duplicate_published_mapping_version:1"
