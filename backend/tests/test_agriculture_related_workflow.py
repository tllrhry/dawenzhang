from collections.abc import Iterator
from unittest.mock import MagicMock

import pytest
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.db.session import get_sessionmaker
from app.models import (
    AgricultureRelatedResult,
    NationalEconomyClassificationCase,
    NationalEconomyClassificationResult,
)
from app.services.agriculture_related_workflow import (
    classify_agriculture_related_case,
    reclassify_agriculture_related_case,
    run_agriculture_related_stage_b,
)


@pytest.fixture()
def workflow_context() -> Iterator[tuple[Session, NationalEconomyClassificationCase]]:
    session = get_sessionmaker()()
    case = NationalEconomyClassificationCase(
        scenario="agriculture_related",
        original_filename="agriculture.docx",
        input_payload={"enterprise_name": "涉农工作流测试企业"},
        status="pending_classification",
    )
    session.add(case)
    session.commit()
    try:
        yield session, case
    finally:
        session.rollback()
        persisted = session.get(NationalEconomyClassificationCase, case.id)
        if persisted is not None:
            session.delete(persisted)
            session.commit()
        session.close()


def _stage_a(
    session: Session,
    case: NationalEconomyClassificationCase,
    *,
    version: int,
    status: str = "completed",
) -> NationalEconomyClassificationResult:
    result = NationalEconomyClassificationResult(
        case_id=case.id,
        version=version,
        status=status,
        candidate_snapshot=[],
        model_output={"stage": "a"},
    )
    session.add(result)
    case.status = status
    session.commit()
    session.refresh(result)
    return result


def _decision(status: str = "not_applicable") -> dict[str, object]:
    return {
        "status": status,
        "is_agriculture_related": status == "completed",
        "matched_categories": [],
        "basis": "workflow test",
        "evidence_refs": [],
        "model_output": None,
    }


def test_incomplete_stage_a_short_circuits_without_agriculture_result(
    workflow_context: tuple[Session, NationalEconomyClassificationCase],
) -> None:
    session, case = workflow_context
    stage_a = _stage_a(session, case, version=1, status="needs_review")
    determiner = MagicMock()

    outcome = run_agriculture_related_stage_b(session, case, stage_a, determiner=determiner)

    assert outcome.stage_a_result.id == stage_a.id
    assert outcome.stage_b_result is None
    assert determiner.call_count == 0
    assert session.scalar(select(func.count(AgricultureRelatedResult.id)).where(
        AgricultureRelatedResult.case_id == case.id
    )) == 0


def test_stage_b_failure_rolls_back_and_preserves_stage_a(
    workflow_context: tuple[Session, NationalEconomyClassificationCase],
) -> None:
    session, case = workflow_context
    stage_a = _stage_a(session, case, version=1)

    outcome = run_agriculture_related_stage_b(
        session, case, stage_a, determiner=MagicMock(side_effect=RuntimeError("AI failed"))
    )

    assert outcome.stage_b_result is not None
    assert outcome.stage_b_result.status == "classification_failed"
    assert outcome.stage_b_result.error_detail == "AI failed"
    assert session.get(NationalEconomyClassificationResult, stage_a.id) is not None


def test_retry_reuses_stage_a_and_completed_result_is_idempotent(
    workflow_context: tuple[Session, NationalEconomyClassificationCase],
) -> None:
    session, case = workflow_context
    stage_a = _stage_a(session, case, version=1)
    first = run_agriculture_related_stage_b(
        session, case, stage_a, determiner=MagicMock(return_value=_decision("completed"))
    )
    duplicate_determiner = MagicMock(return_value=_decision("completed"))
    duplicate = run_agriculture_related_stage_b(
        session, case, stage_a, determiner=duplicate_determiner
    )

    assert first.stage_b_result is not None
    assert duplicate.stage_b_result is not None
    assert duplicate.stage_b_result.id == first.stage_b_result.id
    assert duplicate_determiner.call_count == 0
    assert session.scalar(select(func.count(NationalEconomyClassificationResult.id)).where(
        NationalEconomyClassificationResult.case_id == case.id
    )) == 1
    assert session.scalar(select(func.count(AgricultureRelatedResult.id)).where(
        AgricultureRelatedResult.case_id == case.id
    )) == 1


def test_objection_creates_new_stage_a_and_stage_b_versions(
    workflow_context: tuple[Session, NationalEconomyClassificationCase],
) -> None:
    session, case = workflow_context
    first_stage_a = _stage_a(session, case, version=1)
    first = run_agriculture_related_stage_b(
        session, case, first_stage_a, determiner=MagicMock(return_value=_decision())
    )
    second_stage_a = _stage_a(session, case, version=2)
    stage_a_reclassifier = MagicMock(return_value=second_stage_a)

    objection = reclassify_agriculture_related_case(
        session,
        case,
        "异议：贷款投向发生变化",
        stage_a_reclassifier=stage_a_reclassifier,
        determiner=MagicMock(return_value=_decision("completed")),
    )

    assert first.stage_b_result is not None
    assert objection.stage_a_result.id == second_stage_a.id
    assert objection.stage_b_result is not None
    assert objection.stage_b_result.version == first.stage_b_result.version + 1
    assert objection.stage_b_result.stage_a_result_id == second_stage_a.id
    stage_a_reclassifier.assert_called_once()
