"""Green-finance condition-criteria retrieval and grounded selection.

This module deliberately stays independent from Stage B orchestration.  Stage B
will decide when a side has exhausted NEIC-code lookup and call these helpers.
"""

import json
import re
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Literal

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import FiveArticlesMappingRow, FiveArticlesMappingVersion
from app.services.national_economy_catalog_chunks import embed_texts
from app.services.scenario_registry import GREEN_FINANCE_SCENARIO
from app.services.technology_finance_mapping_query import FiveArticlesMappingLabel


RECALL_LIMIT = 30
MIN_RERANK_RESULTS = 5
MAX_RERANK_RESULTS = 8
NO_MATCH_SOURCE_ROW = "以上均不匹配"
_CHINESE_PATTERN = re.compile(r"[㐀-鿿]")
_ROOT_FIELDS = frozenset({"selected_source_row", "selection_basis"})

ConditionSide = Literal["enterprise", "loan_direction"]
EmbeddingRequest = Callable[[Sequence[str], Settings], Sequence[Sequence[float]]]


class GreenFinanceConditionSelectionError(RuntimeError):
    """Raised when condition-candidate selection is not grounded in evidence."""


@dataclass(frozen=True)
class GreenFinanceConditionCandidate:
    label: FiveArticlesMappingLabel
    condition_criteria: str
    vector_score: float
    rerank_score: float

    @property
    def source_row(self) -> int:
        return self.label.source_row


def retrieve_green_finance_condition_candidates(
    session: Session,
    input_payload: Mapping[str, object],
    side: ConditionSide,
    settings: Settings,
    *,
    top_n: int = MAX_RERANK_RESULTS,
    embedding_request: EmbeddingRequest = embed_texts,
    rerank_client: httpx.Client | None = None,
) -> tuple[GreenFinanceConditionCandidate, ...]:
    """Recall published green-finance condition rows and rerank their criteria.

    ``side`` is intentionally explicit so enterprise and loan-direction fallback
    calls cannot accidentally share their evidence or retrieved candidates.
    """
    if not MIN_RERANK_RESULTS <= top_n <= MAX_RERANK_RESULTS:
        raise ValueError("top_n must be between 5 and 8")
    query = build_green_finance_condition_evidence(input_payload, side)
    embeddings = tuple(embedding_request((query,), settings))
    if len(embeddings) != 1:
        raise ValueError("condition embedding response count does not match request")

    distance = FiveArticlesMappingRow.condition_embedding.cosine_distance(
        list(embeddings[0])
    )
    statement = (
        select(FiveArticlesMappingRow, distance.label("distance"))
        .join(
            FiveArticlesMappingVersion,
            FiveArticlesMappingRow.mapping_version_id == FiveArticlesMappingVersion.id,
        )
        .where(
            FiveArticlesMappingRow.scenario_id == GREEN_FINANCE_SCENARIO,
            FiveArticlesMappingVersion.scenario_id == GREEN_FINANCE_SCENARIO,
            FiveArticlesMappingVersion.status == "published",
            FiveArticlesMappingRow.condition_embedding.is_not(None),
            FiveArticlesMappingRow.condition_criteria.is_not(None),
        )
        .order_by(distance)
        .limit(RECALL_LIMIT)
    )
    recalled = tuple(session.execute(statement).all())
    if not recalled:
        return ()

    candidates = tuple(
        _candidate_from_row(row, float(row_distance))
        for row, row_distance in recalled
    )
    reranked = _rerank_green_finance_condition_candidates(
        query, candidates, settings, top_n=top_n, client=rerank_client
    )
    return reranked


def build_green_finance_condition_evidence(
    input_payload: Mapping[str, object], side: ConditionSide
) -> str:
    """Build only the two evidence fields allowed for the requested side."""
    if side == "enterprise":
        fields = (
            ("核心产品 / 服务名称", "core_products_services"),
            ("主营业务", "main_business"),
        )
    elif side == "loan_direction":
        fields = (
            ("贷款用途详细描述", "loan_purpose"),
            ("贸易合同核心交易品类 / 服务内容", "trade_goods_services"),
        )
    else:
        raise ValueError("side must be enterprise or loan_direction")
    evidence = tuple(
        f"{label}：{text}"
        for label, key in fields
        if (text := _text(input_payload.get(key)))
    )
    if not evidence:
        raise ValueError(f"{side} condition fallback requires usable evidence")
    return "\n".join(evidence)


