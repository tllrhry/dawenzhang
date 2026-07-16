from collections.abc import Iterator, Sequence
from uuid import uuid4

import pytest
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.db.session import get_sessionmaker
from app.models import FiveArticlesMappingRow, FiveArticlesMappingVersion
from app.services.technology_finance_mapping_query import (
    FiveArticlesMappingLookupResult,
    lookup_five_articles_hierarchy_mapping,
    lookup_five_articles_mapping,
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


@pytest.fixture
def four_scenario_query_session() -> Iterator[Session]:
    session = get_sessionmaker()()
    try:
        yield session
    finally:
        session.rollback()
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
    condition_criteria: str | None = None,
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
        "condition_criteria": condition_criteria,
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
) -> FiveArticlesMappingLookupResult:
    return lookup_five_articles_mapping(
        session,
        scenario_id=scenario_id,
        enterprise_four_digit_code=enterprise_four_digit_code,
        enterprise_major_category_code=enterprise_major_category_code,
        loan_direction_four_digit_code=loan_direction_four_digit_code,
        loan_direction_major_category_code=loan_direction_major_category_code,
    )


def _lookup_hierarchy(
    session: Session,
    scenario_id: str,
    *,
    enterprise_industry_code: str = "3011",
    enterprise_major_category_code: str = "C30",
    enterprise_middle_category_code: str | None = "C301",
    loan_direction_industry_code: str = "2710",
    loan_direction_major_category_code: str = "C27",
    loan_direction_middle_category_code: str | None = "C271",
) -> FiveArticlesMappingLookupResult:
    return lookup_five_articles_hierarchy_mapping(
        session,
        scenario_id=scenario_id,
        enterprise_industry_code=enterprise_industry_code,
        enterprise_major_category_code=enterprise_major_category_code,
        enterprise_middle_category_code=enterprise_middle_category_code,
        loan_direction_industry_code=loan_direction_industry_code,
        loan_direction_major_category_code=loan_direction_major_category_code,
        loan_direction_middle_category_code=loan_direction_middle_category_code,
    )


@pytest.mark.parametrize(
    "scenario_id",
    (
        "technology_finance",
        "green_finance",
        "digital_finance",
        "pension_finance",
    ),
)
def test_each_five_articles_scenario_hits_only_its_own_four_digit_mapping(
    four_scenario_query_session: Session,
    scenario_id: str,
) -> None:
    session = four_scenario_query_session
    version = _add_version(
        session,
        scenario_id,
        version_number=2_000_000_000,
        rows=(
            _mapping_row(
                neic_code="2710",
                neic_name="化学药品原料药制造",
                subject=f"{scenario_id}主题",
                tier1=f"{scenario_id}层级",
                source_row=2,
            ),
        ),
    )

    result = _lookup(session, scenario_id)

    assert result.status == "mapping_hit"
    assert result.mapping_version_id == version.id
    assert [label.scenario_id for label in result.loan_direction_labels] == [
        scenario_id
    ]
    assert [label.subject for label in result.loan_direction_labels] == [
        f"{scenario_id}主题"
    ]


def test_same_code_in_other_scenarios_is_never_used_as_a_mapping_fallback(
    four_scenario_query_session: Session,
) -> None:
    session = four_scenario_query_session
    suffix = uuid4().hex
    requested_scenario = f"digital_finance_{suffix}"
    other_scenarios = (
        f"technology_finance_{suffix}",
        f"green_finance_{suffix}",
        f"pension_finance_{suffix}",
    )
    _add_version(
        session,
        requested_scenario,
        rows=(
            _mapping_row(
                neic_code="3011",
                neic_name="工业设备制造",
                subject="数字场景非投向主题",
                tier1="数字场景层级",
                source_row=2,
            ),
        ),
    )
    for index, other_scenario in enumerate(other_scenarios, start=2):
        _add_version(
            session,
            other_scenario,
            rows=(
                _mapping_row(
                    neic_code="2710",
                    neic_name="化学药品原料药制造",
                    subject=f"其他场景主题{index}",
                    tier1=f"其他场景层级{index}",
                    source_row=2,
                ),
            ),
        )

    result = _lookup(session, requested_scenario)

    assert result.status == "not_applicable"
    assert result.loan_direction_labels == ()
    assert all(
        label.scenario_id == requested_scenario
        for label in result.enterprise_labels
    )


def test_other_scenario_published_mapping_does_not_hide_missing_requested_version(
    four_scenario_query_session: Session,
) -> None:
    session = four_scenario_query_session
    suffix = uuid4().hex
    requested_scenario = f"pension_finance_{suffix}"
    _add_version(
        session,
        f"green_finance_{suffix}",
        rows=(
            _mapping_row(
                neic_code="2710",
                neic_name="化学药品原料药制造",
                subject="绿色场景主题",
                tier1="绿色场景层级",
                source_row=2,
            ),
        ),
    )

    result = _lookup(session, requested_scenario)

    assert result.status == "needs_review"
    assert result.detail == "published_mapping_version_not_found"
    assert result.mapping_version_id is None
    assert result.loan_direction_labels == ()


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


