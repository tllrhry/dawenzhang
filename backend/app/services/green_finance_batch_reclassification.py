"""Batch Stage B refresh for green-finance cases on the current ruleset."""

from dataclasses import dataclass

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import (
    FiveArticlesResult,
    NationalEconomyClassificationCase,
    NationalEconomyClassificationResult,
)
from app.services.green_finance_mapping_maintenance import (
    latest_green_finance_mapping_version,
)
from app.services.scenario_registry import GREEN_FINANCE_REGISTRATION
from app.services.technology_finance_classification_workflow import (
    GREEN_FINANCE_DECISION_POLICY_VERSION,
    run_five_articles_stage_b,
)


_TERMINAL_STATUSES = ("completed", "not_applicable", "needs_review")


@dataclass(frozen=True)
class GreenFinanceReclassificationCandidate:
    case: NationalEconomyClassificationCase
    stage_a_result: NationalEconomyClassificationResult


@dataclass(frozen=True)
class GreenFinanceBatchSummary:
    selected: int
    completed: int
    not_applicable: int
    needs_review: int
    classification_failed: int
    last_case_id: int | None


def list_stale_green_finance_cases(
    session: Session,
    *,
    after_case_id: int = 0,
    limit: int | None = None,
) -> tuple[GreenFinanceReclassificationCandidate, ...]:
    """Return latest completed Stage A rows missing a current-policy Stage B."""
    mapping_version = latest_green_finance_mapping_version(session)
    latest_stage_a_id = (
        select(NationalEconomyClassificationResult.id)
        .where(
            NationalEconomyClassificationResult.case_id
            == NationalEconomyClassificationCase.id
        )
        .order_by(
            NationalEconomyClassificationResult.version.desc(),
            NationalEconomyClassificationResult.id.desc(),
        )
        .limit(1)
        .correlate(NationalEconomyClassificationCase)
        .scalar_subquery()
    )
    current_result_exists = exists(
        select(FiveArticlesResult.id).where(
            FiveArticlesResult.case_id == NationalEconomyClassificationCase.id,
            FiveArticlesResult.stage_a_result_id
            == NationalEconomyClassificationResult.id,
            FiveArticlesResult.mapping_version_id == mapping_version.id,
            FiveArticlesResult.decision_policy_version
            == GREEN_FINANCE_DECISION_POLICY_VERSION,
            FiveArticlesResult.status.in_(_TERMINAL_STATUSES),
        )
    )
    statement = (
        select(
            NationalEconomyClassificationCase,
            NationalEconomyClassificationResult,
        )
        .join(
            NationalEconomyClassificationResult,
            NationalEconomyClassificationResult.id == latest_stage_a_id,
        )
        .where(
            NationalEconomyClassificationCase.scenario
            == GREEN_FINANCE_REGISTRATION.id,
            NationalEconomyClassificationCase.id > after_case_id,
            NationalEconomyClassificationResult.status == "completed",
            ~current_result_exists,
        )
        .order_by(NationalEconomyClassificationCase.id)
    )
    if limit is not None:
        if limit <= 0:
            raise ValueError("limit must be greater than zero")
        statement = statement.limit(limit)
    return tuple(
        GreenFinanceReclassificationCandidate(case=case, stage_a_result=stage_a)
        for case, stage_a in session.execute(statement).all()
    )


def reclassify_stale_green_finance_cases(
    session: Session,
    settings: Settings,
    *,
    after_case_id: int = 0,
    limit: int | None = None,
) -> GreenFinanceBatchSummary:
    candidates = list_stale_green_finance_cases(
        session, after_case_id=after_case_id, limit=limit
    )
    counts = {status: 0 for status in (*_TERMINAL_STATUSES, "classification_failed")}
    last_case_id: int | None = None
    for candidate in candidates:
        outcome = run_five_articles_stage_b(
            session,
            candidate.case,
            candidate.stage_a_result,
            GREEN_FINANCE_REGISTRATION,
            settings,
        )
        if outcome.stage_b_result is None:
            raise RuntimeError(
                f"case {candidate.case.id} has no Stage B result after refresh"
            )
        counts[outcome.stage_b_result.status] += 1
        last_case_id = candidate.case.id

    return GreenFinanceBatchSummary(
        selected=len(candidates),
        completed=counts["completed"],
        not_applicable=counts["not_applicable"],
        needs_review=counts["needs_review"],
        classification_failed=counts["classification_failed"],
        last_case_id=last_case_id,
    )
