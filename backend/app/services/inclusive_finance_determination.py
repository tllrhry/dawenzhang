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
BORROWER_TYPE_LABELS = {
    "farmer": "农户",
    "individual_business": "个体工商户",
    "small_micro_owner": "小微企业主",
    "enterprise": "企业",
}
_OPERATING_KEYWORDS = ("经营性", "经营", "流动资金", "流贷", "生产", "周转")
_NON_OPERATING_KEYWORDS = ("个人消费", "消费", "按揭", "住房", "车贷")
_OPERATING_EVIDENCE_FIELDS = (
    "credit_variety",
    "loan_purpose",
    "credit_approval_opinion",
)
_FARMER_FIELD_LABELS = {
    "farmer_long_term_town_resident": "长期居住在乡镇",
    "farmer_town_village_resident": "居住在城关镇所辖行政村",
    "farmer_nonlocal_resident_over_one_year": "非本地户籍但在本地居住一年以上",
    "farmer_state_farm_employee_or_rural_individual_business": "国有农场职工或农村个体工商户",
}
_APPROVED_AMOUNT_RE = re.compile(
    r"(?:人民币|RMB|¥)?\s*[0-9][0-9,，]*(?:\.[0-9]+)?\s*(?:亿元?|万元?|元)",
    re.IGNORECASE,
)
_APPROVAL_KEYWORD_RE = re.compile(r"批复|同意|核定|批准|审定")
_APPLICATION_AMOUNT_RE = re.compile(
    r"(?:申请|申报|拟申请)(?:授信)?(?:金额|额度)?\s*$"
)


