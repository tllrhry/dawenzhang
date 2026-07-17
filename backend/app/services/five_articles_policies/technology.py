from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from decimal import Decimal, InvalidOperation
import re
from typing import Any, Literal

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.services.five_articles_policies.base import (
    FiveArticlesScenarioPolicy,
    MappingResolution,
)
from app.services.five_articles_stage_b_types import (
    StageAResult,
    TechnologyFinanceStageBResult,
)
from app.services.scenario_registry import TECHNOLOGY_FINANCE_SCENARIO
from app.services.technology_finance_ip_registry import (
    lookup_technology_finance_ip_registry_match,
)
from app.services.technology_finance_mapping_query import (
    FiveArticlesMappingLabel,
    FiveArticlesMappingLookupResult,
)


TECHNOLOGY_FINANCE_DECISION_POLICY_VERSION = "technology-direction-v3"
_RD_STAFF_THRESHOLD = Decimal("10")
_RD_INVESTMENT_RATIO_THRESHOLD = Decimal("3")
_RD_STAFF_FIELD = "rd_staff_ratio"
_RD_INVESTMENT_FIELD = "rd_investment"
_ANNUAL_REVENUE_FIELD = "annual_revenue"
_PATENT_FIELD = "patent_software_copyright_info"
_LEGACY_RD_FIELD = "rd_ip_info"
_CERTIFICATIONS_FIELD = "certifications"
_DIRECTION_FIELDS = (
    "loan_purpose",
    "project_name",
    "project_content",
    "trade_goods_services",
)

_IP_INTENSIVE_INDUSTRY_SUBJECTS = frozenset(
    {"知识产权（专利）密集型产业", "知识产权(专利)密集型产业"}
)
_QUALIFICATION_KEYWORDS = (
    "高新技术企业",
    "专精特新",
    "科技型中小企业",
    "技术先进型服务企业",
    "创新型中小企业",
    "科技企业",
)
_IP_KEYWORDS = (
    "发明专利",
    "实用新型",
    "外观设计专利",
    "专利",
    "软件著作权",
    "软著",
    "集成电路布图",
)
_NEGATIVE_TEXT = re.compile(r"^(无|没有|未有|不涉及|暂无)(相关)?(资质|认证|专利|软著|软件著作权|知识产权|成果)?[。.]?$")
_QUALIFICATION_NEGATIVE_PATTERN = re.compile(
    r"(?:无|没有|未取得|未获得|不具备)[^。；;\n]{0,100}"
    r"(?:任何)?(?:科创类|科技类|科技企业)?(?:资质|认证)"
)
_LEGACY_STAFF_PATTERN = re.compile(
    r"研发人员(?:数量)?(?:占比|比例)?[^，,；;\n]{0,20}?(-?\d+(?:\.\d+)?\s*%)"
)
_LEGACY_INVESTMENT_PATTERN = re.compile(
    r"研发投入[^，,；;\n]{0,20}?(-?\d+(?:\.\d+)?\s*(?:亿元|万元|万|元))"
)
_AMOUNT_PATTERN = re.compile(
    r"^([+-]?\d+(?:,\d{3})*(?:\.\d+)?)\s*(亿元|万元|万|元)?$"
)

MetricState = Literal["valid", "missing", "invalid"]
AuxiliaryStatus = Literal["satisfied", "unsatisfied", "unknown"]


@dataclass(frozen=True)
class ParsedMetric:
    raw_value: object
    normalized_value: Decimal | None
    state: MetricState
    detail: str | None = None


