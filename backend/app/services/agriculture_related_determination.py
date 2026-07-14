"""确定性涉农类别判定。

本模块只读取模板字段和已持久化的 Stage A 结果，不访问数据库、向量库或云端模型。
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

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


class StageAResult(Protocol):
    """The Stage A attributes used by category three."""


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


def determine_category_one(input_payload: Mapping[str, object]) -> dict[str, object]:
    """Generic alias reserved for the shared four-category result contract."""
    return determine_farmer_loan_category(input_payload)


def determine_category_three(
    stage_a_result: StageAResult | Mapping[str, object],
) -> dict[str, object]:
    """Generic alias reserved for the shared four-category result contract."""
    return determine_agriculture_industry_loan_category(stage_a_result)


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