def determine_inclusive_finance(
    input_payload: Mapping[str, object], stage_a_result: StageAResult | Mapping[str, object]
) -> dict[str, object]:
    """Return the fully traceable Phase-2 determination for one inclusive case."""
    raw = {
        key: _text(input_payload.get(key))
        for key in (*_evidence_keys(), "registered_address")
    }
    borrower_type = _determine_borrower_type(raw)
    is_operating_loan, operating_source = _determine_operating_loan(raw)
    credit_resolution = resolve_credit_amount(
        raw["credit_amount"], raw["credit_approval_opinion"]
    )
    credit_amount_wan = credit_resolution["adopted_amount_wan"]
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
    credit_issue = credit_resolution["issue"]
    if credit_issue:
        missing_elements.append(str(credit_issue))

    filled_size = _parse_size(raw["enterprise_scale_type"])
    farmer_matched_conditions = [
        _FARMER_FIELD_LABELS[key] for key in FARMER_FIELD_KEYS if _is_yes(raw[key])
    ]
    borrower_type_basis = (
        f"农户条件命中：{'、'.join(farmer_matched_conditions)}"
        if borrower_type == "farmer" and farmer_matched_conditions
        else (
            f"主体类型填报：{raw['entity_type']}；农户条件作为补充证据，"
            f"不覆盖明确主体类型：{'、'.join(farmer_matched_conditions)}"
            if farmer_matched_conditions
            else f"主体类型填报：{raw['entity_type'] or '未明确，按企业处理'}"
        )
    )
    farmer_registration_address_support = _farmer_registration_address_support(
        raw["registered_address"]
    )
    anomalies: list[dict[str, object]] = []
    if credit_resolution["conflict"]:
        anomalies.append(
            {
                "type": "credit_amount_conflict",
                "structured_raw_value": raw["credit_amount"],
                "structured_amount_wan": credit_resolution["structured_amount_wan"],
                "approval_raw_value": raw["credit_approval_opinion"],
                "approval_amounts_wan": credit_resolution["approval_amounts_wan"],
                "message": "结构化授信额度与授信审批意见中的批复额度不一致，需人工复核",
            }
        )
    elif len(credit_resolution["approval_amounts_wan"]) > 1:
        anomalies.append(
            {
                "type": "multiple_approved_credit_amounts",
                "approval_raw_value": raw["credit_approval_opinion"],
                "approval_amounts_wan": credit_resolution["approval_amounts_wan"],
                "message": "授信审批意见包含多个不同批复额度，需人工复核",
            }
        )
    elif raw["credit_amount"] and credit_resolution["structured_amount_wan"] is None:
        anomalies.append(
            {
                "type": "unparseable_structured_credit_amount",
                "structured_raw_value": raw["credit_amount"],
                "message": "结构化授信额度不可解析，已按其他明确来源处理",
            }
        )
    if is_operating_loan is None and any(
        _classify_operating_text(raw[field]) is not None
        for field in _OPERATING_EVIDENCE_FIELDS
    ):
        anomalies.append(
            {
                "type": "operating_nature_conflict",
                "message": "经营性与非经营性贷款证据冲突，需人工复核",
            }
        )
    if borrower_type == "enterprise" and computed_size in (None, "不可判定"):
        missing_sizing_metrics = (
            _missing_sizing_elements(sizing_category, raw)
            if sizing_category
            else ["Stage A 企业行业信息"]
        )
        anomalies.append(
            {
                "type": "missing_sizing_metrics",
                "missing_metrics": missing_sizing_metrics,
                "message": f"企业划型必要指标缺失：{'、'.join(missing_sizing_metrics)}",
            }
        )
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
        "credit_amount_source": credit_resolution["source"],
        "credit_amount_consistent": credit_resolution["consistent"],
        "structured_credit_amount_raw": raw["credit_amount"],
        "structured_credit_amount_wan": credit_resolution["structured_amount_wan"],
        "approval_credit_amount_raw": raw["credit_approval_opinion"],
        "approval_credit_amounts_wan": credit_resolution["approval_amounts_wan"],
        "credit_amount_conflict": credit_resolution["conflict"],
        "farmer_matched_conditions": farmer_matched_conditions,
        "borrower_type_basis": borrower_type_basis,
        "farmer_registration_address_support": farmer_registration_address_support,
        "missing_elements": tuple(dict.fromkeys(missing_elements)),
    }
    evidence_refs = _build_evidence_refs(
        raw, industry_code, industry_major_code, borrower_type
    )
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
            basis="；".join(
                (
                    *reasons,
                    *(
                        (farmer_registration_address_support,)
                        if farmer_registration_address_support
                        else ()
                    ),
                )
            ),
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
        basis=(
            f"{category}：经营性贷款且授信金额 {credit_amount_wan:g} 万元"
            f"不超过{limit:g}万元上限"
            + (
                f"；{farmer_registration_address_support}"
                if farmer_registration_address_support
                else ""
            )
        ),
        evidence_refs=evidence_refs,
        anomalies=anomalies,
        determination=determination,
    )


def parse_credit_amount_wan(value: object) -> float | None:
    """Parse the template credit amount to 万元, accepting 亿 and thousands separators."""
    return _parse_amount(value, allow_units=True)


def extract_approved_credit_amounts_wan(value: object) -> tuple[float, ...]:
    """Extract distinct explicit approved amounts from an approval opinion.

    Application amounts are ignored unless the same local phrase also contains
    an approval verb. Unitless numbers are deliberately rejected so dates,
    terms and rates cannot be mistaken for a credit amount.
    """
    text = _text(value)
    approved: list[float] = []
    for match in _APPROVED_AMOUNT_RE.finditer(text):
        clause_start = max(
            (text.rfind(separator, 0, match.start()) for separator in "，,；;。\n"),
            default=-1,
        )
        prefix = text[clause_start + 1 : match.start()].strip()
        nearby_prefix = prefix[-24:]
        has_approval_keyword = bool(_APPROVAL_KEYWORD_RE.search(nearby_prefix))
        has_credit_limit = "授信额度" in nearby_prefix[-16:]
        is_application_only = bool(_APPLICATION_AMOUNT_RE.search(nearby_prefix))
        if not has_approval_keyword and (not has_credit_limit or is_application_only):
            continue
        parsed = parse_credit_amount_wan(match.group(0))
        if parsed is not None and parsed not in approved:
            approved.append(parsed)
    return tuple(approved)


