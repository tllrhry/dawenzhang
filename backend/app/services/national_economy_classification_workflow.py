from collections.abc import Callable, Mapping, Sequence

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models import (
    NationalEconomyClassificationCase,
    NationalEconomyClassificationResult,
)
from app.services.national_economy_classification import (
    ConstrainedClassificationResult,
    classify_national_economy,
)
from app.services.national_economy_retrieval import (
    EvidenceSnapshot,
    retrieve_industry_evidence,
)


COMPLETED_CASE_STATUS = "completed"
NEEDS_REVIEW_CASE_STATUS = "needs_review"
FAILED_CASE_STATUS = "classification_failed"

_QUERY_FIELDS = (
    ("主营业务", "main_business"),
    ("核心产品 / 服务", "core_products_services"),
    ("营业执照经营范围", "business_scope"),
    ("贷款用途", "loan_purpose"),
)

RetrievalCallable = Callable[
    [Session, str, Settings], Sequence[EvidenceSnapshot]
]
ClassificationCallable = Callable[
    [
        Mapping[str, object],
        Sequence[EvidenceSnapshot],
        Settings,
        Mapping[str, object] | None,
    ],
    ConstrainedClassificationResult,
]


def build_classification_query(
    input_payload: Mapping[str, object],
    objection_text: str | None = None,
) -> str:
    parts = []
    for label, field in _QUERY_FIELDS:
        value = str(input_payload.get(field, "")).strip()
        if value:
            parts.append(f"{label}：{value}")
    if objection_text is not None:
        normalized_objection = objection_text.strip()
        if normalized_objection:
            parts.append(f"异议说明：{normalized_objection}")
    if not parts:
        raise ValueError("classification query has no usable enterprise information")
    return "\n".join(parts)


def classify_case(
    session: Session,
    case: NationalEconomyClassificationCase,
    settings: Settings | None = None,
    *,
    retrieval: RetrievalCallable = retrieve_industry_evidence,
    classifier: ClassificationCallable = classify_national_economy,
) -> NationalEconomyClassificationResult:
    return _run_classification(
        session,
        case,
        settings or get_settings(),
        objection=None,
        retrieval=retrieval,
        classifier=classifier,
    )


def reclassify_case(
    session: Session,
    case: NationalEconomyClassificationCase,
    objection_text: str,
    settings: Settings | None = None,
    *,
    retrieval: RetrievalCallable = retrieve_industry_evidence,
    classifier: ClassificationCallable = classify_national_economy,
) -> NationalEconomyClassificationResult:
    normalized_objection = objection_text.strip()
    if not normalized_objection:
        raise ValueError("objection must not be blank")
    return _run_classification(
        session,
        case,
        settings or get_settings(),
        objection={"description": normalized_objection},
        retrieval=retrieval,
        classifier=classifier,
    )


def get_current_completed_result(
    case: NationalEconomyClassificationCase,
) -> NationalEconomyClassificationResult | None:
    completed_results = (
        result for result in case.result_versions if result.status == "completed"
    )
    return max(completed_results, key=lambda result: result.version, default=None)


def _run_classification(
    session: Session,
    case: NationalEconomyClassificationCase,
    settings: Settings,
    *,
    objection: Mapping[str, object] | None,
    retrieval: RetrievalCallable,
    classifier: ClassificationCallable,
) -> NationalEconomyClassificationResult:
    objection_text = None if objection is None else str(objection["description"])
    query = build_classification_query(case.input_payload, objection_text)
    try:
        candidates = tuple(retrieval(session, query, settings))
        classification = classifier(case.input_payload, candidates, settings, objection)
        result = _build_result(case, classification, objection)
        session.add(result)
        case.status = (
            COMPLETED_CASE_STATUS
            if classification.status == "completed"
            else NEEDS_REVIEW_CASE_STATUS
        )
        session.commit()
        session.refresh(result)
        return result
    except Exception:
        session.rollback()
        case.status = FAILED_CASE_STATUS
        session.add(case)
        session.commit()
        raise


def _build_result(
    case: NationalEconomyClassificationCase,
    classification: ConstrainedClassificationResult,
    objection: Mapping[str, object] | None,
) -> NationalEconomyClassificationResult:
    next_version = max(
        (result.version for result in case.result_versions),
        default=0,
    ) + 1
    return NationalEconomyClassificationResult(
        case=case,
        version=next_version,
        status=classification.status,
        industry_code=classification.industry_code,
        industry_name=classification.industry_name,
        confidence=(
            round(classification.confidence)
            if classification.confidence is not None
            else None
        ),
        rationale=classification.matching_basis,
        ai_summary=classification.summary,
        candidate_snapshot=list(classification.candidate_snapshot),
        objection=dict(objection) if objection is not None else None,
        model_output=dict(classification.model_output),
    )