def select_green_finance_condition_label(
    candidates: Sequence[GreenFinanceConditionCandidate],
    evidence_text: str,
    settings: Settings,
    *,
    client: httpx.Client | None = None,
) -> FiveArticlesMappingLabel | None:
    """Select one grounded condition candidate, or explicitly return no match."""
    if not candidates:
        raise GreenFinanceConditionSelectionError(
            "condition label selection requires at least one candidate"
        )
    normalized_evidence = _text(evidence_text)
    if not normalized_evidence:
        raise GreenFinanceConditionSelectionError(
            "condition label selection requires non-empty evidence text"
        )
    by_source_row = {candidate.source_row: candidate for candidate in candidates}
    if len(by_source_row) != len(candidates):
        raise GreenFinanceConditionSelectionError(
            "condition candidates must have distinct source rows"
        )
    if any(candidate.label.scenario_id != GREEN_FINANCE_SCENARIO for candidate in candidates):
        raise GreenFinanceConditionSelectionError(
            "condition candidates must all belong to green_finance"
        )
    if not settings.deepseek_api_key:
        raise GreenFinanceConditionSelectionError(
            "DEEPSEEK_API_KEY is required for green-finance condition selection"
        )

    request_payload = _build_selection_request(candidates, normalized_evidence, settings)
    owns_client = client is None
    http_client = client or httpx.Client(
        base_url=settings.deepseek_base_url.rstrip("/"),
        timeout=httpx.Timeout(
            settings.deepseek_timeout_seconds,
            connect=settings.http_connect_timeout_seconds,
        ),
    )
    try:
        for attempt in range(3):
            try:
                response = http_client.post(
                    "/chat/completions",
                    headers={"Authorization": f"Bearer {settings.deepseek_api_key}"},
                    json=request_payload,
                )
                break
            except (httpx.TimeoutException, httpx.NetworkError):
                if attempt == 2:
                    raise
                time.sleep(0.5 * (2**attempt))
        response.raise_for_status()
        return _validate_selection_response(
            response.json(), by_source_row, normalized_evidence
        )
    except GreenFinanceConditionSelectionError:
        raise
    except (httpx.HTTPError, json.JSONDecodeError, TypeError, ValueError, KeyError) as exc:
        raise GreenFinanceConditionSelectionError(
            f"DeepSeek green-finance condition selection failed: {exc}"
        ) from exc
    finally:
        if owns_client:
            http_client.close()


def _candidate_from_row(
    row: FiveArticlesMappingRow, distance: float
) -> GreenFinanceConditionCandidate:
    criteria = _text(row.condition_criteria)
    if not criteria:
        raise ValueError("recalled condition row must contain condition_criteria")
    return GreenFinanceConditionCandidate(
        label=FiveArticlesMappingLabel(
            mapping_version_id=row.mapping_version_id,
            scenario_id=row.scenario_id,
            neic_code=row.neic_code,
            code_level=row.code_level,  # '-' placeholder rows intentionally have None.
            neic_name=row.neic_name,
            subject=row.subject,
            tier1=row.tier1,
            tier2=row.tier2,
            tier3=row.tier3,
            tier4=row.tier4,
            source_row=row.source_row,
        ),
        condition_criteria=criteria,
        vector_score=1.0 - distance,
        rerank_score=0.0,
    )


def _rerank_green_finance_condition_candidates(
    query: str,
    candidates: Sequence[GreenFinanceConditionCandidate],
    settings: Settings,
    *,
    top_n: int,
    client: httpx.Client | None,
) -> tuple[GreenFinanceConditionCandidate, ...]:
    if not settings.siliconflow_api_key:
        raise RuntimeError("SILICONFLOW_API_KEY is required for reranking")
    owns_client = client is None
    http_client = client or httpx.Client(
        base_url=settings.siliconflow_base_url.rstrip("/"),
        timeout=httpx.Timeout(
            settings.siliconflow_timeout_seconds,
            connect=settings.http_connect_timeout_seconds,
        ),
    )
    try:
        response = http_client.post(
            "/rerank",
            headers={"Authorization": f"Bearer {settings.siliconflow_api_key}"},
            json={
                "model": settings.siliconflow_rerank_model,
                "query": query,
                "documents": [candidate.condition_criteria for candidate in candidates],
                "top_n": min(top_n, len(candidates)),
                "return_documents": False,
            },
        )
        response.raise_for_status()
        results = response.json().get("results")
        if not isinstance(results, list):
            raise ValueError("rerank response results must be a list")
        reranked: list[GreenFinanceConditionCandidate] = []
        for result in results:
            if not isinstance(result, dict) or "index" not in result or "relevance_score" not in result:
                raise ValueError("rerank response item is missing index or relevance_score")
            index = result["index"]
            if not isinstance(index, int) or not 0 <= index < len(candidates):
                raise ValueError("rerank response index is out of range")
            candidate = candidates[index]
            reranked.append(
                GreenFinanceConditionCandidate(
                    label=candidate.label,
                    condition_criteria=candidate.condition_criteria,
                    vector_score=candidate.vector_score,
                    rerank_score=float(result["relevance_score"]),
                )
            )
        return tuple(reranked[:top_n])
    finally:
        if owns_client:
            http_client.close()