def resolve_credit_amount(
    structured_value: object, approval_opinion: object
) -> dict[str, object]:
    """Resolve the adopted credit amount and preserve source/conflict details."""
    structured_amount = parse_credit_amount_wan(structured_value)
    approval_amounts = list(extract_approved_credit_amounts_wan(approval_opinion))
    approval_amount = approval_amounts[0] if len(approval_amounts) == 1 else None
    if len(approval_amounts) > 1:
        return {
            "structured_amount_wan": structured_amount,
            "approval_amounts_wan": approval_amounts,
            "adopted_amount_wan": None,
            "source": "approval_opinion_multiple",
            "consistent": None,
            "conflict": False,
            "issue": "授信审批意见存在多个不同批复额度",
        }
    if structured_amount is not None and approval_amount is not None:
        consistent = structured_amount == approval_amount
        return {
            "structured_amount_wan": structured_amount,
            "approval_amounts_wan": approval_amounts,
            "adopted_amount_wan": structured_amount if consistent else None,
            "source": "structured_and_approval_consistent" if consistent else "conflict",
            "consistent": consistent,
            "conflict": not consistent,
            "issue": None if consistent else "结构化授信额度与审批意见批复额度冲突",
        }
    if structured_amount is not None:
        return {
            "structured_amount_wan": structured_amount,
            "approval_amounts_wan": approval_amounts,
            "adopted_amount_wan": structured_amount,
            "source": "structured",
            "consistent": None,
            "conflict": False,
            "issue": None,
        }
    if approval_amount is not None:
        return {
            "structured_amount_wan": None,
            "approval_amounts_wan": approval_amounts,
            "adopted_amount_wan": approval_amount,
            "source": "approval_opinion",
            "consistent": None,
            "conflict": False,
            "issue": None,
        }
    return {
        "structured_amount_wan": None,
        "approval_amounts_wan": [],
        "adopted_amount_wan": None,
        "source": "missing",
        "consistent": None,
        "conflict": False,
        "issue": "本次授信额度",
    }


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
    if "农户" in entity_type:
        return "farmer"
    if "个体工商户" in entity_type:
        return "individual_business"
    if "小微企业主" in entity_type:
        return "small_micro_owner"
    if "企业" in entity_type:
        return "enterprise"
    if any(_is_yes(raw[key]) for key in FARMER_FIELD_KEYS):
        return "farmer"
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


def _build_evidence_refs(
    raw: Mapping[str, str],
    industry_code: str | None,
    industry_major_code: str | None,
    borrower_type: str,
) -> list[dict[str, object]]:
    return [
        {"type": "field", "field_key": key, "raw_value": raw[key]}
        for key in (
            *_evidence_keys(),
            *(() if borrower_type != "farmer" else ("registered_address",)),
        )
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


def _farmer_registration_address_support(address: str) -> str:
    if not address:
        return "未填写注册地址，无法作为农户身份佐证"
    rural = re.search(r"村|乡|(?<!城关)镇", address)
    urban = re.search(r"城关镇|市辖区|市[^县乡镇村]{0,12}区", address)
    if rural and not urban:
        return f"注册地址“{address}”包含“{rural.group(0)}”，可作为农户身份的地址佐证"
    if urban and not rural:
        return f"注册地址“{address}”显示城区特征，未能作为农户身份的地址佐证"
    return f"注册地址“{address}”无法判断城乡特征，未能作为农户身份的地址佐证"


def _text(value: object) -> str:
    return str(value or "").strip()


def _is_yes(value: str) -> bool:
    return value.strip().lower() in {"是", "yes", "y", "true", "1"}
