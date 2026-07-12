import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

import httpx

from app.core.config import Settings
from app.services.national_economy_decision_policy import EvidenceLayer, EvidenceLevel
from app.services.national_economy_retrieval import EvidenceSnapshot


ClassificationStatus = Literal["completed", "needs_review"]
LoanSpecificity = Literal["generic", "specific"]
_ENTERPRISE_SUCCESS_OUTPUT_FIELDS = frozenset(
    {"no_match", "industry_code", "industry_name", "matching_basis"}
)
_ENTERPRISE_NO_MATCH_OUTPUT_FIELDS = frozenset({"no_match", "reason"})
_LOAN_SUCCESS_OUTPUT_FIELDS = frozenset(
    {
        "no_match",
        "industry_code",
        "industry_name",
        "matching_basis",
        "specificity",
    }
)
_LOAN_NO_MATCH_OUTPUT_FIELDS = frozenset({"no_match", "reason", "specificity"})
_DUAL_OUTPUT_FIELDS = frozenset({"enterprise", "loan_direction"})


class NationalEconomyClassificationError(RuntimeError):
    """Raised when DeepSeek cannot produce a valid constrained classification."""


@dataclass(frozen=True)
class ConstrainedClassificationResult:
    status: ClassificationStatus
    industry_code: str | None
    industry_name: str | None
    confidence: float | None
    matching_basis: str
    summary: str | None
    candidate_snapshot: tuple[dict[str, object], ...]
    objection: dict[str, object] | None
    model_output: dict[str, object]
    loan_industry_code: str | None = None
    loan_industry_name: str | None = None
    loan_matching_basis: str | None = None
    loan_specificity: LoanSpecificity | None = None
    loan_matches_enterprise: bool | None = None


def classify_national_economy(
    evidence_layers: Sequence[EvidenceLayer],
    candidates: Sequence[EvidenceSnapshot],
    settings: Settings,
    objection: Mapping[str, object] | None = None,
    client: httpx.Client | None = None,
    loan_direction_candidates: Sequence[EvidenceSnapshot] = (),
) -> ConstrainedClassificationResult:
    if not candidates:
        raise ValueError("at least one industry candidate is required")
    if not settings.deepseek_api_key:
        raise NationalEconomyClassificationError(
            "DEEPSEEK_API_KEY is required for classification"
        )

    candidate_snapshot = tuple(_serialize_candidate(candidate) for candidate in candidates)
    loan_direction_candidate_snapshot = tuple(
        _serialize_candidate(candidate) for candidate in loan_direction_candidates
    )
    request_payload = _build_request_payload(
        evidence_layers,
        candidate_snapshot,
        loan_direction_candidate_snapshot,
        settings.deepseek_model,
        objection,
    )
    owns_client = client is None
    http_client = client or httpx.Client(
        base_url=settings.deepseek_base_url.rstrip("/"),
        timeout=httpx.Timeout(
            settings.deepseek_timeout_seconds,
            connect=settings.http_connect_timeout_seconds,
        ),
    )
    try:
        response = http_client.post(
            "/chat/completions",
            headers={"Authorization": f"Bearer {settings.deepseek_api_key}"},
            json=request_payload,
        )
        response.raise_for_status()
        return _validate_model_response(
            response.json(),
            candidates,
            loan_direction_candidates,
            candidate_snapshot,
            objection,
        )
    except (httpx.HTTPError, json.JSONDecodeError, TypeError, ValueError, KeyError) as exc:
        raise NationalEconomyClassificationError(
            f"DeepSeek classification failed: {exc}"
        ) from exc
    finally:
        if owns_client:
            http_client.close()