def parse_rd_staff_ratio(value: object) -> ParsedMetric:
    """Parse only an explicit, bounded percentage for R&D staff."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return ParsedMetric(value, None, "missing")
    if isinstance(value, bool):
        return ParsedMetric(value, None, "invalid", "布尔值不是有效百分比")
    if isinstance(value, (int, float, Decimal)):
        text = str(value)
    else:
        text = str(value).strip()
        if not text.endswith("%"):
            return ParsedMetric(value, None, "invalid", "研发人员占比必须填写明确百分比")
        text = text[:-1].strip()
    try:
        normalized = Decimal(text)
    except (InvalidOperation, ValueError):
        return ParsedMetric(value, None, "invalid", "研发人员占比必须为数值")
    if not normalized.is_finite() or normalized < 0 or normalized > 100:
        return ParsedMetric(value, None, "invalid", "研发人员占比必须在0%至100%之间")
    return ParsedMetric(value, normalized, "valid")


def parse_amount_wan(value: object) -> ParsedMetric:
    """Parse a non-negative money amount and normalize it to ten-thousand yuan."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return ParsedMetric(value, None, "missing")
    if isinstance(value, bool):
        return ParsedMetric(value, None, "invalid", "布尔值不是有效金额")
    text = str(value).strip().replace("人民币", "").replace(" ", "")
    match = _AMOUNT_PATTERN.fullmatch(text)
    if match is None:
        return ParsedMetric(value, None, "invalid", "金额必须为数值并使用元、万元或亿元单位")
    try:
        amount = Decimal(match.group(1).replace(",", ""))
    except InvalidOperation:
        return ParsedMetric(value, None, "invalid", "金额必须为有效数值")
    if not amount.is_finite() or amount < 0:
        return ParsedMetric(value, None, "invalid", "金额不得为负数")
    unit = match.group(2) or "万元"
    normalized = (
        amount * Decimal("10000")
        if unit == "亿元"
        else amount / Decimal("10000")
        if unit == "元"
        else amount
    )
    return ParsedMetric(value, normalized, "valid")


class TechnologyFinancePolicy(FiveArticlesScenarioPolicy):
    def resolve_mapping(
        self,
        session: Session,
        input_payload: dict[str, object],
        mapping_result: FiveArticlesMappingLookupResult,
        settings: Settings,
        *,
        condition_candidate_retriever: Callable[..., Any],
        condition_label_selector: Callable[..., Any],
    ) -> MappingResolution:
        resolution = super().resolve_mapping(
            session,
            input_payload,
            mapping_result,
            settings,
            condition_candidate_retriever=condition_candidate_retriever,
            condition_label_selector=condition_label_selector,
        )
        if mapping_result.status != "not_applicable":
            return resolution

        decision = _technology_decision(
            input_payload,
            mapping_result.enterprise_labels,
            (),
        )
        return replace(resolution, terminal_result=decision)

    def preclassify_stage_b(
        self,
        input_payload: Mapping[str, object],
        stage_a_result: StageAResult,
        enterprise_labels: Sequence[FiveArticlesMappingLabel],
        loan_direction_labels: Sequence[FiveArticlesMappingLabel],
    ) -> TechnologyFinanceStageBResult | None:
        del stage_a_result
        if not loan_direction_labels:
            return None
        # Every DOCX parsed through the current scenario schema contains these
        # keys, including old templates where their values are empty.  Keep the
        # pre-schema direct-call contract on the guarded model path so existing
        # anti-fabrication validation remains testable for historical payloads.
        if not any(
            field_key in input_payload
            for field_key in (
                _RD_STAFF_FIELD,
                _RD_INVESTMENT_FIELD,
                _PATENT_FIELD,
            )
        ):
            return None
        return _technology_decision(
            input_payload,
            enterprise_labels,
            loan_direction_labels,
        )

    def postprocess_labels(
        self,
        session: Session,
        input_payload: dict[str, object],
        labels: Sequence[Mapping[str, object]],
    ) -> list[dict[str, object]]:
        enterprise_name = input_payload.get("enterprise_name")
        display_name = (
            enterprise_name.strip() if isinstance(enterprise_name, str) else ""
        )
        display_name = display_name or "（未填写）"
        result_labels: list[dict[str, object]] = []
        for label in labels:
            result_label = dict(label)
            if result_label.get("subject") in _IP_INTENSIVE_INDUSTRY_SUBJECTS:
                match = lookup_technology_finance_ip_registry_match(
                    session,
                    enterprise_name if isinstance(enterprise_name, str) else None,
                )
                if match.matched:
                    result_label["ip_intensive_industry_status"] = "satisfied"
                    result_label["ip_intensive_industry_basis"] = (
                        f"企业名称『{display_name}』能在江苏省高新技术企业备案名单中匹配到"
                        f"（来源序号 {match.source_row}），知识产权（专利）密集型产业条件满足。"
                    )
                else:
                    result_label["ip_intensive_industry_status"] = "unsatisfied"
                    result_label["ip_intensive_industry_basis"] = (
                        f"企业名称『{display_name}』未能在江苏省高新技术企业备案名单中匹配到，"
                        "知识产权（专利）密集型产业条件不满足。"
                    )
            result_labels.append(result_label)
        return result_labels


