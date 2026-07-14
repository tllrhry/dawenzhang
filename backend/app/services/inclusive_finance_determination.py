"""普惠金融确定性判定；不访问数据库，也不调用云端服务。"""

from __future__ import annotations

import re
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Protocol

from app.services.inclusive_finance_sizing import (
    SIZING_CATEGORIES,
    classify_enterprise_size,
    map_industry_to_sizing_category,
)


class StageAResult(Protocol):
    industry_code: str | None
    industry_major_code: str | None


FARMER_FIELD_KEYS = (
    "farmer_long_term_town_resident",
    "farmer_town_village_resident",
    "farmer_nonlocal_resident_over_one_year",
    "farmer_state_farm_employee_or_rural_individual_business",
)
_OPERATING_KEYWORDS = ("经营性", "经营", "流动资金", "流贷", "生产", "周转")
_NON_OPERATING_KEYWORDS = ("个人消费", "消费", "按揭", "住房", "车贷")
_OPERATING_EVIDENCE_FIELDS = (
    "credit_variety",
    "loan_purpose",
    "credit_approval_opinion",
)


def determine_inclusive_finance(
    input_payload: Mapping[str, object], stage_a_result: StageAResult | Mapping[str, object]
) -> dict[str, object]:
    """Return the fully traceable Phase-2 determination for one inclusive case."""
    raw = {key: _text(input_payload.get(key)) for key in _evidence_keys()}
    borrower_type = _determine_borrower_type(raw)
    is_operating_loan, operating_source = _determine_operating_loan(raw)
    credit_amount_wan = parse_credit_amount_wan(raw["credit_amount"])
    industry_code = _stage_a_value(stage_a_result, "industry_code")
    industry_major_code = _stage_a_value(stage_a_result, "industry_major_code")
    sizing_category = map_industry_to_sizing_category(industry_code, industry_major_code)
    computed_size: str | None = None
    missing_elements: list[str] = []
    if borrower_type == "enterprise":
        computed_size = classify_enterprise_size(
            sizing_category,
            parse_wan_amount(raw["annual_revenue"]),
            parse_count(raw["employee_count"]),
            parse_wan_amount(raw["total_assets"]),
        )
        if sizing_category is None:
            missing_elements.append("Stage A 企业行业信息")
        elif computed_size == "不可判定":
            missing_elements.extend(_missing_sizing_elements(sizing_category, raw))
    if is_operating_loan is None:
        missing_elements.append("经营性贷款判定")
    if credit_amount_wan is None:
        missing_elements.append("本次授信额度")

    filled_size = _parse_size(raw["enterprise_scale_type"])
    anomalies: list[dict[str, object]] = []
    if (
        borrower_type == "enterprise"
        and filled_size is not None
        and computed_size not in (None, "不可判定")
        and filled_size != computed_size
    ):
        anomalies.append(
            {
                "type": "size_mismatch",
                "filled_size": filled_size,
                "computed_size": computed_size,
                "message": "模板企业规模类型与按工信部300号计算结果不一致，以计算结果为准",
            }
        )

    determination = {
        "borrower_type": borrower_type,
        "industry_code": industry_code,
        "industry_major_code": industry_major_code,
        "sizing_category": sizing_category,
        "computed_size": computed_size,
        "filled_size": filled_size,
        "size_consistent": (
            None
            if filled_size is None or computed_size in (None, "不可判定")
            else filled_size == computed_size
        ),
        "is_operating_loan": is_operating_loan,
        "operating_determination_source": operating_source,
        "credit_amount_wan": credit_amount_wan,
        "missing_elements": tuple(dict.fromkeys(missing_elements)),
    }
    evidence_refs = _build_evidence_refs(raw, industry_code, industry_major_code)
    if missing_elements:
        basis = f"关键要素不可判定：{'、'.join(dict.fromkeys(missing_elements))}"
        return _result(
            status="needs_review",
            borrower_type=borrower_type,
            computed_size=computed_size,
            filled_size=filled_size,
            is_operating_loan=is_operating_loan,
            credit_amount_wan=credit_amount_wan,
            qualifies=None,
            inclusive_category=None,
            basis=basis,
            evidence_refs=evidence_refs,
            anomalies=anomalies,
            determination=determination,
        )

    assert credit_amount_wan is not None and is_operating_loan is not None
    reasons: list[str] = []
    if not is_operating_loan:
        reasons.append("贷款不属于经营性贷款")
    limit = 500.0 if borrower_type == "farmer" else 1000.0
    if credit_amount_wan > limit:
        reasons.append(f"授信金额 {credit_amount_wan:g} 万元超过{limit:g}万元上限")
    if borrower_type == "enterprise" and computed_size not in {"小型", "微型"}:
        reasons.append(f"计算企业规模为{computed_size}，不属于小微企业")
    if reasons:
        return _result(
            status="not_applicable",
            borrower_type=borrower_type,
            computed_size=computed_size,
            filled_size=filled_size,
            is_operating_loan=is_operating_loan,
            credit_amount_wan=credit_amount_wan,
            qualifies=False,
            inclusive_category=None,
            basis="；".join(reasons),
            evidence_refs=evidence_refs,
            anomalies=anomalies,
            determination=determination,
        )
    category = {
        "farmer": "农户经营性贷款",
        "individual_business": "个体工商户经营性贷款",
        "small_micro_owner": "小微企业主经营性贷款",
        "enterprise": "小微企业贷款",
    }[borrower_type]
    return _result(
        status="completed",
        borrower_type=borrower_type,
        computed_size=computed_size,
        filled_size=filled_size,
        is_operating_loan=is_operating_loan,
        credit_amount_wan=credit_amount_wan,
        qualifies=True,
        inclusive_category=category,
        basis=f"{category}：经营性贷款且授信金额 {credit_amount_wan:g} 万元不超过{limit:g}万元上限",
        evidence_refs=evidence_refs,
        anomalies=anomalies,
        determination=determination,
    )