def _build_request_payload(
    evidence_layers: Sequence[EvidenceLayer],
    candidate_snapshot: Sequence[dict[str, object]],
    loan_direction_candidate_snapshot: Sequence[dict[str, object]],
    model: str,
    objection: Mapping[str, object] | None,
) -> dict[str, object]:
    ordered_layers = tuple(sorted(evidence_layers, key=lambda layer: layer.level))
    dominant_main_business = next(
        (
            fact.indicated_business.strip()
            for layer in ordered_layers
            if layer.level is EvidenceLevel.MAIN_BUSINESS_REVENUE
            for fact in layer.usable_facts
            if fact.field_label == "主营业务及营收占比（主导主营）"
        ),
        None,
    )
    prompt_input: dict[str, object] = {
        "dominant_main_business": dominant_main_business,
        "ordered_evidence": [
            _serialize_evidence_layer(layer) for layer in ordered_layers
        ],
        "enterprise_candidates": list(candidate_snapshot),
        "loan_direction_candidates": list(loan_direction_candidate_snapshot),
    }
    if objection is not None:
        prompt_input["objection"] = dict(objection)
    return {
        "model": model,
        "response_format": {"type": "json_object"},
        "temperature": 0,
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是 GB/T 4754-2017 国民经济行业分类器。只能依据企业输入、"
                    "异议（如有）和两组给定候选的定义/命中片段作答，不得使用或声称使用"
                    "候选外目录、企业清单、涉农规则或其他标签。企业证据已按 priority=1"
                    "到 4 排序：主营业务及营收、贸易合同及产业链、贷款用途、营业执照"
                    "经营范围。必须采用最高可用层；低层冲突不得推翻高层，只有高层不可用"
                    "才可降级，并须在 matching_basis 说明采用层级、字段标签、目录片段及"
                    "冲突或降级理由。异议已并入 ordered_evidence 的既有层，不是第五级。"
                    "当 dominant_main_business 非空时，表示原文存在单项占比不低于50%的"
                    "唯一主导主营：企业结论必须落在该主导主营对应的四级行业，绝对不得因"
                    "核心产品/服务中的其他条目或更低占比业务线改判；该锁定只约束企业结论。"
                    "当 dominant_main_business 为空时，不存在主导主营锁定，企业结论继续按"
                    "上述四级证据优先级综合判定，既有行为不变。"
                    "贷款投向必须按以下决策树判定：一、贷款用途为空或仅为经营周转、"
                    "流动资金、经营使用等未指向具体经营领域的笼统表述，返回"
                    "specificity=generic，投向代码和名称必须回落为企业结论；二、具体用途"
                    "命中主营，返回 specificity=specific，投向仍为企业结论；三、具体用途"
                    "不在主营但在营业执照经营范围内，从给定候选中选择该实际投向；四、"
                    "具体用途既不在主营也不在经营范围，贷款投向返回 no_match=true 及非空"
                    "reason，不得臆造代码或名称。贷款投向 matching_basis 必须说明实际投向"
                    "用途、匹配到的经营范围或主营条目及对应四级代码。企业代码/名称只能从"
                    "enterprise_candidates 的同一记录选择；specific 的贷款投向代码/名称"
                    "只能从 enterprise_candidates 或 loan_direction_candidates 的同一记录"
                    "选择，generic 只能等于企业结论。必须仅返回 JSON，根对象只能包含"
                    "enterprise 和 loan_direction。每个成功子结论返回 no_match=false、"
                    "industry_code、industry_name、matching_basis，贷款投向还须返回"
                    "specificity；每个无匹配子结论仅返回 no_match=true 和非空 reason，"
                    "贷款投向还须返回 specificity。不得返回置信度、AI 总结或 matched；"
                    "一致性由服务端复算。"
                ),
            },
            {
                "role": "user",
                "content": json.dumps(prompt_input, ensure_ascii=False),
            },
        ],
    }


def _serialize_candidate(candidate: EvidenceSnapshot) -> dict[str, object]:
    return {
        "major_category_code": candidate.major_category_code,
        "major_category_name": candidate.major_category_name,
        "industry_code": candidate.industry_code,
        "industry_name": candidate.industry_name,
        "definition_and_hits": [
            {
                "chunk_type": hit.chunk_type,
                "text": hit.text,
                "source_row": hit.source_row,
            }
            for hit in candidate.hits
        ],
        "evidence_traces": [
            {
                "priority": int(trace.level),
                "level": trace.level.name,
                "facts": [
                    {
                        "field_label": fact.field_label,
                        "raw_text": fact.raw_text,
                        "source": fact.source,
                    }
                    for fact in trace.facts
                ],
                "matched_catalog_fragments": [
                    {
                        "chunk_type": hit.chunk_type,
                        "text": hit.text,
                        "source_row": hit.source_row,
                    }
                    for hit in trace.hits
                ],
            }
            for trace in candidate.evidence_traces
        ],
        "vector_score": candidate.vector_score,
        "rerank_score": candidate.rerank_score,
    }


def _serialize_evidence_layer(layer: EvidenceLayer) -> dict[str, object]:
    return {
        "priority": int(layer.level),
        "level": layer.level.name,
        "available": layer.is_available,
        "unavailable_reason": layer.unavailable_reason,
        "facts": [
            {
                "field_label": fact.field_label,
                "raw_text": fact.raw_text,
                "source": fact.source,
            }
            for fact in layer.facts
        ],
    }