def _technology_decision(
    input_payload: Mapping[str, object],
    enterprise_labels: Sequence[FiveArticlesMappingLabel],
    loan_direction_labels: Sequence[FiveArticlesMappingLabel],
) -> TechnologyFinanceStageBResult:
    auxiliary_refs, warnings, official_qualification_hit = _auxiliary_evidence(
        input_payload
    )
    enterprise_technology_hit = bool(enterprise_labels) or official_qualification_hit
    direction_hit = bool(loan_direction_labels)

    if direction_hit:
        consistency_status = (
            "consistent" if enterprise_technology_hit else "inconsistent"
        )
        branch = (
            "TECHNOLOGY_SUBJECT_AND_DIRECTION_HIT"
            if enterprise_technology_hit
            else "NON_TECHNOLOGY_SUBJECT_DIRECTION_HIT"
        )
        basis = (
            "贷款实际投向命中已发布科技金融映射，按该笔资金真实投向认定为科技金融；"
            + (
                "企业侧科技行业或官方科技资质形成主体佐证。"
                if enterprise_technology_hit
                else "企业侧未命中科技行业或官方科技资质，但主体属性不覆盖明确的科技投向。"
            )
        )
        result_status: Literal["completed", "not_applicable", "needs_review"] = (
            "completed"
        )
        labels = tuple(
            _server_label(label, input_payload) for label in loan_direction_labels
        )
    elif enterprise_technology_hit:
        consistency_status = "needs_review"
        branch = "TECHNOLOGY_SUBJECT_NON_TECHNOLOGY_DIRECTION"
        basis = (
            "企业侧命中科技行业或官方科技资质，但贷款实际投向未命中科技金融映射；"
            "主体属性与该笔资金投向冲突，不自动认定科技金融，需人工复核。"
        )
        result_status = "needs_review"
        labels = ()
    else:
        consistency_status = "not_applicable"  # type: ignore[assignment]
        branch = "NON_TECHNOLOGY_SUBJECT_AND_DIRECTION"
        basis = (
            "企业侧未命中科技行业或官方科技资质，贷款实际投向也未命中科技金融映射，"
            "不属于科技金融。"
        )
        result_status = "not_applicable"
        labels = ()

    if warnings:
        basis += f" 辅助证据预警：{'；'.join(warnings)}；预警不改变贷款投向主判。"
    else:
        basis += " 科技资质、研发与知识产权辅助证据完整。"

    direction_ref = _technology_direction_ref(
        loan_direction_labels[0] if loan_direction_labels else None,
        input_payload,
    )
    return TechnologyFinanceStageBResult(
        labels=labels,
        consistency_status=consistency_status,  # type: ignore[arg-type]
        consistency_basis=basis,
        consistency_evidence_refs=(direction_ref, *auxiliary_refs),
        model_output={
            "technology_decision": {
                "branch": branch,
                "direction_mapping_hit": direction_hit,
                "enterprise_mapping_hit": bool(enterprise_labels),
                "official_qualification_hit": official_qualification_hit,
                "warnings": warnings,
            }
        },
        result_status=result_status,
    )


