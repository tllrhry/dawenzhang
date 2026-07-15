from collections.abc import Iterator
from dataclasses import replace
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.session import get_sessionmaker
from app.models import (
    FiveArticlesMappingVersion,
    FiveArticlesResult,
    NationalEconomyClassificationCase,
    NationalEconomyClassificationResult,
)
from app.services import technology_finance_classification_workflow as workflow_module
from app.services.green_finance_condition_matching import GreenFinanceConditionCandidate
from app.services.scenario_registry import (
    DIGITAL_FINANCE_REGISTRATION,
    GREEN_FINANCE_REGISTRATION,
    PENSION_FINANCE_REGISTRATION,
    TECHNOLOGY_FINANCE_REGISTRATION,
    ScenarioRegistration,
)
from app.services.technology_finance_classification_workflow import (
    classify_five_articles_case,
    classify_technology_finance_case,
    reclassify_five_articles_case,
    reclassify_technology_finance_case,
    run_five_articles_stage_b,
)
from app.services.technology_finance_mapping_query import (
    FiveArticlesMappingLabel,
    FiveArticlesMappingLookupResult,
)
from app.services.technology_finance_stage_b import (
    TechnologyFinanceStageBError,
    TechnologyFinanceStageBResult,
)


@pytest.fixture
def workflow_context() -> Iterator[
    tuple[Session, NationalEconomyClassificationCase, FiveArticlesMappingVersion]
]:
    session = get_sessionmaker()()
    scenario_id = "technology_finance"
    case = NationalEconomyClassificationCase(
        scenario=scenario_id,
        input_payload={
            "enterprise_name": "科技金融工作流测试企业",
            "main_business": "工业设备制造",
            "loan_purpose": "用于化学药品项目建设",
        },
        original_filename="technology-finance.docx",
        status="pending_classification",
    )
    mapping_version = FiveArticlesMappingVersion(
        scenario_id=scenario_id,
        version=1,
        source_hash=uuid4().hex * 2,
        status="published",
        validation_report={"valid": True},
    )
    session.add_all([case, mapping_version])
    session.commit()
    case_id = case.id
    mapping_version_id = mapping_version.id
    try:
        yield session, case, mapping_version
    finally:
        session.rollback()
        session.execute(
            delete(NationalEconomyClassificationCase).where(
                NationalEconomyClassificationCase.id == case_id
            )
        )
        session.execute(
            delete(FiveArticlesMappingVersion).where(
                FiveArticlesMappingVersion.id == mapping_version_id
            )
        )
        session.commit()
        session.close()


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        database_url="postgresql+psycopg://user:pass@localhost/test",
        siliconflow_api_key="siliconflow-key",
        deepseek_api_key="deepseek-key",
    )


def _persist_stage_a(
    session: Session,
    case: NationalEconomyClassificationCase,
    *,
    status: str = "completed",
    objection: str | None = None,
) -> NationalEconomyClassificationResult:
    current_version = session.scalar(
        select(func.max(NationalEconomyClassificationResult.version)).where(
            NationalEconomyClassificationResult.case_id == case.id
        )
    )
    result = NationalEconomyClassificationResult(
        case_id=case.id,
        version=(current_version or 0) + 1,
        status=status,
        industry_code="3011" if status == "completed" else None,
        industry_major_code="C30" if status == "completed" else None,
        industry_middle_code="C301" if status == "completed" else None,
        industry_name="工业设备制造" if status == "completed" else None,
        loan_industry_code="2710" if status == "completed" else None,
        loan_industry_major_code="C27" if status == "completed" else None,
        loan_industry_middle_code="C271" if status == "completed" else None,
        loan_industry_name="化学药品原料药制造" if status == "completed" else None,
        loan_matching_basis=("贷款用于化学药品项目" if status == "completed" else None),
        rationale="Stage A 测试依据",
        candidate_snapshot=[],
        objection=None if objection is None else {"description": objection},
        model_output={"stage": "a", "status": status},
    )
    session.add(result)
    case.status = status
    session.commit()
    session.refresh(result)
    return result


