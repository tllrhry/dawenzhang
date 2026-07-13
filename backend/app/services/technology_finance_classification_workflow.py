from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models import (
    FiveArticlesResult,
    NationalEconomyClassificationCase,
    NationalEconomyClassificationResult,
)
from app.services.national_economy_classification_workflow import (
    classify_case,
    reclassify_case,
)
from app.services.technology_finance_label_selection import (
    select_most_matching_technology_finance_label,
)
from app.services.technology_finance_mapping_query import (
    FiveArticlesMappingLabel,
    FiveArticlesMappingLookupResult,
    lookup_five_articles_mapping,
)
from app.services.technology_finance_stage_b import (
    TechnologyFinanceStageBResult,
    classify_technology_finance_stage_b,
)


StageAClassificationCallable = Callable[
    [Session, NationalEconomyClassificationCase, Settings],
    NationalEconomyClassificationResult,
]
StageAReclassificationCallable = Callable[
    [Session, NationalEconomyClassificationCase, str, Settings],
    NationalEconomyClassificationResult,
]
MappingLookupCallable = Callable[..., FiveArticlesMappingLookupResult]
LabelSelectionCallable = Callable[..., FiveArticlesMappingLabel]
StageBClassificationCallable = Callable[
    ...,
    TechnologyFinanceStageBResult,
]


@dataclass(frozen=True)
class TechnologyFinanceWorkflowResult:
    stage_a_result: NationalEconomyClassificationResult
    stage_b_result: FiveArticlesResult | None


def classify_technology_finance_case(
    session: Session,
    case: NationalEconomyClassificationCase,
    settings: Settings | None = None,
    *,
    stage_a_classifier: StageAClassificationCallable = classify_case,
    mapping_lookup: MappingLookupCallable = lookup_five_articles_mapping,
    label_selector: LabelSelectionCallable = (
        select_most_matching_technology_finance_label
    ),
    stage_b_classifier: StageBClassificationCallable = (
        classify_technology_finance_stage_b
    ),
) -> TechnologyFinanceWorkflowResult:
    """Run initial Stage A or retry Stage B against the latest persisted Stage A."""
    resolved_settings = settings or get_settings()
    stage_a_result = _latest_stage_a_result(session, case.id)
    if stage_a_result is None:
        # classify_case owns and commits the Stage A transaction boundary.
        stage_a_result = stage_a_classifier(session, case, resolved_settings)
    return run_technology_finance_stage_b(
        session,
        case,
        stage_a_result,
        resolved_settings,
        mapping_lookup=mapping_lookup,
        label_selector=label_selector,
        stage_b_classifier=stage_b_classifier,
    )


def reclassify_technology_finance_case(
    session: Session,
    case: NationalEconomyClassificationCase,
    objection_text: str,
    settings: Settings | None = None,
    *,
    stage_a_reclassifier: StageAReclassificationCallable = reclassify_case,
    mapping_lookup: MappingLookupCallable = lookup_five_articles_mapping,
    label_selector: LabelSelectionCallable = (
        select_most_matching_technology_finance_label
    ),
    stage_b_classifier: StageBClassificationCallable = (
        classify_technology_finance_stage_b
    ),
) -> TechnologyFinanceWorkflowResult:
    """Create a new objection-driven Stage A, then bind a new Stage B to it."""
    resolved_settings = settings or get_settings()
    # reclassify_case validates the objection and commits Stage A independently.
    stage_a_result = stage_a_reclassifier(
        session,
        case,
        objection_text,
        resolved_settings,
    )
    return run_technology_finance_stage_b(
        session,
        case,
        stage_a_result,
        resolved_settings,
        mapping_lookup=mapping_lookup,
        label_selector=label_selector,
        stage_b_classifier=stage_b_classifier,
    )


def run_technology_finance_stage_b(
    session: Session,
    case: NationalEconomyClassificationCase,
    stage_a_result: NationalEconomyClassificationResult,
    settings: Settings,
    *,
    mapping_lookup: MappingLookupCallable = lookup_five_articles_mapping,
    label_selector: LabelSelectionCallable = (
        select_most_matching_technology_finance_label
    ),
    stage_b_classifier: StageBClassificationCallable = (
        classify_technology_finance_stage_b
    ),
) -> TechnologyFinanceWorkflowResult:
    """Persist an independently committed Stage B bound to one Stage A result."""
    if stage_a_result.status != "completed":
        return TechnologyFinanceWorkflowResult(stage_a_result, None)

    existing_completed = session.scalar(
        select(FiveArticlesResult)
        .where(
            FiveArticlesResult.case_id == case.id,
            FiveArticlesResult.stage_a_result_id == stage_a_result.id,
            FiveArticlesResult.status == "completed",
        )
        .order_by(FiveArticlesResult.version.desc())
        .limit(1)
    )
    if existing_completed is not None:
        return TechnologyFinanceWorkflowResult(stage_a_result, existing_completed)

    mapping_result: FiveArticlesMappingLookupResult | None = None
    try:
        mapping_result = mapping_lookup(
            session,
            enterprise_four_digit_code=stage_a_result.industry_code or "",
            enterprise_major_category_code=stage_a_result.industry_major_code or "",
            loan_direction_four_digit_code=stage_a_result.loan_industry_code or "",
            loan_direction_major_category_code=(
                stage_a_result.loan_industry_major_code or ""
            ),
            scenario_id=case.scenario,
        )
        stage_b_result = _build_stage_b_result(
            session,
            case,
            stage_a_result,
            mapping_result,
            settings,
            label_selector,
            stage_b_classifier,
        )
        return TechnologyFinanceWorkflowResult(
            stage_a_result,
            _commit_stage_b_result(session, stage_b_result),
        )
    except Exception as exc:
        # Stage A was already committed by its own workflow. Roll back only the
        # current Stage B attempt, then persist a separate failure version.
        session.rollback()
        failed_result = _new_result(
            session,
            case=case,
            stage_a_result=stage_a_result,
            status="classification_failed",
            mapping_version_id=(
                None if mapping_result is None else mapping_result.mapping_version_id
            ),
            error_detail=str(exc) or exc.__class__.__name__,
        )
        return TechnologyFinanceWorkflowResult(
            stage_a_result,
            _commit_stage_b_result(session, failed_result),
        )