def _auxiliary_evidence(
    input_payload: Mapping[str, object],
) -> tuple[tuple[dict[str, object], ...], list[str], bool]:
    legacy = _text(input_payload.get(_LEGACY_RD_FIELD))
    staff_raw: object = input_payload.get(_RD_STAFF_FIELD)
    if not _text(staff_raw) and legacy:
        match = _LEGACY_STAFF_PATTERN.search(legacy)
        staff_raw = match.group(1) if match else None
    investment_raw: object = input_payload.get(_RD_INVESTMENT_FIELD)
    if not _text(investment_raw) and legacy:
        match = _LEGACY_INVESTMENT_PATTERN.search(legacy)
        investment_raw = match.group(1) if match else None
    patent_raw: object = input_payload.get(_PATENT_FIELD)
    if not _text(patent_raw) and legacy:
        patent_raw = legacy

    qualification_text = _text(input_payload.get(_CERTIFICATIONS_FIELD))
    qualification_status = _qualification_status(qualification_text)
    qualification_warning = _status_warning(
        qualification_status,
        missing="未提供可识别的官方科技企业资质",
        unsatisfied="企业明确未持有官方科技企业资质",
    )

    staff = parse_rd_staff_ratio(staff_raw)
    staff_status: AuxiliaryStatus = (
        "satisfied"
        if staff.state == "valid"
        and staff.normalized_value is not None
        and staff.normalized_value >= _RD_STAFF_THRESHOLD
        else "unsatisfied"
        if staff.state == "valid"
        else "unknown"
    )
    staff_warning = (
        None
        if staff_status == "satisfied"
        else "研发人员占比低于10%参考阈值"
        if staff_status == "unsatisfied"
        else staff.detail or "未提供研发人员占比"
    )

    investment = parse_amount_wan(investment_raw)
    revenue = parse_amount_wan(input_payload.get(_ANNUAL_REVENUE_FIELD))
    derived_ratio: Decimal | None = None
    if (
        investment.state == "valid"
        and investment.normalized_value is not None
        and revenue.state == "valid"
        and revenue.normalized_value is not None
        and revenue.normalized_value > 0
    ):
        derived_ratio = (
            investment.normalized_value / revenue.normalized_value * Decimal("100")
        )
    investment_status: AuxiliaryStatus = (
        "satisfied"
        if derived_ratio is not None
        and derived_ratio >= _RD_INVESTMENT_RATIO_THRESHOLD
        else "unsatisfied"
        if derived_ratio is not None
        else "unknown"
    )
    investment_warning = (
        None
        if investment_status == "satisfied"
        else "研发投入占营收比例低于3%参考阈值"
        if investment_status == "unsatisfied"
        else investment.detail
        or revenue.detail
        or (
            "上年度营业收入必须大于0才能派生研发投入占比"
            if revenue.state == "valid"
            else "研发投入或上年度营业收入缺失，无法派生研发投入占比"
        )
    )

    patent_text = _text(patent_raw)
    patent_status = _text_status(patent_text, _IP_KEYWORDS)
    patent_warning = _status_warning(
        patent_status,
        missing="未提供可识别的专利或软著等知识产权佐证",
        unsatisfied="企业明确无专利或软著等知识产权成果",
    )

    refs = (
        {
            "type": "technology_auxiliary",
            "evidence_role": "official_qualification",
            "field_key": _CERTIFICATIONS_FIELD,
            "field_label": "企业核心资质与认证",
            "excerpt": qualification_text,
            "status": qualification_status,
            "warning": qualification_warning,
        },
        {
            "type": "technology_auxiliary",
            "evidence_role": "rd_staff_ratio",
            "field_key": _RD_STAFF_FIELD,
            "field_label": "研发人员占比",
            "excerpt": _text(staff_raw),
            "raw_value": staff.raw_value,
            "normalized_percent": _number(staff.normalized_value),
            "threshold_percent": 10,
            "status": staff_status,
            "warning": staff_warning,
        },
        {
            "type": "technology_auxiliary",
            "evidence_role": "rd_investment_ratio",
            "field_key": _RD_INVESTMENT_FIELD,
            "field_label": "研发投入占营收比例",
            "excerpt": _text(investment_raw),
            "raw_value": investment.raw_value,
            "normalized_amount_wan": _number(investment.normalized_value),
            "annual_revenue_raw": revenue.raw_value,
            "annual_revenue_wan": _number(revenue.normalized_value),
            "derived_ratio_percent": _number(derived_ratio),
            "threshold_percent": 3,
            "status": investment_status,
            "warning": investment_warning,
        },
        {
            "type": "technology_auxiliary",
            "evidence_role": "patent_software_copyright",
            "field_key": _PATENT_FIELD,
            "field_label": "专利或软著等",
            "excerpt": patent_text,
            "status": patent_status,
            "warning": patent_warning,
        },
    )
    warnings = [
        str(ref["warning"])
        for ref in refs
        if ref.get("warning")
    ]
    return refs, warnings, qualification_status == "satisfied"


