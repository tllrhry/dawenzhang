import json
import re
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import httpx

from app.core.config import Settings
from app.services.scenario_registry import (
    TECHNOLOGY_FINANCE_REGISTRATION,
    ScenarioRegistration,
)
from app.services.technology_finance_mapping_query import FiveArticlesMappingLabel
from app.services.technology_finance_stage_b import StageAResult


_CHINESE_PATTERN = re.compile(r"[㐀-鿿]")
_ROOT_FIELDS = frozenset({"selected_source_row", "selection_basis"})


class TechnologyFinanceLabelSelectionError(RuntimeError):
    """Raised when the most-matching-label selection cannot be grounded."""


def select_most_matching_technology_finance_label(
    input_payload: Mapping[str, object],
    stage_a_result: StageAResult,
    candidate_labels: Sequence[FiveArticlesMappingLabel],
    settings: Settings,
    client: httpx.Client | None = None,
) -> FiveArticlesMappingLabel:
    """Compatibility wrapper for the existing technology-finance workflow."""
    return select_most_matching_five_articles_label(
        TECHNOLOGY_FINANCE_REGISTRATION,
        input_payload,
        stage_a_result,
        candidate_labels,
        settings,
        client=client,
    )


def select_most_matching_five_articles_label(
    profile: ScenarioRegistration,
    input_payload: Mapping[str, object],
    stage_a_result: StageAResult,
    candidate_labels: Sequence[FiveArticlesMappingLabel],
    settings: Settings,
    client: httpx.Client | None = None,
) -> FiveArticlesMappingLabel:
    """Narrow multiple deterministic loan-direction candidates to the single
    most-matching one within a scenario via a constrained, grounded LLM call."""
    if not candidate_labels:
        raise TechnologyFinanceLabelSelectionError(
            "label selection requires at least one candidate label"
        )
    if any(label.scenario_id != profile.id for label in candidate_labels):
        raise TechnologyFinanceLabelSelectionError(
            f"candidate labels must all belong to scenario {profile.id}"
        )
    if len(candidate_labels) == 1:
        return candidate_labels[0]

    by_source_row = {label.source_row: label for label in candidate_labels}
    if len(by_source_row) != len(candidate_labels):
        raise TechnologyFinanceLabelSelectionError(
            "candidate labels must have distinct source rows"
        )

    request_payload = _build_request_payload(
        profile,
        input_payload,
        stage_a_result,
        candidate_labels,
        settings.deepseek_model,
    )

    if not settings.deepseek_api_key:
        raise TechnologyFinanceLabelSelectionError(
            f"DEEPSEEK_API_KEY is required for {profile.name} label selection"
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
        return _validate_response(response.json(), by_source_row)
    except TechnologyFinanceLabelSelectionError:
        raise
    except (httpx.HTTPError, json.JSONDecodeError, TypeError, ValueError, KeyError) as exc:
        raise TechnologyFinanceLabelSelectionError(
            f"DeepSeek {profile.name} label selection failed: {exc}"
        ) from exc
    finally:
        if owns_client:
            http_client.close()


def _build_request_payload(
    profile: ScenarioRegistration,
    input_payload: Mapping[str, object],
    stage_a_result: StageAResult,
    candidate_labels: Sequence[FiveArticlesMappingLabel],
    model: str,
) -> dict[str, object]:
    field_payload = [
        {"field_key": field.key, "field_label": field.label, "value": value}
        for field in profile.field_schema
        if (value := _text(input_payload.get(field.key)))
    ]
    candidates_payload = [
        {
            "source_row": label.source_row,
            "subject": label.subject,
            "taxonomy_path": list(label.taxonomy_path),
            "NEIC_Code": label.neic_code,
            "NEIC_Name": label.neic_name,
        }
        for label in candidate_labels
    ]
    prompt_input = {
        "template_fields": field_payload,
        "loan_matching_basis": _text(stage_a_result.loan_matching_basis),
        "candidates": candidates_payload,
    }
    return {
        "model": model,
        "response_format": {"type": "json_object"},
        "temperature": 0,
        "messages": [
            {
                "role": "system",
                "content": (
                    f"你是{profile.name}贷款投向标签的最终选择器。candidates 中的每一项都是"
                    "已通过确定性映射校验的候选主题标签，彼此是相互独立的主题，不是"
                    "层级祖先关系。你必须只输出一个合法 JSON 对象，不得包含 JSON 以外"
                    "任何文字，只能包含 selected_source_row 和 selection_basis 两个字段。"
                    "selected_source_row 必须原样等于 candidates 中某一项的 source_row，"
                    "不得新增、修改或臆造。你需要结合当前场景 schema 提供的模板字段和 "
                    "Stage A 贷款投向匹配依据，判断这笔"
                    "贷款的实际业务内容与哪一个候选主题最匹配，只能从 candidates 中选择"
                    "唯一一个。selection_basis 必须是非空中文，说明选择该主题而非其余"
                    "候选主题的理由。"
                ),
            },
            {
                "role": "user",
                "content": json.dumps(prompt_input, ensure_ascii=False),
            },
        ],
    }


def _validate_response(
    response_payload: object,
    by_source_row: Mapping[int, FiveArticlesMappingLabel],
) -> FiveArticlesMappingLabel:
    try:
        content = response_payload["choices"][0]["message"]["content"]
    except (TypeError, KeyError, IndexError) as exc:
        raise TechnologyFinanceLabelSelectionError(
            "DeepSeek response is missing choices[0].message.content"
        ) from exc
    if not isinstance(content, str) or not content.strip():
        raise TechnologyFinanceLabelSelectionError(
            "DeepSeek label selection response content must be non-empty"
        )
    try:
        model_output = json.loads(content)
    except json.JSONDecodeError as exc:
        raise TechnologyFinanceLabelSelectionError(
            "DeepSeek label selection response content is not valid JSON"
        ) from exc
    if not isinstance(model_output, dict) or set(model_output) != _ROOT_FIELDS:
        raise TechnologyFinanceLabelSelectionError(
            "label selection model output must contain exactly selected_source_row "
            "and selection_basis"
        )
    selected_source_row = model_output.get("selected_source_row")
    if (
        not isinstance(selected_source_row, int)
        or isinstance(selected_source_row, bool)
        or selected_source_row not in by_source_row
    ):
        raise TechnologyFinanceLabelSelectionError(
            "selected_source_row must reference a given candidate label"
        )
    selection_basis = model_output.get("selection_basis")
    if not isinstance(selection_basis, str) or not selection_basis.strip():
        raise TechnologyFinanceLabelSelectionError(
            "selection_basis must be non-empty text"
        )
    if _CHINESE_PATTERN.search(selection_basis.strip()) is None:
        raise TechnologyFinanceLabelSelectionError(
            "selection_basis must contain Chinese"
        )
    return by_source_row[selected_source_row]


def _text(value: object) -> str:
    return "" if value is None else str(value).strip()