def _mapping_result(
    mapping_version_id: int,
    *,
    status: str = "mapping_hit",
) -> FiveArticlesMappingLookupResult:
    label = FiveArticlesMappingLabel(
        mapping_version_id=mapping_version_id,
        scenario_id="technology_finance",
        neic_code="2710",
        code_level=4,
        neic_name="化学药品原料药制造",
        subject="高技术产业（制造业）",
        tier1="医药制造业",
        tier2=None,
        tier3=None,
        tier4=None,
        source_row=12,
    )
    return FiveArticlesMappingLookupResult(
        status=status,  # type: ignore[arg-type]
        mapping_version_id=mapping_version_id,
        mapping_version=1,
        enterprise_labels=(label,) if status == "mapping_hit" else (),
        loan_direction_labels=(label,) if status == "mapping_hit" else (),
        detail={
            "mapping_hit": "loan_direction_mapping_hit",
            "not_applicable": "loan_direction_has_no_explicit_mapping",
            "needs_review": "published_mapping_version_not_found",
        }[status],
    )


def _stage_b_decision() -> TechnologyFinanceStageBResult:
    return TechnologyFinanceStageBResult(
        labels=(
            {
                "subject": "高技术产业（制造业）",
                "taxonomy_path": ["医药制造业"],
                "NEIC_Code": "2710",
                "NEIC_Name": "化学药品原料药制造",
                "source_row": 12,
                "matching_basis": "贷款投向命中确定性映射。",
                "evidence_refs": [],
            },
        ),
        consistency_status="consistent",
        consistency_basis="贷款用途服务于企业科技活动。",
        consistency_evidence_refs=(
            {
                "type": "business",
                "field_key": "loan_purpose",
                "excerpt": "用于化学药品项目建设",
            },
        ),
        model_output={"validated": True},
    )


def test_stage_b_failure_preserves_stage_a_and_retry_reuses_it_idempotently(
    workflow_context: tuple[
        Session, NationalEconomyClassificationCase, FiveArticlesMappingVersion
    ],
) -> None:
    session, case, mapping_version = workflow_context
    stage_a_classifier = MagicMock(
        side_effect=lambda session, case, settings: _persist_stage_a(session, case)
    )
    mapping_lookup = MagicMock(return_value=_mapping_result(mapping_version.id))
    failed_stage_b = MagicMock(
        side_effect=TechnologyFinanceStageBError("DeepSeek timed out")
    )

    failed = classify_technology_finance_case(
        session,
        case,
        _settings(),
        stage_a_classifier=stage_a_classifier,
        mapping_lookup=mapping_lookup,
        stage_b_classifier=failed_stage_b,
    )

    assert failed.stage_b_result is not None
    assert failed.stage_b_result.status == "classification_failed"
    assert failed.stage_b_result.stage_a_result_id == failed.stage_a_result.id
    assert session.get(
        NationalEconomyClassificationResult, failed.stage_a_result.id
    ) is not None
    assert session.scalar(
        select(func.count(NationalEconomyClassificationResult.id)).where(
            NationalEconomyClassificationResult.case_id == case.id
        )
    ) == 1
    assert mapping_lookup.call_args.kwargs["enterprise_middle_category_code"] == "C301"
    assert mapping_lookup.call_args.kwargs["loan_direction_middle_category_code"] == "C271"

    successful_stage_b = MagicMock(return_value=_stage_b_decision())
    retry = classify_technology_finance_case(
        session,
        case,
        _settings(),
        stage_a_classifier=stage_a_classifier,
        mapping_lookup=mapping_lookup,
        stage_b_classifier=successful_stage_b,
    )

    assert retry.stage_a_result.id == failed.stage_a_result.id
    assert retry.stage_b_result is not None
    assert retry.stage_b_result.status == "completed"
    assert retry.stage_b_result.version == 2
    assert stage_a_classifier.call_count == 1
    assert session.scalar(
        select(func.count(NationalEconomyClassificationResult.id)).where(
            NationalEconomyClassificationResult.case_id == case.id
        )
    ) == 1

    mapping_calls_before = mapping_lookup.call_count
    stage_b_calls_before = successful_stage_b.call_count
    duplicate = classify_technology_finance_case(
        session,
        case,
        _settings(),
        stage_a_classifier=stage_a_classifier,
        mapping_lookup=mapping_lookup,
        stage_b_classifier=successful_stage_b,
    )

    assert duplicate.stage_b_result is not None
    assert duplicate.stage_b_result.id == retry.stage_b_result.id
    assert mapping_lookup.call_count == mapping_calls_before
    assert successful_stage_b.call_count == stage_b_calls_before
    assert session.scalar(
        select(func.count(FiveArticlesResult.id)).where(
            FiveArticlesResult.case_id == case.id
        )
    ) == 2


