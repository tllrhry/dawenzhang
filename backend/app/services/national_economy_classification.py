import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

import httpx

from app.core.config import Settings
from app.services.national_economy_decision_policy import EvidenceLayer
from app.services.national_economy_retrieval import EvidenceSnapshot


ClassificationStatus = Literal["completed", "needs_review"]
_SUCCESS_OUTPUT_FIELDS = frozenset(
    {"no_match", "industry_code", "industry_name", "matching_basis"}
)
_NO_MATCH_OUTPUT_FIELDS = frozenset({"no_match", "reason"})


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


def classify_national_economy(
    evidence_layers: Sequence[EvidenceLayer],
    candidates: Sequence[EvidenceSnapshot],
    settings: Settings,
    objection: Mapping[str, object] | None = None,
    client: httpx.Client | None = None,
) -> ConstrainedClassificationResult:
    if not candidates:
        raise ValueError("at least one industry candidate is required")
    if not settings.deepseek_api_key:
        raise NationalEconomyClassificationError(
            "DEEPSEEK_API_KEY is required for classification"
        )

    candidate_snapshot = tuple(_serialize_candidate(candidate) for candidate in candidates)
    request_payload = _build_request_payload(
        evidence_layers,
        candidate_snapshot,
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
    model: str,
    objection: Mapping[str, object] | None,
) -> dict[str, object]:
    ordered_layers = tuple(sorted(evidence_layers, key=lambda layer: layer.level))
    prompt_input: dict[str, object] = {
        "ordered_evidence": [
            _serialize_evidence_layer(layer) for layer in ordered_layers
        ],
        "candidates": list(candidate_snapshot),
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
                    "异议（如有）和给定候选的定义/命中片段作答，不得使用或声称使用"
                    "候选外目录、企业清单、涉农规则或其他标签。企业证据已按 priority=1"
                    "到 4 排序：主营业务及营收、贸易合同及产业链、贷款用途、营业执照"
                    "经营范围。必须采用最高可用层；低层冲突不得推翻高层，只有高层不可用"
                    "才可降级，并须在 matching_basis 说明采用层级、字段标签、目录片段及"
                    "冲突或降级理由。异议已并入 ordered_evidence 的既有层，不是第五级。"
                    "必须仅返回 JSON。若存在"
                    "合适候选，返回 no_match=false、industry_code、industry_name、"
                    "matching_basis，除这四个键外不得返回其他字段；代码和名称必须来自"
                    "同一候选且只能选择一个，不得返回置信度或 AI 总结。若候选均不匹配，"
                    "仅返回 no_match=true 和非空 reason，不得强选候选。"
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

    no_match = model_output.get("no_match")
    if not isinstance(no_match, bool):
        raise NationalEconomyClassificationError("model output no_match must be a boolean")
    objection_snapshot = dict(objection) if objection is not None else None
    if no_match:
        _require_exact_output_fields(
            model_output,
            _NO_MATCH_OUTPUT_FIELDS,
            branch="no_match",
        )
        reason = _required_text(model_output, "reason")
        return ConstrainedClassificationResult(
            status="needs_review",
            industry_code=None,
            industry_name=None,
            confidence=None,
            matching_basis=reason,
            summary=None,
            candidate_snapshot=candidate_snapshot,
            objection=objection_snapshot,
            model_output=model_output,
        )

    _require_exact_output_fields(
        model_output,
        _SUCCESS_OUTPUT_FIELDS,
        branch="successful",
    )
    industry_code = _required_text(model_output, "industry_code")
    industry_name = _required_text(model_output, "industry_name")
    matching_basis = _required_text(model_output, "matching_basis")
    valid_pairs = {
        (candidate.industry_code, candidate.industry_name) for candidate in candidates
    }
    if (industry_code, industry_name) not in valid_pairs:
        raise NationalEconomyClassificationError(
            "industry_code and industry_name must exactly match the same candidate"
        )
    return ConstrainedClassificationResult(
        status="completed",
        industry_code=industry_code,
        industry_name=industry_name,
        confidence=None,
        matching_basis=matching_basis,
        summary=None,
        candidate_snapshot=candidate_snapshot,
        objection=objection_snapshot,
        model_output=model_output,
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