def test_four_digit_mapping_takes_precedence_over_lower_granularity_rows(
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

    result = _lookup_hierarchy(session, scenario_id)

    assert result.status == "mapping_hit"
    assert {(label.subject, label.neic_code) for label in result.loan_direction_labels} == {
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


def test_lower_granularity_rows_are_not_combined_with_a_four_digit_hit(
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

    result = _lookup_hierarchy(session, scenario_id)

    assert {(label.subject, label.neic_code) for label in result.loan_direction_labels} == {
        ("四位独立主题", "2710"),
    }


def test_three_digit_mapping_is_used_when_four_digit_mapping_is_absent(
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
                tier1="医药制造业整体",
                source_row=2,
            ),
            _mapping_row(
                neic_code="271",
                neic_name="化学药品原料药制造",
                subject="中类主题",
                tier1="化学药品制造",
                source_row=3,
            ),
        ),
    )

    result = _lookup_hierarchy(session, scenario_id)

    assert [(label.neic_code, label.code_level) for label in result.loan_direction_labels] == [
        ("271", 3)
    ]


def test_two_digit_mapping_is_the_final_fallback(
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
                tier1="医药制造业整体",
                source_row=2,
            ),
        ),
    )

    result = _lookup_hierarchy(session, scenario_id)

    assert [(label.neic_code, label.code_level) for label in result.loan_direction_labels] == [
        ("27", 2)
    ]


def test_three_digit_stage_a_result_uses_its_own_mapping_before_major_fallback(
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
                tier1="医药制造业整体",
                source_row=2,
            ),
            _mapping_row(
                neic_code="271",
                neic_name="化学药品制造",
                subject="中类主题",
                tier1="化学药品制造",
                source_row=3,
            ),
        ),
    )

    result = _lookup_hierarchy(
        session,
        scenario_id,
        loan_direction_industry_code="C271",
        loan_direction_middle_category_code=None,
    )

    assert [(label.neic_code, label.code_level) for label in result.loan_direction_labels] == [
        ("271", 3)
    ]


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


def test_same_taxonomy_with_different_conditions_returns_distinct_candidates(
    mapping_query_context: tuple[Session, str],
) -> None:
    session, scenario_id = mapping_query_context
    shared = dict(
        neic_code="2710",
        neic_name="化学药品原料药制造",
        subject="能源绿色低碳转型",
        tier1="新能源与清洁能源装备制造",
        tier2="新型储能产品制造",
    )
    _add_version(
        session,
        scenario_id,
        rows=(
            _mapping_row(
                **shared,
                source_row=646,
                condition_criteria="超级电容储能产品及配套系统设备制造。",
            ),
            _mapping_row(
                **shared,
                source_row=648,
                condition_criteria="锂离子、钠离子等储能电池及配套系统设备制造。",
            ),
        ),
    )

    result = _lookup(session, scenario_id)

    assert result.status == "mapping_hit"
    assert [label.source_row for label in result.loan_direction_labels] == [646, 648]
    assert [label.condition_criteria for label in result.loan_direction_labels] == [
        "超级电容储能产品及配套系统设备制造。",
        "锂离子、钠离子等储能电池及配套系统设备制造。",
    ]


def test_query_code_name_conflict_still_needs_review(
    mapping_query_context: tuple[Session, str],
) -> None:
    session, scenario_id = mapping_query_context
    first = _mapping_row(
        neic_code="2710",
        neic_name="化学药品原料药制造",
        subject="主题一",
        tier1="层级一",
        source_row=2,
    )
    _add_version(
        session,
        scenario_id,
        rows=(
            first,
            {
                **first,
                "neic_name": "冲突行业名称",
                "subject": "主题二",
                "source_row": 3,
            },
        ),
    )

    result = _lookup(session, scenario_id)

    assert result.status == "needs_review"
    assert result.detail == "mapping_query_code_name_conflict"


def test_distinct_candidates_with_duplicate_source_row_still_need_review(
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
                subject="主题一",
                tier1="层级一",
                source_row=2,
            ),
            _mapping_row(
                neic_code="2710",
                neic_name="化学药品原料药制造",
                subject="主题二",
                tier1="层级二",
                source_row=2,
            ),
        ),
    )

    result = _lookup(session, scenario_id)

    assert result.status == "needs_review"
    assert result.detail == "mapping_query_duplicate_source_row"


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