def test_objection_creates_new_stage_a_and_new_stage_b_versions(
    workflow_context: tuple[
        Session, NationalEconomyClassificationCase, FiveArticlesMappingVersion
    ],
) -> None:
    session, case, mapping_version = workflow_context
    mapping_lookup = MagicMock(return_value=_mapping_result(mapping_version.id))
    stage_b_classifier = MagicMock(return_value=_stage_b_decision())
    initial = classify_technology_finance_case(
        session,
        case,
        _settings(),
        stage_a_classifier=lambda session, case, settings: _persist_stage_a(
            session, case
        ),
        mapping_lookup=mapping_lookup,
        stage_b_classifier=stage_b_classifier,
    )

    stage_a_reclassifier = MagicMock(
        side_effect=lambda session, case, objection, settings: _persist_stage_a(
            session,
            case,
            objection=objection,
        )
    )
    objection = reclassify_technology_finance_case(
        session,
        case,
        "贷款投向应按医药项目重新判断",
        _settings(),
        stage_a_reclassifier=stage_a_reclassifier,
        mapping_lookup=mapping_lookup,
        stage_b_classifier=stage_b_classifier,
    )

    assert initial.stage_a_result.version == 1
    assert objection.stage_a_result.version == 2
    assert initial.stage_b_result is not None
    assert objection.stage_b_result is not None
    assert initial.stage_b_result.version == 1
    assert objection.stage_b_result.version == 2
    assert objection.stage_b_result.stage_a_result_id == objection.stage_a_result.id
    assert objection.stage_a_result.objection == {
        "description": "贷款投向应按医药项目重新判断"
    }
    assert session.scalars(
        select(NationalEconomyClassificationResult)
        .where(NationalEconomyClassificationResult.case_id == case.id)
        .order_by(NationalEconomyClassificationResult.version)
    ).all() == [initial.stage_a_result, objection.stage_a_result]


@pytest.mark.parametrize("stage_a_status", ["needs_review", "classification_failed"])
def test_uncompleted_stage_a_short_circuits_without_mapping_or_stage_b(
    workflow_context: tuple[
        Session, NationalEconomyClassificationCase, FiveArticlesMappingVersion
    ],
    stage_a_status: str,
) -> None:
    session, case, _ = workflow_context
    mapping_lookup = MagicMock()
    stage_b_classifier = MagicMock()

    outcome = classify_technology_finance_case(
        session,
        case,
        _settings(),
        stage_a_classifier=lambda session, case, settings: _persist_stage_a(
            session,
            case,
            status=stage_a_status,
        ),
        mapping_lookup=mapping_lookup,
        stage_b_classifier=stage_b_classifier,
    )

    assert outcome.stage_a_result.status == stage_a_status
    assert outcome.stage_b_result is None
    mapping_lookup.assert_not_called()
    stage_b_classifier.assert_not_called()
    assert session.scalar(
        select(func.count(FiveArticlesResult.id)).where(
            FiveArticlesResult.case_id == case.id
        )
    ) == 0


def _multi_subject_labels(
    mapping_version_id: int,
) -> tuple[FiveArticlesMappingLabel, ...]:
    return (
        FiveArticlesMappingLabel(
            mapping_version_id=mapping_version_id,
            scenario_id="technology_finance",
            neic_code="2710",
            code_level=4,
            neic_name="化学药品原料药制造",
            subject="高技术产业（制造业）",
            tier1="医药制造业",
            tier2=None,
            tier3=None,
            tier4=None,
            source_row=11,
        ),
        FiveArticlesMappingLabel(
            mapping_version_id=mapping_version_id,
            scenario_id="technology_finance",
            neic_code="2710",
            code_level=4,
            neic_name="化学药品原料药制造",
            subject="国家科技重大项目",
            tier1="重大新药创制",
            tier2=None,
            tier3=None,
            tier4=None,
            source_row=22,
        ),
    )