def parse_credit_amount_wan(value: object) -> float | None:
    """Parse the template credit amount to 万元, accepting 亿 and thousands separators."""
    return _parse_amount(value, allow_units=True)


def parse_wan_amount(value: object) -> float | None:
    """Parse a template monetary metric whose default unit is 万元."""
    return _parse_amount(value, allow_units=True)


def parse_count(value: object) -> float | None:
    parsed = _parse_amount(value, allow_units=False)
    if parsed is not None:
        return parsed
    text = str(value or "").strip()
    match = re.match(r"^([0-9]+(?:\.[0-9]+)?)\s*(?:人|名|员工)", text)
    return float(match.group(1)) if match else None


def _parse_amount(value: object, *, allow_units: bool) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip().replace(",", "").replace("，", "")
    if not text:
        return None
    match = re.fullmatch(r"(?:人民币|RMB|¥)?\s*([0-9]+(?:\.[0-9]+)?)\s*(亿元?|万(?:元)?|元)?", text, re.IGNORECASE)
    if not match:
        return None
    try:
        amount = Decimal(match.group(1))
    except InvalidOperation:
        return None
    unit = match.group(2) or ""
    if amount < 0 or (unit and not allow_units):
        return None
    if "亿" in unit:
        amount *= Decimal(10000)
    elif unit == "元":
        amount /= Decimal(10000)
    return float(amount)


def _determine_borrower_type(raw: Mapping[str, str]) -> str:
    entity_type = raw["entity_type"]
    if "农户" in entity_type or any(_is_yes(raw[key]) for key in FARMER_FIELD_KEYS):
        return "farmer"
    if "个体工商户" in entity_type:
        return "individual_business"
    if "小微企业主" in entity_type:
        return "small_micro_owner"
    return "enterprise"


def _determine_operating_loan(raw: Mapping[str, str]) -> tuple[bool | None, str | None]:
    """Determine operating nature from all structured loan evidence.

    A document may abbreviate the product type (for example, ``流贷``) or only
    state the nature in the approval opinion.  One explicit positive source is
    sufficient; contradictory positive and non-operating evidence is preserved
    for manual review rather than resolved by field order.
    """
    operating_sources: list[str] = []
    non_operating_sources: list[str] = []
    for field in _OPERATING_EVIDENCE_FIELDS:
        result = _classify_operating_text(raw[field])
        if result is True:
            operating_sources.append(field)
        elif result is False:
            non_operating_sources.append(field)
    if operating_sources and non_operating_sources:
        return None, None
    if operating_sources:
        return True, ",".join(operating_sources)
    if non_operating_sources:
        return False, ",".join(non_operating_sources)
    return None, None


def _classify_operating_text(value: str) -> bool | None:
    operating = any(keyword in value for keyword in _OPERATING_KEYWORDS)
    non_operating = any(keyword in value for keyword in _NON_OPERATING_KEYWORDS)
    return operating if operating != non_operating else None


def _missing_sizing_elements(category: str, raw: Mapping[str, str]) -> list[str]:
    metric_fields = {
        "revenue_wan": ("annual_revenue", "上年度营业收入"),
        "employee_count": ("employee_count", "从业人员数量"),
        "total_assets_wan": ("total_assets", "总资产"),
    }
    return [
        label
        for metric in SIZING_CATEGORIES[category].required_metrics
        for field, label in (metric_fields[metric],)
        if (
            parse_wan_amount(raw[field]) if metric != "employee_count" else parse_count(raw[field])
        ) is None
    ]


def _parse_size(value: str) -> str | None:
    for size in ("大型", "中型", "小型", "微型"):
        if size in value:
            return size
    return None


def _stage_a_value(stage_a_result: StageAResult | Mapping[str, object], field: str) -> str | None:
    value = stage_a_result.get(field) if isinstance(stage_a_result, Mapping) else getattr(stage_a_result, field, None)
    return _text(value) or None


def _build_evidence_refs(raw: Mapping[str, str], industry_code: str | None, industry_major_code: str | None) -> list[dict[str, object]]:
    return [
        {"type": "field", "field_key": key, "raw_value": raw[key]}
        for key in _evidence_keys()
    ] + [
        {"type": "stage_a", "field": "industry_code", "raw_value": industry_code},
        {"type": "stage_a", "field": "industry_major_code", "raw_value": industry_major_code},
    ]


def _result(**values: object) -> dict[str, object]:
    return values


def _evidence_keys() -> tuple[str, ...]:
    return (
        "entity_type", "enterprise_scale_type", "total_assets", "annual_revenue",
        "employee_count", "credit_amount", "credit_variety", "loan_purpose",
        "credit_approval_opinion", *FARMER_FIELD_KEYS,
    )


def _text(value: object) -> str:
    return str(value or "").strip()


def _is_yes(value: str) -> bool:
    return value.strip().lower() in {"是", "yes", "y", "true", "1"}
