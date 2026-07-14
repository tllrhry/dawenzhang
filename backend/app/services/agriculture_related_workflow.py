from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models import (
    AgricultureRelatedResult,
    NationalEconomyClassificationCase,
    NationalEconomyClassificationResult,
)
from app.services.agriculture_related_determination import determine_agriculture_related
from app.services.national_economy_classification_workflow import classify_case, reclassify_case


@dataclass(frozen=True)
class AgricultureRelatedWorkflowResult:
    stage_a_result: NationalEconomyClassificationResult
    stage_b_result: AgricultureRelatedResult | None


def classify_agriculture_related_case(
    session: Session,
    case: NationalEconomyClassificationCase,
    settings: Settings | None = None,
    *,
    stage_a_classifier: Callable = classify_case,
    determiner: Callable = determine_agriculture_related,
) -> AgricultureRelatedWorkflowResult:
    stage_a = _latest_stage_a(session, case.id)
    if stage_a is None:
        stage_a = stage_a_classifier(session, case, settings or get_settings())
    return run_agriculture_related_stage_b(
        session, case, stage_a, settings=settings, determiner=determiner
    )


def reclassify_agriculture_related_case(
    session: Session,
    case: NationalEconomyClassificationCase,
    objection_text: str,
    settings: Settings | None = None,
    *,
    stage_a_reclassifier: Callable = reclassify_case,
    determiner: Callable = determine_agriculture_related,
) -> AgricultureRelatedWorkflowResult:
    stage_a = stage_a_reclassifier(
        session, case, objection_text, settings or get_settings()
    )
    return run_agriculture_related_stage_b(
        session, case, stage_a, settings=settings, determiner=determiner
    )


def run_agriculture_related_stage_b(
    session: Session,
    case: NationalEconomyClassificationCase,
    stage_a: NationalEconomyClassificationResult,
    settings: Settings | None = None,
    *,
    determiner: Callable = determine_agriculture_related,
) -> AgricultureRelatedWorkflowResult:
    if stage_a.status != "completed":
        return AgricultureRelatedWorkflowResult(stage_a, None)

    existing = session.scalar(
        select(AgricultureRelatedResult)
        .where(
            AgricultureRelatedResult.case_id == case.id,
            AgricultureRelatedResult.stage_a_result_id == stage_a.id,
            AgricultureRelatedResult.status == "completed",
        )
        .order_by(AgricultureRelatedResult.version.desc())
        .limit(1)
    )
    if existing is not None:
        return AgricultureRelatedWorkflowResult(stage_a, existing)

    try:
        decision = determiner(
            case.input_payload, stage_a, settings or get_settings()
        )
        result = _new_result(session, case, stage_a, **decision)
        session.add(result)
        session.commit()
        session.refresh(result)
        return AgricultureRelatedWorkflowResult(stage_a, result)
    except Exception as exc:
        session.rollback()
        result = _new_result(
            session,
            case,
            stage_a,
            status="classification_failed",
            error_detail=str(exc) or exc.__class__.__name__,
        )
        session.add(result)
        session.commit()
        session.refresh(result)
        return AgricultureRelatedWorkflowResult(stage_a, result)


def _latest_stage_a(
    session: Session, case_id: int
) -> NationalEconomyClassificationResult | None:
    return session.scalar(
        select(NationalEconomyClassificationResult)
        .where(NationalEconomyClassificationResult.case_id == case_id)
        .order_by(
            NationalEconomyClassificationResult.version.desc(),
            NationalEconomyClassificationResult.id.desc(),
        )
        .limit(1)
    )


def _new_result(
    session: Session,
    case: NationalEconomyClassificationCase,
    stage_a: NationalEconomyClassificationResult,
    *,
    status: str,
    is_agriculture_related: bool | None = None,
    matched_categories: list[dict[str, object]] | None = None,
    basis: str | None = None,
    evidence_refs: list[dict[str, object]] | None = None,
    model_output: dict[str, object] | None = None,
    error_detail: str | None = None,
    **_: object,
) -> AgricultureRelatedResult:
    version = session.scalar(
        select(func.max(AgricultureRelatedResult.version)).where(
            AgricultureRelatedResult.case_id == case.id
        )
    ) or 0
    return AgricultureRelatedResult(
        case_id=case.id,
        scenario_id=case.scenario,
        version=version + 1,
        status=status,
        stage_a_result_id=stage_a.id,
        is_agriculture_related=is_agriculture_related,
        matched_categories=matched_categories or [],
        basis=basis,
        evidence_refs=evidence_refs or [],
        model_output=model_output,
        error_detail=error_detail,
    )