def test_multiple_candidates_are_narrowed_to_one_before_stage_b(
    workflow_context: tuple[
        Session, NationalEconomyClassificationCase, FiveArticlesMappingVersion
    ],
) -> None:
    session, case, mapping_version = workflow_context
    candidates = _multi_subject_labels(mapping_version.id)
    mapping_result = FiveArticlesMappingLookupResult(
        status="mapping_hit",
        mapping_version_id=mapping_version.id,
        mapping_version=1,
        enterprise_labels=(),
        loan_direction_labels=candidates,
        detail="loan_direction_mapping_hit",
    )
    mapping_lookup = MagicMock(return_value=mapping_result)
    label_selector = MagicMock(return_value=candidates[1])
    stage_b_classifier = MagicMock(return_value=_stage_b_decision())

    outcome = classify_technology_finance_case(
        session,
        case,
        _settings(),
        stage_a_classifier=lambda session, case, settings: _persist_stage_a(
            session, case
        ),
        mapping_lookup=mapping_lookup,
        label_selector=label_selector,
        stage_b_classifier=stage_b_classifier,
    )

    label_selector.assert_not_called()
    stage_b_classifier.assert_called_once()
    assert stage_b_classifier.call_args.args[3] == candidates
    assert outcome.stage_b_result is not None
    assert outcome.stage_b_result.status == "completed"


def _persist_same_code_stage_a(
    session: Session, case: NationalEconomyClassificationCase
) -> NationalEconomyClassificationResult:
    # enterprise and loan four-digit codes are identical (both 2710).
    result = NationalEconomyClassificationResult(
        case_id=case.id,
        version=1,
        status="completed",
        industry_code="2710",
        industry_major_code="C27",
        industry_name="化学药品原料药制造",
        loan_industry_code="2710",
        loan_industry_major_code="C27",
        loan_industry_name="化学药品原料药制造",
        loan_matching_basis="贷款用于化学药品项目",
        rationale="Stage A 测试依据",
        candidate_snapshot=[],
        model_output={"stage": "a", "status": "completed"},
    )
    session.add(result)
    case.status = "completed"
    session.commit()
    session.refresh(result)
    return result


def test_same_code_narrows_enterprise_side_to_the_same_winner(
    workflow_context: tuple[
        Session, NationalEconomyClassificationCase, FiveArticlesMappingVersion
    ],
) -> None:
    session, case, mapping_version = workflow_context
    candidates = _multi_subject_labels(mapping_version.id)
    mapping_result = FiveArticlesMappingLookupResult(
        status="mapping_hit",
        mapping_version_id=mapping_version.id,
        mapping_version=1,
        enterprise_labels=candidates,
        loan_direction_labels=candidates,
        detail="loan_direction_mapping_hit",
    )
    mapping_lookup = MagicMock(return_value=mapping_result)
    label_selector = MagicMock(return_value=candidates[0])
    stage_b_classifier = MagicMock(return_value=_stage_b_decision())

    outcome = classify_technology_finance_case(
        session,
        case,
        _settings(),
        stage_a_classifier=lambda session, case, settings: _persist_same_code_stage_a(
            session, case
        ),
        mapping_lookup=mapping_lookup,
        label_selector=label_selector,
        stage_b_classifier=stage_b_classifier,
    )

    label_selector.assert_not_called()
    stage_b_classifier.assert_called_once()
    assert stage_b_classifier.call_args.args[2] == candidates
    assert stage_b_classifier.call_args.args[3] == candidates
    assert outcome.stage_b_result is not None


@pytest.mark.parametrize(
    ("mapping_status", "result_status", "consistency_status"),
    [
        ("not_applicable", "not_applicable", "not_applicable"),
        ("needs_review", "needs_review", "needs_review"),
    ],
)
def test_non_mapping_hit_statuses_persist_without_model_call(
    workflow_context: tuple[
        Session, NationalEconomyClassificationCase, FiveArticlesMappingVersion
    ],
    mapping_status: str,
    result_status: str,
    consistency_status: str,
) -> None:
    session, case, mapping_version = workflow_context
    stage_b_classifier = MagicMock()

    outcome = classify_technology_finance_case(
        session,
        case,
        _settings(),
        stage_a_classifier=lambda session, case, settings: _persist_stage_a(
            session, case
        ),
        mapping_lookup=MagicMock(
            return_value=_mapping_result(mapping_version.id, status=mapping_status)
        ),
        stage_b_classifier=stage_b_classifier,
    )

    assert outcome.stage_b_result is not None
    assert outcome.stage_b_result.status == result_status
    assert outcome.stage_b_result.consistency_status == consistency_status
    assert outcome.stage_b_result.labels == []
    stage_b_classifier.assert_not_called()