def _build_selection_request(
    candidates: Sequence[GreenFinanceConditionCandidate], evidence_text: str, settings: Settings
) -> dict[str, object]:
    prompt_input = {
        "evidence_text": evidence_text,
        "candidates": [
            {
                "source_row": candidate.source_row,
                "subject": candidate.label.subject,
                "taxonomy_path": list(candidate.label.taxonomy_path),
                "condition_criteria": candidate.condition_criteria,
            }
            for candidate in candidates
        ],
        "no_match_source_row": NO_MATCH_SOURCE_ROW,
    }
    return {
        "model": settings.deepseek_model,
        "response_format": {"type": "json_object"},
        "temperature": 0,
        "messages": [
            {
                "role": "system",
                "content": (
                    "你是绿色金融条件/标准标签选择器。你必须只输出一个合法 JSON 对象，"
                    "只包含 selected_source_row 和 selection_basis 两个字段。"
                    "selected_source_row 必须原样等于 candidates 中某项的 source_row，"
                    f"或原样等于 {NO_MATCH_SOURCE_ROW}。只有在任一候选的条件/标准"
                    "与证据文本均不匹配时才可选择该值。selection_basis 必须是非空中文，"
                    "并逐字引用候选条件/标准原文或证据文本中的一个连续片段；不得臆造。"
                ),
            },
            {"role": "user", "content": json.dumps(prompt_input, ensure_ascii=False)},
        ],
    }


def _validate_selection_response(
    response_payload: object,
    by_source_row: Mapping[int, GreenFinanceConditionCandidate],
    evidence_text: str,
) -> FiveArticlesMappingLabel | None:
    try:
        content = response_payload["choices"][0]["message"]["content"]
    except (TypeError, KeyError, IndexError) as exc:
        raise GreenFinanceConditionSelectionError(
            "DeepSeek response is missing choices[0].message.content"
        ) from exc
    if not isinstance(content, str) or not content.strip():
        raise GreenFinanceConditionSelectionError(
            "DeepSeek condition selection response content must be non-empty"
        )
    try:
        model_output = json.loads(content)
    except json.JSONDecodeError as exc:
        raise GreenFinanceConditionSelectionError(
            "DeepSeek condition selection response content is not valid JSON"
        ) from exc
    if not isinstance(model_output, dict) or set(model_output) != _ROOT_FIELDS:
        raise GreenFinanceConditionSelectionError(
            "condition selection model output must contain exactly selected_source_row and selection_basis"
        )
    selected_source_row = model_output.get("selected_source_row")
    basis = model_output.get("selection_basis")
    if not isinstance(basis, str) or not basis.strip() or _CHINESE_PATTERN.search(basis) is None:
        raise GreenFinanceConditionSelectionError(
            "selection_basis must be non-empty Chinese text"
        )
    grounded_sources = tuple(candidate.condition_criteria for candidate in by_source_row.values())
    if not _basis_is_grounded(basis.strip(), grounded_sources, evidence_text):
        raise GreenFinanceConditionSelectionError(
            "selection_basis must quote candidate condition criteria or side evidence"
        )
    if selected_source_row == NO_MATCH_SOURCE_ROW:
        return None
    if not isinstance(selected_source_row, int) or isinstance(selected_source_row, bool):
        raise GreenFinanceConditionSelectionError(
            "selected_source_row must reference a given condition candidate or no-match"
        )
    candidate = by_source_row.get(selected_source_row)
    if candidate is None:
        raise GreenFinanceConditionSelectionError(
            "selected_source_row must reference a given condition candidate or no-match"
        )
    return candidate.label


def _basis_is_grounded(
    basis: str, criteria: Sequence[str], evidence_text: str
) -> bool:
    # Require a meaningful contiguous quote rather than accepting incidental one
    # character overlap such as “的”.
    sources = (*criteria, evidence_text)
    return any(
        fragment in source
        for source in sources
        for fragment in _chinese_fragments(basis)
        if len(fragment) >= 2
    )


def _chinese_fragments(text: str) -> tuple[str, ...]:
    return tuple(fragment for fragment in re.findall(r"[㐀-鿿]{2,}", text) if fragment)


def _text(value: object) -> str:
    return "" if value is None else str(value).strip()
