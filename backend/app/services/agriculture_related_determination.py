"""确定性涉农类别判定。

本模块只读取模板字段和已持久化的 Stage A 结果，不访问数据库、向量库或云端模型。
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
import time
from typing import Protocol

import httpx

from app.core.config import Settings
from app.core.config import get_settings

from app.services.national_economy_result_presentation import (
    format_industry_display_code,
)


AGRICULTURE_CATEGORY_NAME = "农、林、牧、渔业"
FARMER_IDENTITY_FIELD_KEYS = (
    "farmer_long_term_town_resident",
    "farmer_town_village_resident",
    "farmer_nonlocal_resident_over_one_year",
    "farmer_state_farm_employee_or_rural_individual_business",
)
AGRICULTURE_CATEGORY_TWO = "农村企业及各类组织贷款"
AGRICULTURE_CATEGORY_FOUR = "城市企业及各类组织涉农贷款"
URBAN_AGRICULTURE_SUBCATEGORIES = (
    "农产品加工",
    "农村基建",
    "农村流通",
    "乡村文旅或种养基地建设或农机制造销售",
)
_CHINESE_PATTERN = re.compile(r"[\u3400-\u9fff]")


class AgricultureRelatedAIError(RuntimeError):
    """Raised when a constrained agriculture fallback cannot be trusted."""


class StageAResult(Protocol):
    """The Stage A attributes used by category three."""


def determine_agriculture_related(
    input_payload: Mapping[str, object],
    stage_a_result: StageAResult | Mapping[str, object],
    settings: Settings | None = None,
    client: httpx.Client | None = None,
) -> dict[str, object]:
    """Evaluate all four agriculture categories and aggregate their outcomes.

    Category order is intentional: the two zero-cost checks run first, followed
    by address and use checks.  A match never short-circuits the remaining checks.
    """
    resolved_settings = settings or get_settings()
    category_results = [
        determine_farmer_loan_category(input_payload),
        determine_agriculture_industry_loan_category(stage_a_result),
    ]
    category_two = determine_category_two(input_payload, resolved_settings, client)
    category_results.append(category_two)
    category_results.append(
        determine_category_four(input_payload, category_two, resolved_settings, client)
    )

    matched = [item for item in category_results if item.get("result") == "matched"]
    needs_review = [item for item in category_results if item.get("result") == "needs_review"]
    if matched:
        status = "completed"
        is_agriculture_related: bool | None = True
    elif needs_review:
        status = "needs_review"
        is_agriculture_related = None
    else:
        status = "not_applicable"
        is_agriculture_related = False

    evidence_refs = [
        ref
        for item in category_results
        for ref in item.get("evidence_refs", [])
        if isinstance(ref, dict)
    ]
    model_output = {
        str(item["category"]): item["model_output"]
        for item in category_results
        if item.get("model_output") is not None
    } or None
    return {
        "status": status,
        "is_agriculture_related": is_agriculture_related,
        "matched_categories": category_results,
        "basis": "；".join(
            str(item.get("basis", "")) for item in category_results if item.get("basis")
        ),
        "evidence_refs": evidence_refs,
        "model_output": model_output,
    }


def determine_farmer_loan_category(
    input_payload: Mapping[str, object],
) -> dict[str, object]:
    """Determine category one from the four farmer identity fields."""
    matched_fields = [
        key for key in FARMER_IDENTITY_FIELD_KEYS if _is_yes(input_payload.get(key))
    ]
    evidence_refs = [
        {
            "type": "field",
            "field_key": key,
            "raw_value": _text(input_payload.get(key)),
        }
        for key in matched_fields
    ]
    if matched_fields:
        labels = "、".join(matched_fields)
        basis = f"农户身份字段 {labels} 的填写值为“是”，命中农户贷款类别。"
        result = "matched"
    else:
        basis = "农户身份四项字段均非“是”（空值按未命中处理），不命中农户贷款类别。"
        result = "not_matched"
    return _category_result(
        category=1,
        category_name="农户贷款",
        result=result,
        basis=basis,
        method="rule",
        evidence_refs=evidence_refs,
    )


def determine_agriculture_industry_loan_category(
    stage_a_result: StageAResult | Mapping[str, object],
) -> dict[str, object]:
    """Determine category three from the two persisted Stage A category names."""
    enterprise = _candidate(stage_a_result, "enterprise")
    loan = _candidate(stage_a_result, "loan")
    enterprise_hit = enterprise["category_name"] == AGRICULTURE_CATEGORY_NAME
    loan_hit = loan["category_name"] == AGRICULTURE_CATEGORY_NAME
    evidence_refs: list[dict[str, object]] = []
    basis_parts: list[str] = []

    if enterprise_hit:
        evidence_refs.append(_stage_a_ref(enterprise, "industry_category_name"))
        basis_parts.append(
            f"企业结论门类为“{AGRICULTURE_CATEGORY_NAME}”"
            f"（{enterprise['display_code']} {enterprise['industry_name']}），"
            "命中农林牧渔业贷款类别。"
        )
    if loan_hit:
        evidence_refs.append(_stage_a_ref(loan, "loan_industry_category_name"))
        basis_parts.append(
            f"贷款投向为“{AGRICULTURE_CATEGORY_NAME}”"
            f"（{loan['display_code']} {loan['industry_name']}），"
            "命中农林牧渔业贷款类别。"
        )

    return _category_result(
        category=3,
        category_name="农林牧渔业贷款",
        result="matched" if enterprise_hit or loan_hit else "not_matched",
        basis=("；".join(basis_parts) if basis_parts else "企业结论门类与贷款投向门类均未命中农、林、牧、渔业。"),
        method="stage_a",
        evidence_refs=evidence_refs,
    )


def determine_rural_enterprise_loan_category(
    input_payload: Mapping[str, object],
    settings: Settings,
    client: httpx.Client | None = None,
) -> dict[str, object]:
    """Classify category two from registration address, with a grounded AI fallback."""
    address, source = _select_address(input_payload)
    if not address:
        return _category_result(
            category=2, category_name=AGRICULTURE_CATEGORY_TWO,
            result="needs_review", basis="注册地址与实际经营地址均为空，待人工复核。",
            method="rule", evidence_refs=[],
        )
    rule_result = _classify_address_rule(address)
    source_note = "注册地址" if source == "registered_address" else "实际经营地址（注册地址为空时降级使用）"
    if rule_result is not None:
        urban_rural, excerpt = rule_result
        result = "matched" if urban_rural == "农村地区" else "not_matched"
        return _category_result(
            category=2, category_name=AGRICULTURE_CATEGORY_TWO, result=result,
            basis=f"{source_note}“{address}”中“{excerpt}”符合地址规则，判定为{urban_rural}。",
            method="rule", evidence_refs=[_address_ref(source, address, excerpt)],
        )
    model = _call_agriculture_ai(
        settings, client, address, source, "address", ("农村地区", "城区", "无法判定")
    )
    urban_rural = model["label"]
    result = {"农村地区": "matched", "城区": "not_matched", "无法判定": "needs_review"}[urban_rural]
    return _category_result(
        category=2, category_name=AGRICULTURE_CATEGORY_TWO, result=result,
        basis=f"{model['basis']}（依据来源：{source_note}）", method="ai",
        evidence_refs=[_address_ref(source, address, address)], model_output=model["raw"],
    )


def determine_category_two(input_payload: Mapping[str, object], settings: Settings, client: httpx.Client | None = None) -> dict[str, object]:
    return determine_rural_enterprise_loan_category(input_payload, settings, client)


def determine_urban_agriculture_loan_category(
    input_payload: Mapping[str, object], category_two: Mapping[str, object],
    settings: Settings, client: httpx.Client | None = None,
) -> dict[str, object]:
    """Classify category four only after category two establishes an urban address."""
    category_two_result = str(category_two.get("result", ""))
    if category_two_result == "matched":
        return _category_result(category=4, category_name=AGRICULTURE_CATEGORY_FOUR,
                                result="not_applicable", basis="类别二已判定为农村地区，类别四不适用。",
                                method="rule", evidence_refs=[])
    if category_two_result == "needs_review":
        return _category_result(category=4, category_name=AGRICULTURE_CATEGORY_FOUR,
                                result="needs_review", basis="类别二待人工复核，无法确认城市主体前提。",
                                method="rule", evidence_refs=[])
    fields = ("loan_purpose", "project_content", "trade_goods_services")
    text = "；".join(f"{key}：{_text(input_payload.get(key))}" for key in fields if _text(input_payload.get(key)))
    for label, patterns in _URBAN_USE_RULES:
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                excerpt = match.group(0)
                return _category_result(category=4, category_name=AGRICULTURE_CATEGORY_FOUR,
                                        result="matched", basis=f"原文“{excerpt}”命中{label}关键词。",
                                        method="rule", evidence_refs=[{"type": "field_text", "excerpt": excerpt}])
    model = _call_agriculture_ai(settings, client, text, "use_fields", "use",
                                 (*URBAN_AGRICULTURE_SUBCATEGORIES, "均不属于", "无法判定"))
    label = model["label"]
    result = "matched" if label in URBAN_AGRICULTURE_SUBCATEGORIES else ("needs_review" if label == "无法判定" else "not_matched")
    return _category_result(category=4, category_name=AGRICULTURE_CATEGORY_FOUR, result=result,
                            basis=model["basis"], method="ai", evidence_refs=[{"type": "field_text", "excerpt": text}],
                            model_output=model["raw"])


def determine_category_four(input_payload: Mapping[str, object], category_two: Mapping[str, object], settings: Settings, client: httpx.Client | None = None) -> dict[str, object]:
    return determine_urban_agriculture_loan_category(input_payload, category_two, settings, client)


_URBAN_USE_RULES = (
    ("农产品加工", (r"(?:粮食|果蔬|蔬菜|水果|肉类|屠宰|水产)[^；。]{0,12}(?:加工|深加工)", r"农产品加工")),
    ("农村基建", (r"乡村道路", r"农田水利", r"农村污水", r"垃圾处理", r"村级养老设施")),
    ("农村流通", (r"农产品批发市场", r"冷链仓储", r"农资经销")),
    (URBAN_AGRICULTURE_SUBCATEGORIES[3], (r"乡村文旅", r"种养基地", r"农机(?:制造|销售)")),
)


def _select_address(payload: Mapping[str, object]) -> tuple[str, str]:
    registered = _text(payload.get("registered_address"))
    if registered:
        return registered, "registered_address"
    return _text(payload.get("actual_business_address")), "actual_business_address"


def _classify_address_rule(address: str) -> tuple[str, str] | None:
    rural = re.search(r"村|乡|(?<!城关)镇", address)
    urban = re.search(r"城关镇|市辖区|市[^县乡镇村]{0,12}区", address)
    if bool(rural) == bool(urban):
        return None
    match = rural or urban
    return ("农村地区" if rural else "城区", match.group(0))


def _call_agriculture_ai(settings: Settings, client: httpx.Client | None, raw_text: str, source: str,
                         task: str, labels: tuple[str, ...]) -> dict[str, object]:
    if not settings.deepseek_api_key:
        raise AgricultureRelatedAIError("DEEPSEEK_API_KEY is required for agriculture fallback")
    payload = {"model": settings.deepseek_model, "response_format": {"type": "json_object"}, "temperature": 0,
               "messages": [{"role": "system", "content": f"你只能从 {'、'.join(labels)} 中选择一个，并只输出 JSON：label、basis。basis 必须是非空中文，且引用输入原文。任务：{task}。"},
                             {"role": "user", "content": json.dumps({"source": source, "text": raw_text, "candidates": labels}, ensure_ascii=False)}]}
    owns_client = client is None
    http_client = client or httpx.Client(base_url=settings.deepseek_base_url.rstrip("/"), timeout=httpx.Timeout(settings.deepseek_timeout_seconds, connect=settings.http_connect_timeout_seconds))
    try:
        for attempt in range(3):
            try:
                response = http_client.post("/chat/completions", headers={"Authorization": f"Bearer {settings.deepseek_api_key}"}, json=payload)
                break
            except (httpx.TimeoutException, httpx.NetworkError):
                if attempt == 2:
                    raise
                time.sleep(0.5 * (2 ** attempt))
        response.raise_for_status()
        try:
            content = response.json()["choices"][0]["message"]["content"]
            output = json.loads(content)
        except (TypeError, KeyError, IndexError, json.JSONDecodeError) as exc:
            raise AgricultureRelatedAIError("DeepSeek response is not valid JSON") from exc
        if not isinstance(output, dict):
            raise AgricultureRelatedAIError("DeepSeek output must be a JSON object")
        label_key = next((key for key in ("label", "result", "category", "classification") if key in output), None)
        basis_key = next((key for key in ("basis", "reason", "evidence") if key in output), None)
        if label_key is None or basis_key is None or len(output) != 2:
            raise AgricultureRelatedAIError("DeepSeek output must contain one label and one basis")
        label, basis = output[label_key], output[basis_key]
        original_values = [part.split("：", 1)[-1].strip() for part in _text(raw_text).split("；")]
        grounded = isinstance(basis, str) and _has_grounded_basis(original_values, basis)
        if label not in labels or not isinstance(basis, str) or not basis.strip() or _CHINESE_PATTERN.search(basis) is None or not grounded:
            raise AgricultureRelatedAIError("DeepSeek basis must be Chinese and quote original input")
        return {"label": label, "basis": basis.strip(), "raw": output}
    except AgricultureRelatedAIError:
        raise
    except httpx.HTTPError as exc:
        raise AgricultureRelatedAIError(f"DeepSeek agriculture fallback failed: {exc}") from exc
    finally:
        if owns_client:
            http_client.close()


def _has_grounded_basis(original_values: list[str], basis: str, *, minimum_length: int = 4) -> bool:
    """Accept a rewritten citation when it preserves a meaningful Chinese phrase.

    Model explanations commonly omit connective words or add punctuation, so an
    entire field value is too strict.  Short placeholders such as ``无`` are
    deliberately ignored by requiring a contiguous Chinese overlap of at least
    four characters.
    """
    return any(
        _longest_common_chinese_substring_length(value, basis) >= minimum_length
        for value in original_values
        if value
    )


def _longest_common_chinese_substring_length(left: str, right: str) -> int:
    """Return the longest contiguous shared run made only of Chinese chars."""
    previous = [0] * (len(right) + 1)
    longest = 0
    for left_char in left:
        current = [0]
        for index, right_char in enumerate(right, start=1):
            if left_char == right_char and _CHINESE_PATTERN.fullmatch(left_char):
                current.append(previous[index - 1] + 1)
                longest = max(longest, current[-1])
            else:
                current.append(0)
        previous = current
    return longest


def _address_ref(source: str, address: str, excerpt: str) -> dict[str, object]:
    return {"type": "field", "field_key": source, "raw_value": address, "excerpt": excerpt}


def _candidate(stage_a_result: StageAResult | Mapping[str, object], side: str) -> dict[str, str | None]:
    prefix = "" if side == "enterprise" else "loan_"
    code = _stage_a_value(stage_a_result, f"{prefix}industry_code")
    major_code = _stage_a_value(stage_a_result, f"{prefix}industry_major_code")
    middle_code = _stage_a_value(stage_a_result, f"{prefix}industry_middle_code")
    category_name = _stage_a_value(stage_a_result, f"{prefix}industry_category_name")
    middle_name = _stage_a_value(stage_a_result, f"{prefix}industry_middle_name")
    industry_name = _stage_a_value(stage_a_result, f"{prefix}industry_name")
    if len(code or "") == 2:
        display_name = category_name or industry_name
    elif len(code or "") == 3:
        display_name = middle_name or industry_name or category_name
    else:
        display_name = industry_name or middle_name or category_name
    return {
        "side": side,
        "code": code,
        "major_code": major_code,
        "middle_code": middle_code,
        "category_name": category_name,
        "industry_name": display_name,
        "display_code": format_industry_display_code(major_code, code, middle_code),
    }


def _stage_a_ref(candidate: Mapping[str, str | None], field_key: str) -> dict[str, object]:
    return {
        "type": "stage_a",
        "field_key": field_key,
        "raw_value": candidate["category_name"],
        "code": candidate["display_code"],
        "name": candidate["industry_name"],
    }


def _category_result(**values: object) -> dict[str, object]:
    return values


def _stage_a_value(stage_a_result: StageAResult | Mapping[str, object], field: str) -> str | None:
    value = stage_a_result.get(field) if isinstance(stage_a_result, Mapping) else getattr(stage_a_result, field, None)
    return _text(value) or None


def _text(value: object) -> str:
    return str(value or "").strip()


def _is_yes(value: object) -> bool:
    return _text(value).lower() in {"是", "yes", "y", "true", "1"}