@pytest.fixture
def green_workflow_context() -> Iterator[
    tuple[Session, NationalEconomyClassificationCase, FiveArticlesMappingVersion]
]:
    session = get_sessionmaker()()
    case = NationalEconomyClassificationCase(
        scenario="green_finance",
        input_payload={
            "enterprise_name": "绿色金融工作流测试企业",
            "core_products_services": "环保设备",
            "main_business": "环保工程",
            "loan_purpose": "用于节能改造项目",
            "trade_goods_services": "高效电机",
        },
        original_filename="green-finance.docx",
        status="pending_classification",
    )
    mapping_version = FiveArticlesMappingVersion(
        scenario_id="green_finance", version=1, source_hash=uuid4().hex * 2,
        status="published", validation_report={"valid": True},
    )
    session.add_all([case, mapping_version])
    session.commit()
    try:
        yield session, case, mapping_version
    finally:
        session.rollback()
        session.execute(delete(NationalEconomyClassificationCase).where(
            NationalEconomyClassificationCase.id == case.id
        ))
        session.execute(delete(FiveArticlesMappingVersion).where(
            FiveArticlesMappingVersion.id == mapping_version.id
        ))
        session.commit()
        session.close()


def _green_condition_candidate(mapping_version_id: int) -> GreenFinanceConditionCandidate:
    return GreenFinanceConditionCandidate(
        label=FiveArticlesMappingLabel(
            mapping_version_id=mapping_version_id, scenario_id="green_finance",
            neic_code="-", code_level=None, neic_name="无行业代码",
            subject="绿色产业", tier1="节能环保", tier2="节能改造",
            tier3=None, tier4=None, source_row=88,
        ),
        condition_criteria="节能改造项目", vector_score=0.9, rerank_score=0.9,
    )


def _green_not_applicable_mapping(mapping_version_id: int) -> FiveArticlesMappingLookupResult:
    return FiveArticlesMappingLookupResult(
        status="not_applicable", mapping_version_id=mapping_version_id,
        mapping_version=1, enterprise_labels=(), loan_direction_labels=(),
        detail="loan_direction_has_no_explicit_mapping",
    )


def test_green_condition_fallback_completes_and_serializes_match_method(
    green_workflow_context: tuple[Session, NationalEconomyClassificationCase, FiveArticlesMappingVersion],
) -> None:
    session, case, mapping_version = green_workflow_context
    candidate = _green_condition_candidate(mapping_version.id)
    retriever = MagicMock(side_effect=[(), (candidate,)])
    selector = MagicMock(return_value=candidate.label)
    stage_b_classifier = MagicMock(return_value=TechnologyFinanceStageBResult(
        labels=({"match_method": "condition_fallback", "source_row": 88},),
        consistency_status="consistent", consistency_basis="条件/标准命中节能改造项目。",
        consistency_evidence_refs=(), model_output={"validated": True},
    ))

    outcome = classify_five_articles_case(
        session, case, GREEN_FINANCE_REGISTRATION, _settings(),
        stage_a_classifier=lambda session, case, settings: _persist_stage_a(session, case),
        mapping_lookup=MagicMock(return_value=_green_not_applicable_mapping(mapping_version.id)),
        stage_b_classifier=stage_b_classifier,
        condition_candidate_retriever=retriever,
        condition_label_selector=selector,
    )

    assert outcome.stage_b_result is not None
    assert outcome.stage_b_result.status == "completed"
    assert outcome.stage_b_result.labels[0]["match_method"] == "condition_fallback"
    assert [call.args[2] for call in retriever.call_args_list] == ["enterprise", "loan_direction"]
    selector.assert_called_once()
    assert stage_b_classifier.call_args.args[4][0].match_method == "condition_fallback"


