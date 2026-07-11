import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

import httpx

from app.core.config import Settings
from app.services.national_economy_retrieval import EvidenceSnapshot


ClassificationStatus = Literal["completed", "needs_review"]


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
    enterprise_input: Mapping[str, object],
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
        enterprise_input,
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
    enterprise_input: Mapping[str, object],
    candidate_snapshot: Sequence[dict[str, object]],
    model: str,
    objection: Mapping[str, object] | None,
) -> dict[str, object]:
    prompt_input: dict[str, object] = {
        "enterprise_input": dict(enterprise_input),
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
                    "候选外目录、企业清单、涉农规则或其他标签。必须仅返回 JSON。若存在"
                    "合适候选，返回 no_match=false、industry_code、industry_name、"
                    "confidence(0-100 数字)、matching_basis、summary；代码和名称必须来自"
                    "同一候选且只能选择一个。若候选均不匹配，返回 no_match=true 和非空"
                    "reason，不得强选候选。"
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
        "vector_score": candidate.vector_score,
        "rerank_score": candidate.rerank_score,
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

    industry_code = _required_text(model_output, "industry_code")
    industry_name = _required_text(model_output, "industry_name")
    confidence = model_output.get("confidence")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)):
        raise NationalEconomyClassificationError("confidence must be a number from 0 to 100")
    if not 0 <= confidence <= 100:
        raise NationalEconomyClassificationError("confidence must be between 0 and 100")
    matching_basis = _required_text(model_output, "matching_basis")
    summary = _required_text(model_output, "summary")
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
        confidence=float(confidence),
        matching_basis=matching_basis,
        summary=summary,
        candidate_snapshot=candidate_snapshot,
        objection=objection_snapshot,
        model_output=model_output,
    )


def _required_text(payload: Mapping[str, object], field: str) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value.strip():
        raise NationalEconomyClassificationError(f"model output {field} must be non-empty")
    return value.strip()