def _latest_stage_a_result(
    session: Session,
    case_id: int,
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


def _build_stage_b_result(
    session: Session,
    case: NationalEconomyClassificationCase,
    stage_a_result: NationalEconomyClassificationResult,
    mapping_result: FiveArticlesMappingLookupResult,
    settings: Settings,
    label_selector: LabelSelectionCallable,
    stage_b_classifier: StageBClassificationCallable,
) -> FiveArticlesResult:
    if mapping_result.status == "not_applicable":
        return _new_result(
            session,
            case=case,
            stage_a_result=stage_a_result,
            status="not_applicable",
            mapping_version_id=mapping_result.mapping_version_id,
            consistency_status="not_applicable",
            consistency_basis=(
                "贷款投向未命中已发布科技金融映射，科技金融一致性判定不适用。"
            ),
            error_detail=mapping_result.detail,
        )
    if mapping_result.status == "needs_review":
        return _new_result(
            session,
            case=case,
            stage_a_result=stage_a_result,
            status="needs_review",
            mapping_version_id=mapping_result.mapping_version_id,
            consistency_status="needs_review",
            consistency_basis="科技金融映射数据异常，需人工复核。",
            error_detail=mapping_result.detail,
        )

    loan_direction_labels = mapping_result.loan_direction_labels
    enterprise_labels = mapping_result.enterprise_labels
    if len(loan_direction_labels) > 1:
        # Deterministic mapping may hit multiple independent subjects for the
        # same code; narrow to the single most-matching one before Stage B.
        selected_label = label_selector(
            case.input_payload,
            stage_a_result,
            loan_direction_labels,
            settings,
        )
        loan_direction_labels = (selected_label,)
        if stage_a_result.industry_code == stage_a_result.loan_industry_code:
            # Same-code Stage B requires enterprise and loan label sets to be
            # identical; the enterprise side collapses to the same winner.
            enterprise_labels = loan_direction_labels

    decision = stage_b_classifier(
        case.input_payload,
        stage_a_result,
        enterprise_labels,
        loan_direction_labels,
        settings,
    )
    return _new_result(
        session,
        case=case,
        stage_a_result=stage_a_result,
        status="completed",
        mapping_version_id=mapping_result.mapping_version_id,
        labels=list(decision.labels),
        consistency_status=decision.consistency_status,
        consistency_basis=decision.consistency_basis,
        consistency_evidence_refs=list(decision.consistency_evidence_refs),
        model_output=dict(decision.model_output),
    )


def _new_result(
    session: Session,
    *,
    case: NationalEconomyClassificationCase,
    stage_a_result: NationalEconomyClassificationResult,
    status: str,
    mapping_version_id: int | None,
    labels: list[dict[str, object]] | None = None,
    consistency_status: str | None = None,
    consistency_basis: str | None = None,
    consistency_evidence_refs: list[dict[str, object]] | None = None,
    model_output: dict[str, object] | None = None,
    error_detail: str | None = None,
) -> FiveArticlesResult:
    current_version = session.scalar(
        select(func.max(FiveArticlesResult.version)).where(
            FiveArticlesResult.case_id == case.id
        )
    )
    return FiveArticlesResult(
        case_id=case.id,
        scenario_id=case.scenario,
        version=(current_version or 0) + 1,
        status=status,
        stage_a_result_id=stage_a_result.id,
        mapping_version_id=mapping_version_id,
        labels=labels or [],
        loan_neic_code=stage_a_result.loan_industry_code,
        loan_neic_name=stage_a_result.loan_industry_name,
        enterprise_neic_code=stage_a_result.industry_code,
        enterprise_neic_name=stage_a_result.industry_name,
        consistency_status=consistency_status,
        consistency_basis=consistency_basis,
        consistency_evidence_refs=consistency_evidence_refs or [],
        model_output=model_output,
        error_detail=error_detail,
    )


def _commit_stage_b_result(
    session: Session,
    result: FiveArticlesResult,
) -> FiveArticlesResult:
    session.add(result)
    session.commit()
    session.refresh(result)
    return result
