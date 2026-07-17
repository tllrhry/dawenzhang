from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models import (
    FiveArticlesMappingVersion,
    FiveArticlesResult,
    NationalEconomyClassificationCase,
    NationalEconomyClassificationResult,
)
from app.services.national_economy_classification_workflow import (
    classify_case,
    reclassify_case,
)
from app.services.green_finance_condition_matching import (
    ConditionSide,
    GreenFinanceConditionCandidate,
    retrieve_green_finance_condition_candidates,
    select_green_finance_condition_label,
)
from app.services.five_articles_policies import get_five_articles_policy
from app.services.five_articles_policies.base import LEGACY_DECISION_POLICY_VERSION
from app.services.five_articles_policies.green import (
    GREEN_FINANCE_DECISION_POLICY_VERSION,
)
from app.services.scenario_registry import (
    ScenarioRegistration,
    TECHNOLOGY_FINANCE_REGISTRATION,
)
from app.services.technology_finance_label_selection import (
    select_most_matching_five_articles_label,
    select_most_matching_technology_finance_label,
)
from app.services.technology_finance_mapping_query import (
    FiveArticlesMappingLabel,
    FiveArticlesMappingLookupResult,
    lookup_five_articles_hierarchy_mapping,
)
from app.services.technology_finance_stage_b import (
    TechnologyFinanceStageBResult,
    classify_five_articles_stage_b,
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
StageBClassificationCallable = Callable[..., TechnologyFinanceStageBResult]
ConditionCandidateRetrievalCallable = Callable[
    [Session, dict[str, object], ConditionSide, Settings],
    tuple[GreenFinanceConditionCandidate, ...],
]
ConditionLabelSelectionCallable = Callable[
    [tuple[GreenFinanceConditionCandidate, ...], str, Settings],
    FiveArticlesMappingLabel | None,
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
    mapping_lookup: MappingLookupCallable = lookup_five_articles_hierarchy_mapping,
    label_selector: LabelSelectionCallable = select_most_matching_technology_finance_label,
    stage_b_classifier: StageBClassificationCallable = classify_technology_finance_stage_b,
) -> TechnologyFinanceWorkflowResult:
    """Compatibility wrapper for the technology-finance workflow profile."""
    return classify_five_articles_case(
        session, case, TECHNOLOGY_FINANCE_REGISTRATION, settings,
        stage_a_classifier=stage_a_classifier,
        mapping_lookup=mapping_lookup,
        label_selector=lambda _profile, *args: label_selector(*args),
        stage_b_classifier=lambda _profile, *args: stage_b_classifier(*args),
    )


def classify_five_articles_case(
    session: Session,
    case: NationalEconomyClassificationCase,
    profile: ScenarioRegistration,
    settings: Settings | None = None,
    *,
    stage_a_classifier: StageAClassificationCallable = classify_case,
    mapping_lookup: MappingLookupCallable = lookup_five_articles_hierarchy_mapping,
    label_selector: LabelSelectionCallable = select_most_matching_five_articles_label,
    stage_b_classifier: StageBClassificationCallable = classify_five_articles_stage_b,
    condition_candidate_retriever: ConditionCandidateRetrievalCallable = retrieve_green_finance_condition_candidates,
    condition_label_selector: ConditionLabelSelectionCallable = select_green_finance_condition_label,
) -> TechnologyFinanceWorkflowResult:
    """Run initial Stage A or retry Stage B within one scenario profile."""
    _validate_case_profile(case, profile)
    resolved_settings = settings or get_settings()
    stage_a_result = _latest_stage_a_result(session, case.id)
    if stage_a_result is None:
        stage_a_result = stage_a_classifier(session, case, resolved_settings)
    return run_five_articles_stage_b(
        session, case, stage_a_result, profile, resolved_settings,
        mapping_lookup=mapping_lookup,
        label_selector=label_selector,
        stage_b_classifier=stage_b_classifier,
        condition_candidate_retriever=condition_candidate_retriever,
        condition_label_selector=condition_label_selector,
    )


def reclassify_technology_finance_case(
    session: Session,
    case: NationalEconomyClassificationCase,
    objection_text: str,
    settings: Settings | None = None,
    *,
    stage_a_reclassifier: StageAReclassificationCallable = reclassify_case,
    mapping_lookup: MappingLookupCallable = lookup_five_articles_hierarchy_mapping,
    label_selector: LabelSelectionCallable = select_most_matching_technology_finance_label,
    stage_b_classifier: StageBClassificationCallable = classify_technology_finance_stage_b,
) -> TechnologyFinanceWorkflowResult:
    """Compatibility wrapper for objection-driven technology-finance reruns."""
    return reclassify_five_articles_case(
        session, case, objection_text, TECHNOLOGY_FINANCE_REGISTRATION, settings,
        stage_a_reclassifier=stage_a_reclassifier,
        mapping_lookup=mapping_lookup,
        label_selector=lambda _profile, *args: label_selector(*args),
        stage_b_classifier=lambda _profile, *args: stage_b_classifier(*args),
    )


def reclassify_five_articles_case(
    session: Session,
    case: NationalEconomyClassificationCase,
    objection_text: str,
    profile: ScenarioRegistration,
    settings: Settings | None = None,
    *,
    stage_a_reclassifier: StageAReclassificationCallable = reclassify_case,
    mapping_lookup: MappingLookupCallable = lookup_five_articles_hierarchy_mapping,
    label_selector: LabelSelectionCallable = select_most_matching_five_articles_label,
    stage_b_classifier: StageBClassificationCallable = classify_five_articles_stage_b,
    condition_candidate_retriever: ConditionCandidateRetrievalCallable = retrieve_green_finance_condition_candidates,
    condition_label_selector: ConditionLabelSelectionCallable = select_green_finance_condition_label,
) -> TechnologyFinanceWorkflowResult:
    """Create a new objection Stage A, then bind a profile-bounded Stage B."""
    _validate_case_profile(case, profile)
    resolved_settings = settings or get_settings()
    stage_a_result = stage_a_reclassifier(session, case, objection_text, resolved_settings)
    return run_five_articles_stage_b(
        session, case, stage_a_result, profile, resolved_settings,
        mapping_lookup=mapping_lookup,
        label_selector=label_selector,
        stage_b_classifier=stage_b_classifier,
        condition_candidate_retriever=condition_candidate_retriever,
        condition_label_selector=condition_label_selector,
    )


def run_technology_finance_stage_b(
    session: Session,
    case: NationalEconomyClassificationCase,
    stage_a_result: NationalEconomyClassificationResult,
    settings: Settings,
    *,
    mapping_lookup: MappingLookupCallable = lookup_five_articles_hierarchy_mapping,
    label_selector: LabelSelectionCallable = select_most_matching_technology_finance_label,
    stage_b_classifier: StageBClassificationCallable = classify_technology_finance_stage_b,
) -> TechnologyFinanceWorkflowResult:
    """Compatibility wrapper for a technology-finance Stage B retry."""
    return run_five_articles_stage_b(
        session, case, stage_a_result, TECHNOLOGY_FINANCE_REGISTRATION, settings,
        mapping_lookup=mapping_lookup,
        label_selector=lambda _profile, *args: label_selector(*args),
        stage_b_classifier=lambda _profile, *args: stage_b_classifier(*args),
    )


def run_five_articles_stage_b(
    session: Session,
    case: NationalEconomyClassificationCase,
    stage_a_result: NationalEconomyClassificationResult,
    profile: ScenarioRegistration,
    settings: Settings,
    *,
    mapping_lookup: MappingLookupCallable = lookup_five_articles_hierarchy_mapping,
    label_selector: LabelSelectionCallable = select_most_matching_five_articles_label,
    stage_b_classifier: StageBClassificationCallable = classify_five_articles_stage_b,
    condition_candidate_retriever: ConditionCandidateRetrievalCallable = retrieve_green_finance_condition_candidates,
    condition_label_selector: ConditionLabelSelectionCallable = select_green_finance_condition_label,
) -> TechnologyFinanceWorkflowResult:
    """Persist an independently committed, profile-bounded Stage B result."""
    _validate_case_profile(case, profile)
    if stage_a_result.case_id != case.id:
        raise ValueError("Stage A result does not belong to the current case")
    if stage_a_result.status != "completed":
        return TechnologyFinanceWorkflowResult(stage_a_result, None)

    mapping_result: FiveArticlesMappingLookupResult | None = None
    decision_policy_version = _decision_policy_version(profile)
    try:
        mapping_result = mapping_lookup(
            session,
            enterprise_industry_code=stage_a_result.industry_code or "",
            enterprise_major_category_code=stage_a_result.industry_major_code or "",
            enterprise_middle_category_code=stage_a_result.industry_middle_code,
            loan_direction_industry_code=stage_a_result.loan_industry_code or "",
            loan_direction_major_category_code=stage_a_result.loan_industry_major_code or "",
            loan_direction_middle_category_code=stage_a_result.loan_industry_middle_code,
            scenario_id=profile.id,
        )
        _validate_mapping_context(session, mapping_result, profile)
        existing_completed = session.scalar(
            select(FiveArticlesResult)
            .where(
                FiveArticlesResult.case_id == case.id,
                FiveArticlesResult.scenario_id == profile.id,
                FiveArticlesResult.stage_a_result_id == stage_a_result.id,
                FiveArticlesResult.mapping_version_id == mapping_result.mapping_version_id,
                FiveArticlesResult.decision_policy_version == decision_policy_version,
                FiveArticlesResult.status == "completed",
            )
            .order_by(FiveArticlesResult.version.desc())
            .limit(1)
        )
        if existing_completed is not None:
            return TechnologyFinanceWorkflowResult(stage_a_result, existing_completed)
        result = _build_stage_b_result(
            session, case, stage_a_result, mapping_result, settings, profile,
            label_selector, stage_b_classifier, condition_candidate_retriever,
            condition_label_selector,
        )
        return TechnologyFinanceWorkflowResult(stage_a_result, _commit_stage_b_result(session, result))
    except Exception as exc:
        session.rollback()
        failed_result = _new_result(
            session, case=case, stage_a_result=stage_a_result,
            status="classification_failed",
            mapping_version_id=_failure_mapping_version_id(session, mapping_result, profile),
            decision_policy_version=decision_policy_version,
            error_detail=str(exc) or exc.__class__.__name__,
        )
        return TechnologyFinanceWorkflowResult(stage_a_result, _commit_stage_b_result(session, failed_result))


def _latest_stage_a_result(session: Session, case_id: int) -> NationalEconomyClassificationResult | None:
    return session.scalar(
        select(NationalEconomyClassificationResult)
        .where(NationalEconomyClassificationResult.case_id == case_id)
        .order_by(NationalEconomyClassificationResult.version.desc(), NationalEconomyClassificationResult.id.desc())
        .limit(1)
    )


def _build_stage_b_result(
    session: Session,
    case: NationalEconomyClassificationCase,
    stage_a_result: NationalEconomyClassificationResult,
    mapping_result: FiveArticlesMappingLookupResult,
    settings: Settings,
    profile: ScenarioRegistration,
    label_selector: LabelSelectionCallable,
    stage_b_classifier: StageBClassificationCallable,
    condition_candidate_retriever: ConditionCandidateRetrievalCallable,
    condition_label_selector: ConditionLabelSelectionCallable,
) -> FiveArticlesResult:
    policy = get_five_articles_policy(profile.id)
    if mapping_result.status == "needs_review":
        return _new_result(
            session, case=case, stage_a_result=stage_a_result, status="needs_review",
            mapping_version_id=mapping_result.mapping_version_id,
            decision_policy_version=_decision_policy_version(profile),
            consistency_status="needs_review",
            consistency_basis=f"{profile.name}映射数据异常，需人工复核。",
            error_detail=mapping_result.detail,
        )

    resolution = policy.resolve_mapping(
        session,
        case.input_payload,
        mapping_result,
        settings,
        condition_candidate_retriever=condition_candidate_retriever,
        condition_label_selector=condition_label_selector,
    )
    mapping_result = resolution.mapping_result
    if mapping_result.status == "not_applicable":
        return _new_result(
            session, case=case, stage_a_result=stage_a_result, status="not_applicable",
            mapping_version_id=mapping_result.mapping_version_id,
            decision_policy_version=_decision_policy_version(profile),
            consistency_status="not_applicable",
            consistency_basis=policy.build_not_applicable_basis(profile, resolution),
            error_detail=(
                resolution.not_applicable_error_detail or mapping_result.detail
            ),
        )

    loan_labels = mapping_result.loan_direction_labels
    enterprise_labels = mapping_result.enterprise_labels
    if len(loan_labels) > 1 and policy.narrows_loan_labels:
        selected = label_selector(profile, case.input_payload, stage_a_result, loan_labels, settings)
        loan_labels = (selected,)
    if stage_a_result.industry_code == stage_a_result.loan_industry_code:
        enterprise_labels = loan_labels
    decision = stage_b_classifier(
        profile, case.input_payload, stage_a_result, enterprise_labels, loan_labels, settings
    )
    labels = policy.postprocess_labels(session, case.input_payload, decision.labels)
    return _new_result(
        session, case=case, stage_a_result=stage_a_result, status=decision.result_status,
        mapping_version_id=mapping_result.mapping_version_id,
        decision_policy_version=_decision_policy_version(profile), labels=labels,
        consistency_status=decision.consistency_status, consistency_basis=decision.consistency_basis,
        consistency_evidence_refs=list(decision.consistency_evidence_refs), model_output=dict(decision.model_output),
    )


def _decision_policy_version(profile: ScenarioRegistration) -> str:
    return get_five_articles_policy(profile.id).decision_policy_version


def _validate_case_profile(case: NationalEconomyClassificationCase, profile: ScenarioRegistration) -> None:
    if not profile.is_executable_profile or case.scenario != profile.id:
        raise ValueError(f"case scenario must match executable profile {profile.id}")


def _validate_mapping_context(
    session: Session, mapping_result: FiveArticlesMappingLookupResult, profile: ScenarioRegistration
) -> None:
    if mapping_result.mapping_version_id is not None:
        version = session.get(FiveArticlesMappingVersion, mapping_result.mapping_version_id)
        if version is None or version.scenario_id != profile.id:
            raise ValueError("mapping version does not belong to the current scenario")
    labels = (*mapping_result.enterprise_labels, *mapping_result.loan_direction_labels)
    if any(label.scenario_id != profile.id for label in labels):
        raise ValueError("mapping labels do not belong to the current scenario")


def _failure_mapping_version_id(
    session: Session, mapping_result: FiveArticlesMappingLookupResult | None, profile: ScenarioRegistration
) -> int | None:
    if mapping_result is None or mapping_result.mapping_version_id is None:
        return None
    version = session.get(FiveArticlesMappingVersion, mapping_result.mapping_version_id)
    return version.id if version is not None and version.scenario_id == profile.id else None


def _new_result(
    session: Session,
    *,
    case: NationalEconomyClassificationCase,
    stage_a_result: NationalEconomyClassificationResult,
    status: str,
    mapping_version_id: int | None,
    decision_policy_version: str = LEGACY_DECISION_POLICY_VERSION,
    labels: list[dict[str, object]] | None = None,
    consistency_status: str | None = None,
    consistency_basis: str | None = None,
    consistency_evidence_refs: list[dict[str, object]] | None = None,
    model_output: dict[str, object] | None = None,
    error_detail: str | None = None,
) -> FiveArticlesResult:
    current_version = session.scalar(select(func.max(FiveArticlesResult.version)).where(FiveArticlesResult.case_id == case.id))
    return FiveArticlesResult(
        case_id=case.id, scenario_id=case.scenario, version=(current_version or 0) + 1,
        status=status, stage_a_result_id=stage_a_result.id, mapping_version_id=mapping_version_id,
        decision_policy_version=decision_policy_version,
        labels=labels or [], loan_neic_code=stage_a_result.loan_industry_code,
        loan_neic_name=stage_a_result.loan_industry_name, enterprise_neic_code=stage_a_result.industry_code,
        enterprise_neic_name=stage_a_result.industry_name, consistency_status=consistency_status,
        consistency_basis=consistency_basis, consistency_evidence_refs=consistency_evidence_refs or [],
        model_output=model_output, error_detail=error_detail,
    )


def _commit_stage_b_result(session: Session, result: FiveArticlesResult) -> FiveArticlesResult:
    session.add(result)
    session.commit()
    session.refresh(result)
    return result
