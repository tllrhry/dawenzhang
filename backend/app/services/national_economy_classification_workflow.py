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
from app.services.national_economy_case_ingestion import FIELD_LABELS
from app.services.national_economy_decision_policy import (
    EvidenceFact,
    EvidenceLayer,
    EvidenceLevel,
    supplement_layer_with_objection,
)
from app.services.national_economy_retrieval import (
    EvidenceSnapshot,
    retrieve_industry_evidence,
)


COMPLETED_CASE_STATUS = "completed"
NEEDS_REVIEW_CASE_STATUS = "needs_review"
FAILED_CASE_STATUS = "classification_failed"

_EVIDENCE_FIELDS = (
    (
        EvidenceLevel.MAIN_BUSINESS_REVENUE,
        ("main_business", "main_business_revenue_share", "core_products_services"),
    ),
    (
        EvidenceLevel.TRADE_AND_INDUSTRY_CHAIN,
        (
            "trade_goods_services",
            "counterparty_business_industry",
            "industry_chain_position",
            "industry_position_competitiveness",
        ),
    ),
    (
        EvidenceLevel.LOAN_PURPOSE,
        ("loan_purpose", "credit_approval_opinion"),
    ),
    (EvidenceLevel.BUSINESS_SCOPE, ("business_scope",)),
)

RetrievalCallable = Callable[
    [Session, Sequence[EvidenceLayer], Settings], Sequence[EvidenceSnapshot]
]
ClassificationCallable = Callable[
    [
        Sequence[EvidenceLayer],
        Sequence[EvidenceSnapshot],
        Settings,
        Mapping[str, object] | None,
    ],
    ConstrainedClassificationResult,
]


def build_classification_query(
    input_payload: Mapping[str, object],
    objection_text: str | None = None,
) -> tuple[EvidenceLayer, ...]:
    layers = tuple(
        _build_evidence_layer(input_payload, level, fields)
        for level, fields in _EVIDENCE_FIELDS
    )
    normalized_objection = (objection_text or "").strip()
    if normalized_objection:
        target_index = next(
            (index for index, layer in enumerate(layers) if layer.is_available),
            0,
        )
        layers = tuple(
            supplement_layer_with_objection(
                layer,
                field_label="异议说明",
                raw_text=normalized_objection,
                indicated_business=normalized_objection,
            )
            if index == target_index
            else layer
            for index, layer in enumerate(layers)
        )
    if not any(layer.is_available for layer in layers):
        raise ValueError("classification query has no usable enterprise information")
    return layers


def _build_evidence_layer(
    input_payload: Mapping[str, object],
    level: EvidenceLevel,
    fields: Sequence[str],
) -> EvidenceLayer:
    facts = tuple(
        EvidenceFact(
            field_label=FIELD_LABELS[field],
            raw_text=value,
            indicated_business=value,
        )
        for field in fields
        if (value := _field_text(input_payload.get(field)))
    )
    return EvidenceLayer(
        level=level,
        facts=facts,
        unavailable_reason=None if facts else "该证据层没有可用输入字段",
    )


def _field_text(value: object) -> str:
    return "" if value is None else str(value).strip()


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
    evidence_layers = build_classification_query(case.input_payload, objection_text)
    try:
        candidates = tuple(retrieval(session, evidence_layers, settings))
        classification = classifier(evidence_layers, candidates, settings, objection)
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
