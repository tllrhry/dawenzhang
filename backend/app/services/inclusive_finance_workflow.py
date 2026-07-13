from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models import InclusiveFinanceResult, NationalEconomyClassificationCase, NationalEconomyClassificationResult
from app.services.inclusive_finance_determination import determine_inclusive_finance
from app.services.national_economy_classification_workflow import classify_case, reclassify_case

@dataclass(frozen=True)
class InclusiveFinanceWorkflowResult:
    stage_a_result: NationalEconomyClassificationResult
    stage_b_result: InclusiveFinanceResult | None

def classify_inclusive_finance_case(session: Session, case: NationalEconomyClassificationCase, settings: Settings | None = None, *, stage_a_classifier: Callable = classify_case, determiner: Callable = determine_inclusive_finance) -> InclusiveFinanceWorkflowResult:
    stage_a = _latest_stage_a(session, case.id)
    if stage_a is None:
        stage_a = stage_a_classifier(session, case, settings or get_settings())
    return run_inclusive_finance_stage_b(session, case, stage_a, determiner=determiner)

def reclassify_inclusive_finance_case(session: Session, case: NationalEconomyClassificationCase, objection_text: str, settings: Settings | None = None, *, stage_a_reclassifier: Callable = reclassify_case, determiner: Callable = determine_inclusive_finance) -> InclusiveFinanceWorkflowResult:
    stage_a = stage_a_reclassifier(session, case, objection_text, settings or get_settings())
    return run_inclusive_finance_stage_b(session, case, stage_a, determiner=determiner)

def run_inclusive_finance_stage_b(session: Session, case: NationalEconomyClassificationCase, stage_a: NationalEconomyClassificationResult, *, determiner: Callable = determine_inclusive_finance) -> InclusiveFinanceWorkflowResult:
    if stage_a.status != "completed": return InclusiveFinanceWorkflowResult(stage_a, None)
    existing = session.scalar(select(InclusiveFinanceResult).where(InclusiveFinanceResult.case_id == case.id, InclusiveFinanceResult.stage_a_result_id == stage_a.id, InclusiveFinanceResult.status == "completed").order_by(InclusiveFinanceResult.version.desc()).limit(1))
    if existing is not None: return InclusiveFinanceWorkflowResult(stage_a, existing)
    try:
        decision = determiner(case.input_payload, stage_a)
        result = _new_result(session, case, stage_a, **decision)
        session.add(result); session.commit(); session.refresh(result)
        return InclusiveFinanceWorkflowResult(stage_a, result)
    except Exception as exc:
        session.rollback()
        result = _new_result(session, case, stage_a, status="classification_failed", error_detail=str(exc) or exc.__class__.__name__)
        session.add(result); session.commit(); session.refresh(result)
        return InclusiveFinanceWorkflowResult(stage_a, result)

def _latest_stage_a(session: Session, case_id: int) -> NationalEconomyClassificationResult | None:
    return session.scalar(select(NationalEconomyClassificationResult).where(NationalEconomyClassificationResult.case_id == case_id).order_by(NationalEconomyClassificationResult.version.desc(), NationalEconomyClassificationResult.id.desc()).limit(1))

def _new_result(session: Session, case: NationalEconomyClassificationCase, stage_a: NationalEconomyClassificationResult, *, status: str, borrower_type: str | None = None, computed_size: str | None = None, filled_size: str | None = None, is_operating_loan: bool | None = None, credit_amount_wan: float | None = None, qualifies: bool | None = None, inclusive_category: str | None = None, basis: str | None = None, evidence_refs: list[dict[str, object]] | None = None, anomalies: list[dict[str, object]] | None = None, determination: dict[str, object] | None = None, error_detail: str | None = None, **_: object) -> InclusiveFinanceResult:
    version = session.scalar(select(func.max(InclusiveFinanceResult.version)).where(InclusiveFinanceResult.case_id == case.id)) or 0
    size_consistent = determination.get("size_consistent") if determination else None
    return InclusiveFinanceResult(case_id=case.id, scenario_id=case.scenario, version=version + 1, status=status, stage_a_result_id=stage_a.id, borrower_type=borrower_type, computed_size=computed_size, filled_size=filled_size, size_consistent=size_consistent, is_operating_loan=is_operating_loan, credit_amount_wan=credit_amount_wan, qualifies=qualifies, inclusive_category=inclusive_category, basis=basis, evidence_refs=evidence_refs or [], anomalies=anomalies or [], determination=determination, error_detail=error_detail)