def _server_label(
    label: FiveArticlesMappingLabel,
    input_payload: Mapping[str, object],
) -> dict[str, object]:
    evidence_refs: list[dict[str, object]] = [
        {
            "type": "mapping",
            "mapping_version_id": label.mapping_version_id,
            "source_row": label.source_row,
            "NEIC_Code": label.neic_code,
            "NEIC_Name": label.neic_name,
            "taxonomy_path": list(label.taxonomy_path),
        }
    ]
    for field_key in _DIRECTION_FIELDS:
        value = _text(input_payload.get(field_key))
        if value:
            evidence_refs.append(
                {
                    "type": "business",
                    "field_key": field_key,
                    "field_label": _field_label(field_key),
                    "excerpt": value,
                }
            )
    return {
        "mapping_version_id": label.mapping_version_id,
        "source_row": label.source_row,
        "NEIC_Code": label.neic_code,
        "NEIC_Name": label.neic_name,
        "subject": label.subject,
        "taxonomy_path": list(label.taxonomy_path),
        "matching_basis": "贷款实际投向命中已发布科技金融映射，由服务端确定性认定。",
        "evidence_refs": evidence_refs,
        "decision_policy_version": TECHNOLOGY_FINANCE_DECISION_POLICY_VERSION,
    }


def _technology_direction_ref(
    label: FiveArticlesMappingLabel | None,
    input_payload: Mapping[str, object],
) -> dict[str, object]:
    reference: dict[str, object] = {
        "type": "technology_direction",
        "mapping_hit": label is not None,
        "field_key": "loan_purpose",
        "field_label": "贷款用途详细描述",
        "excerpt": _text(input_payload.get("loan_purpose")),
    }
    if label is not None:
        reference.update(
            {
                "mapping_version_id": label.mapping_version_id,
                "source_row": label.source_row,
                "NEIC_Code": label.neic_code,
                "NEIC_Name": label.neic_name,
                "subject": label.subject,
                "taxonomy_path": list(label.taxonomy_path),
            }
        )
    return reference


def _text_status(text: str, positive_keywords: Sequence[str]) -> AuxiliaryStatus:
    if not text:
        return "unknown"
    if _NEGATIVE_TEXT.fullmatch(text):
        return "unsatisfied"
    if any(keyword in text for keyword in positive_keywords):
        return "satisfied"
    return "unknown"


def _qualification_status(text: str) -> AuxiliaryStatus:
    if not text:
        return "unknown"
    if _NEGATIVE_TEXT.fullmatch(text) or _QUALIFICATION_NEGATIVE_PATTERN.search(text):
        return "unsatisfied"
    return _text_status(text, _QUALIFICATION_KEYWORDS)


def _status_warning(
    status: AuxiliaryStatus,
    *,
    missing: str,
    unsatisfied: str,
) -> str | None:
    if status == "satisfied":
        return None
    return unsatisfied if status == "unsatisfied" else missing


def _field_label(field_key: str) -> str:
    return {
        "loan_purpose": "贷款用途详细描述",
        "project_name": "对应项目名称",
        "project_content": "项目建设 / 运营内容",
        "trade_goods_services": "贸易合同核心交易品类 / 服务内容",
    }[field_key]


def _text(value: object) -> str:
    return value.strip() if isinstance(value, str) else "" if value is None else str(value).strip()


def _number(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


TECHNOLOGY_FINANCE_POLICY = TechnologyFinancePolicy(
    scenario_id=TECHNOLOGY_FINANCE_SCENARIO,
    decision_policy_version=TECHNOLOGY_FINANCE_DECISION_POLICY_VERSION,
    narrows_loan_labels=False,
)