def _validate_model_response(
    response_payload: object,
    candidates: Sequence[EvidenceSnapshot],
    loan_direction_candidates: Sequence[EvidenceSnapshot],
    candidate_snapshot: tuple[dict[str, object], ...],
    objection: Mapping[str, object] | None,
) -> ConstrainedClassificationResult:
    try:
        content = response_payload["choices"][0]["message"]["content"]
    except (TypeError, KeyError, IndexError) as exc:
        raise NationalEconomyClassificationError(
            "DeepSeek response is missing choices[0].message.content"
        ) from exc
    if not isinstance(content, str) or not content.strip():
        raise NationalEconomyClassificationError("DeepSeek response content must be non-empty")
    try:
        model_output = json.loads(content)
    except json.JSONDecodeError as exc:
        raise NationalEconomyClassificationError(
            "DeepSeek response content is not valid JSON"
        ) from exc
    if not isinstance(model_output, dict):
        raise NationalEconomyClassificationError("DeepSeek model output must be a JSON object")
    _require_exact_output_fields(model_output, _DUAL_OUTPUT_FIELDS, branch="dual")
    enterprise_output = _required_object(model_output, "enterprise")
    loan_output = _required_object(model_output, "loan_direction")
    enterprise_no_match = _required_boolean(enterprise_output, "no_match", "enterprise")
    loan_no_match = _required_boolean(loan_output, "no_match", "loan_direction")
    loan_specificity = _required_specificity(loan_output)
    objection_snapshot = dict(objection) if objection is not None else None

    enterprise_code: str | None = None
    enterprise_name: str | None = None
    if enterprise_no_match:
        _require_exact_output_fields(
            enterprise_output,
            _ENTERPRISE_NO_MATCH_OUTPUT_FIELDS,
            branch="enterprise no_match",
        )
        enterprise_basis = _required_text(enterprise_output, "reason")
    else:
        _require_exact_output_fields(
            enterprise_output,
            _ENTERPRISE_SUCCESS_OUTPUT_FIELDS,
            branch="enterprise successful",
        )
        enterprise_code = _required_text(enterprise_output, "industry_code")
        enterprise_name = _required_text(enterprise_output, "industry_name")
        enterprise_basis = _required_text(enterprise_output, "matching_basis")
        _require_candidate_pair(
            enterprise_code,
            enterprise_name,
            candidates,
            branch="enterprise",
        )

    loan_code: str | None = None
    loan_name: str | None = None
    if loan_no_match:
        _require_exact_output_fields(
            loan_output,
            _LOAN_NO_MATCH_OUTPUT_FIELDS,
            branch="loan_direction no_match",
        )
        if loan_specificity != "specific":
            raise NationalEconomyClassificationError(
                "loan_direction no_match requires specificity=specific"
            )
        loan_basis = _required_text(loan_output, "reason")
    else:
        _require_exact_output_fields(
            loan_output,
            _LOAN_SUCCESS_OUTPUT_FIELDS,
            branch="loan_direction successful",
        )
        loan_code = _required_text(loan_output, "industry_code")
        loan_name = _required_text(loan_output, "industry_name")
        loan_basis = _required_text(loan_output, "matching_basis")
        _require_candidate_pair(
            loan_code,
            loan_name,
            (*candidates, *loan_direction_candidates),
            branch="loan_direction",
        )

    if loan_specificity == "generic":
        if enterprise_code is None or loan_code is None:
            raise NationalEconomyClassificationError(
                "generic loan_direction requires successful enterprise and loan conclusions"
            )
        if (loan_code, loan_name) != (enterprise_code, enterprise_name):
            raise NationalEconomyClassificationError(
                "generic loan_direction must exactly match the enterprise conclusion"
            )

    loan_matches_enterprise = (
        loan_code == enterprise_code
        if loan_code is not None and enterprise_code is not None
        else None
    )
    return ConstrainedClassificationResult(
        status=(
            "needs_review" if enterprise_no_match or loan_no_match else "completed"
        ),
        industry_code=enterprise_code,
        industry_name=enterprise_name,
        confidence=None,
        matching_basis=enterprise_basis,
        summary=None,
        candidate_snapshot=candidate_snapshot,
        objection=objection_snapshot,
        model_output=model_output,
        loan_industry_code=loan_code,
        loan_industry_name=loan_name,
        loan_matching_basis=loan_basis,
        loan_specificity=loan_specificity,
        loan_matches_enterprise=loan_matches_enterprise,
    )


def _required_object(
    payload: Mapping[str, object], field: str
) -> Mapping[str, object]:
    value = payload.get(field)
    if not isinstance(value, dict):
        raise NationalEconomyClassificationError(
            f"model output {field} must be a JSON object"
        )
    return value


def _required_boolean(
    payload: Mapping[str, object], field: str, branch: str
) -> bool:
    value = payload.get(field)
    if not isinstance(value, bool):
        raise NationalEconomyClassificationError(
            f"{branch} model output {field} must be a boolean"
        )
    return value


def _required_specificity(
    loan_output: Mapping[str, object],
) -> LoanSpecificity:
    value = loan_output.get("specificity")
    if value not in {"generic", "specific"}:
        raise NationalEconomyClassificationError(
            "loan_direction specificity must be generic or specific"
        )
    return value


def _require_candidate_pair(
    industry_code: str,
    industry_name: str,
    candidates: Sequence[EvidenceSnapshot],
    *,
    branch: str,
) -> None:
    valid_pairs = {
        (candidate.industry_code, candidate.industry_name) for candidate in candidates
    }
    if (industry_code, industry_name) not in valid_pairs:
        raise NationalEconomyClassificationError(
            f"{branch} industry_code and industry_name must exactly match the same candidate"
        )


def _require_exact_output_fields(
    payload: Mapping[str, object],
    expected_fields: frozenset[str],
    *,
    branch: str,
) -> None:
    actual_fields = set(payload)
    if actual_fields != expected_fields:
        missing = sorted(expected_fields - actual_fields)
        unexpected = sorted(actual_fields - expected_fields)
        raise NationalEconomyClassificationError(
            f"{branch} model output fields do not match contract; "
            f"missing={missing}, unexpected={unexpected}"
        )


def _required_text(payload: Mapping[str, object], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise NationalEconomyClassificationError(f"model output {field} must be non-empty")
    return value.strip()
