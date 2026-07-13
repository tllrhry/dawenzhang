from collections.abc import Iterator
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
from app.services.technology_finance_classification_workflow import (
    classify_technology_finance_case,
    reclassify_technology_finance_case,
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
        industry_name="工业设备制造" if status == "completed" else None,
        loan_industry_code="2710" if status == "completed" else None,
        loan_industry_major_code="C27" if status == "completed" else None,
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

    label_selector.assert_called_once()
    assert label_selector.call_args.args[2] == candidates
    stage_b_classifier.assert_called_once()
    assert stage_b_classifier.call_args.args[3] == (candidates[1],)
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

    stage_b_classifier.assert_called_once()
    assert stage_b_classifier.call_args.args[2] == (candidates[0],)
    assert stage_b_classifier.call_args.args[3] == (candidates[0],)
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