@pytest.mark.parametrize("multiple", [False, True], ids=["single", "multiple"])
def test_green_neic_code_matches_keep_existing_selection_path(
    green_workflow_context: tuple[Session, NationalEconomyClassificationCase, FiveArticlesMappingVersion],
    multiple: bool,
) -> None:
    session, case, mapping_version = green_workflow_context
    first = FiveArticlesMappingLabel(
        mapping_version_id=mapping_version.id, scenario_id="green_finance",
        neic_code="2710", code_level=4, neic_name="化学药品原料药制造",
        subject="绿色产业", tier1="节能环保", tier2="节能改造",
        tier3=None, tier4=None, source_row=31,
    )
    candidates = (first,) if not multiple else (
        first,
        replace(first, subject="清洁能源", tier1="清洁能源", source_row=32),
    )
    mapping_result = FiveArticlesMappingLookupResult(
        status="mapping_hit", mapping_version_id=mapping_version.id, mapping_version=1,
        enterprise_labels=(), loan_direction_labels=candidates,
        detail="loan_direction_mapping_hit",
    )
    fallback_retriever = MagicMock()
    label_selector = MagicMock(return_value=candidates[-1])
    stage_b_classifier = MagicMock(return_value=_stage_b_decision())

    outcome = classify_five_articles_case(
        session, case, GREEN_FINANCE_REGISTRATION, _settings(),
        stage_a_classifier=lambda session, case, settings: _persist_stage_a(session, case),
        mapping_lookup=MagicMock(return_value=mapping_result),
        label_selector=label_selector, stage_b_classifier=stage_b_classifier,
        condition_candidate_retriever=fallback_retriever,
    )

    assert outcome.stage_b_result is not None
    assert outcome.stage_b_result.status == "completed"
    fallback_retriever.assert_not_called()
    if multiple:
        label_selector.assert_called_once()
        assert stage_b_classifier.call_args.args[4] == (candidates[-1],)
    else:
        label_selector.assert_not_called()
        assert stage_b_classifier.call_args.args[4] == candidates


@pytest.mark.parametrize(
    ("profile", "multiple"),
    [
        (GREEN_FINANCE_REGISTRATION, False),
        (GREEN_FINANCE_REGISTRATION, True),
        (DIGITAL_FINANCE_REGISTRATION, False),
        (DIGITAL_FINANCE_REGISTRATION, True),
        (PENSION_FINANCE_REGISTRATION, False),
        (PENSION_FINANCE_REGISTRATION, True),
    ],
    ids=lambda value: value.id if isinstance(value, ScenarioRegistration) else (
        "multiple" if value else "single"
    ),
)
def test_non_technology_finance_same_code_merges_labels_without_regression(
    workflow_context: tuple[Session, NationalEconomyClassificationCase, FiveArticlesMappingVersion],
    profile: ScenarioRegistration,
    multiple: bool,
) -> None:
    session, case, mapping_version = workflow_context
    case.scenario = profile.id
    mapping_version.scenario_id = profile.id
    session.commit()

    first = FiveArticlesMappingLabel(
        mapping_version_id=mapping_version.id, scenario_id=profile.id,
        neic_code="2710", code_level=4, neic_name="化学药品原料药制造",
        subject=f"{profile.id}主题一", tier1="一级", tier2="二级",
        tier3=None, tier4=None, source_row=41,
    )
    candidates = (first,) if not multiple else (
        first,
        replace(first, subject=f"{profile.id}主题二", source_row=42),
    )
    mapping_result = FiveArticlesMappingLookupResult(
        status="mapping_hit", mapping_version_id=mapping_version.id, mapping_version=1,
        enterprise_labels=(), loan_direction_labels=candidates,
        detail="loan_direction_mapping_hit",
    )
    label_selector = MagicMock(return_value=candidates[-1])
    stage_b_classifier = MagicMock(return_value=_stage_b_decision())

    outcome = classify_five_articles_case(
        session, case, profile, _settings(),
        stage_a_classifier=lambda session, case, settings: _persist_same_code_stage_a(
            session, case
        ),
        mapping_lookup=MagicMock(return_value=mapping_result),
        label_selector=label_selector,
        stage_b_classifier=stage_b_classifier,
    )

    assert outcome.stage_b_result is not None
    assert outcome.stage_b_result.status == "completed"
    stage_b_classifier.assert_called_once()
    if multiple:
        label_selector.assert_called_once()
        assert label_selector.call_args.args[3] == candidates
        expected_labels = (candidates[-1],)
    else:
        label_selector.assert_not_called()
        expected_labels = candidates
    assert stage_b_classifier.call_args.args[3] == expected_labels
    assert stage_b_classifier.call_args.args[4] == expected_labels


@pytest.mark.parametrize("keyword", ["绿色生产", "绿色经营"])
def test_green_keyword_after_no_condition_match_needs_review(
    green_workflow_context: tuple[Session, NationalEconomyClassificationCase, FiveArticlesMappingVersion],
    keyword: str,
) -> None:
    session, case, mapping_version = green_workflow_context
    case.input_payload = {**case.input_payload, "loan_purpose": f"用于{keyword}项目"}
    session.commit()
    retriever = MagicMock(return_value=())
    stage_b_classifier = MagicMock()

    outcome = classify_five_articles_case(
        session, case, GREEN_FINANCE_REGISTRATION, _settings(),
        stage_a_classifier=lambda session, case, settings: _persist_stage_a(session, case),
        mapping_lookup=MagicMock(return_value=_green_not_applicable_mapping(mapping_version.id)),
        stage_b_classifier=stage_b_classifier,
        condition_candidate_retriever=retriever,
    )

    assert outcome.stage_b_result is not None
    assert outcome.stage_b_result.status == "needs_review"
    assert "已确认属于绿色金融业务范畴" in (outcome.stage_b_result.consistency_basis or "")
    assert "具体分类标签" in (outcome.stage_b_result.consistency_basis or "")
    assert [call.args[2] for call in retriever.call_args_list] == ["enterprise", "loan_direction"]
    stage_b_classifier.assert_not_called()


def test_green_no_keyword_and_enterprise_text_do_not_change_not_applicable(
    green_workflow_context: tuple[Session, NationalEconomyClassificationCase, FiveArticlesMappingVersion],
) -> None:
    session, case, mapping_version = green_workflow_context
    case.input_payload = {**case.input_payload, "core_products_services": "绿色生产设备", "loan_purpose": "普通流动资金"}
    session.commit()
    retriever = MagicMock(return_value=())

    stage_a = _persist_stage_a(session, case)
    outcome = run_five_articles_stage_b(
        session, case, stage_a, GREEN_FINANCE_REGISTRATION, _settings(),
        mapping_lookup=MagicMock(return_value=_green_not_applicable_mapping(mapping_version.id)),
        condition_candidate_retriever=retriever,
    )

    assert outcome.stage_b_result is not None
    assert outcome.stage_b_result.status == "not_applicable"
    assert outcome.stage_b_result.error_detail == "loan_direction_has_no_explicit_mapping"
    assert [call.args[2] for call in retriever.call_args_list] == ["enterprise", "loan_direction"]


@pytest.mark.parametrize(
    "profile",
    [
        TECHNOLOGY_FINANCE_REGISTRATION,
        DIGITAL_FINANCE_REGISTRATION,
        PENSION_FINANCE_REGISTRATION,
    ],
    ids=lambda profile: profile.id,
)
def test_non_green_no_candidate_does_not_invoke_condition_fallback(
    workflow_context: tuple[Session, NationalEconomyClassificationCase, FiveArticlesMappingVersion],
    profile: ScenarioRegistration,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session, case, mapping_version = workflow_context
    registration = profile
    case.scenario = registration.id
    mapping_version.scenario_id = registration.id
    session.commit()
    retriever = MagicMock()
    monkeypatch.setattr(workflow_module, "retrieve_green_finance_condition_candidates", retriever)

    outcome = reclassify_five_articles_case(
        session, case, "请重新判断", registration, _settings(),
        stage_a_reclassifier=lambda session, case, objection, settings: _persist_stage_a(session, case, objection=objection),
        mapping_lookup=MagicMock(return_value=_green_not_applicable_mapping(mapping_version.id)),
    )

    assert outcome.stage_b_result is not None
    assert outcome.stage_b_result.status == "not_applicable"
    retriever.assert_not_called()
