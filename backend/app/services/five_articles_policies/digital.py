from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
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
from app.services.scenario_registry import DIGITAL_FINANCE_SCENARIO
from app.services.technology_finance_mapping_query import (
    FiveArticlesMappingLabel,
    FiveArticlesMappingLookupResult,
)


DIGITAL_FINANCE_DECISION_POLICY_VERSION = "digital-direction-v2"

DIGITAL_INDUSTRIALIZATION = "数字产业化"
INDUSTRIAL_DIGITALIZATION = "产业数字化"
DIGITAL_EFFICIENCY_IMPROVEMENT = "数字化效率提升"

_DIGITAL_INDUSTRIALIZATION_TIERS = frozenset(
    {
        "数字产业化",
        "数字产品制造业",
        "数字产品服务业",
        "数字技术应用业",
        "数字要素驱动业",
    }
)
_INDUSTRIAL_DIGITALIZATION_TIERS = frozenset(
    {
        "产业数字化",
        "智慧农业",
        "智能制造",
        "智能交通",
        "智慧物流",
        "数字金融",
        "数字商贸",
        "数字社会",
        "数字政府",
    }
)
_EFFICIENCY_TIERS = frozenset({"数字化效率提升", "数字化效率提升业"})

_DIRECTION_FIELDS = (
    "loan_purpose",
    "project_name",
    "project_content",
    "trade_goods_services",
)
_VAGUE_DIRECTION_TEXTS = frozenset(
    {
        "经营周转",
        "日常经营周转",
        "补充流动资金",
        "流动资金",
        "采购",
        "项目建设",
        "日常经营",
    }
)
_DIGITAL_DIRECTION_KEYWORDS = (
    "数字",
    "软件",
    "信息系统",
    "数据",
    "云计算",
    "人工智能",
    "物联网",
    "工业互联网",
    "平台",
    "智慧",
    "智能",
    "智能化",
    "线上",
    "电子商务",
    "电商",
    "自动化",
)
_CORE_COMPETITIVENESS_KEYWORDS = (
    "自研",
    "saas",
    "平台",
    "数字化业务订单",
    "产业链合作",
    "企业清单",
    "企业名录",
    "示范企业",
    "示范工厂",
    "数字业务收入",
    "技术团队",
    "数据运营",
)
_IP_POSITIVE_KEYWORDS = (
    "发明专利",
    "实用新型",
    "软件著作权",
    "软著",
    "集成电路布图",
)

AuxiliaryStatus = Literal["positive", "missing", "unrecognized"]


def normalize_digital_category(label: FiveArticlesMappingLabel) -> str:
    """Normalize the published digital taxonomy into the server-owned contract."""
    tier1 = _clean(label.tier1)
    tier2 = _clean(label.tier2)
    if tier1 in _DIGITAL_INDUSTRIALIZATION_TIERS:
        return DIGITAL_INDUSTRIALIZATION
    if tier1 in _INDUSTRIAL_DIGITALIZATION_TIERS:
        return INDUSTRIAL_DIGITALIZATION
    if tier1 in _EFFICIENCY_TIERS:
        if tier2 in _INDUSTRIAL_DIGITALIZATION_TIERS:
            return INDUSTRIAL_DIGITALIZATION
        return DIGITAL_EFFICIENCY_IMPROVEMENT
    raise ValueError(
        "数字金融映射标签无法归一："
        f"第一层={label.tier1!r}，第二层={label.tier2!r}"
    )


class DigitalFinancePolicy(FiveArticlesScenarioPolicy):
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
        direction_requires_review = _direction_requires_review(input_payload)
        enterprise_direction_conflict = bool(mapping_result.enterprise_labels)
        if mapping_result.status == "not_applicable" and (
            direction_requires_review or enterprise_direction_conflict
        ):
            if enterprise_direction_conflict and not direction_requires_review:
                basis = (
                    "企业侧命中数字金融，但该笔贷款实际投向未命中数字产业化或产业数字化；"
                    "企业属性与资金投向冲突，不自动认定数字金融，需人工复核。"
                )
                branch = "DIGITAL_ENTERPRISE_DIRECTION_CONFLICT"
            else:
                basis = (
                    "贷款用途、项目内容和交易品类不足以确定数字产业化或产业数字化投向，"
                    "不得以企业数字属性替代该笔贷款实际投向，需人工复核。"
                )
                branch = "DIGITAL_DIRECTION_EVIDENCE_INSUFFICIENT"
            return replace(
                resolution,
                terminal_result=TechnologyFinanceStageBResult(
                    labels=(),
                    consistency_status="needs_review",
                    consistency_basis=basis,
                    consistency_evidence_refs=tuple(
                        _direction_evidence_refs(input_payload)
                    ),
                    model_output={
                        "digital_decision": {
                            "digital_category": None,
                            "branch": branch,
                            "warnings": [basis],
                        }
                    },
                    result_status="needs_review",
                ),
            )
        return resolution

    def preclassify_stage_b(
        self,
        input_payload: Mapping[str, object],
        stage_a_result: StageAResult,
        enterprise_labels: Sequence[FiveArticlesMappingLabel],
        loan_direction_labels: Sequence[FiveArticlesMappingLabel],
    ) -> TechnologyFinanceStageBResult | None:
        del stage_a_result
        categories = tuple(
            dict.fromkeys(normalize_digital_category(label) for label in loan_direction_labels)
        )
        if not categories:
            return None
        if len(categories) != 1:
            raise ValueError(f"数字金融候选归一到多个互斥类别：{categories}")

        category = categories[0]
        auxiliary_refs, warnings = _auxiliary_evidence(input_payload)
        direction_refs = tuple(_direction_evidence_refs(input_payload))
        if category == DIGITAL_EFFICIENCY_IMPROVEMENT:
            basis = "数字化效率提升无法准确区分，暂不纳入统计"
            return TechnologyFinanceStageBResult(
                labels=(),
                consistency_status="not_applicable",  # type: ignore[arg-type]
                consistency_basis=basis,
                consistency_evidence_refs=(
                    _digital_direction_ref(loan_direction_labels[0], category),
                    *direction_refs,
                    *auxiliary_refs,
                ),
                model_output={
                    "digital_decision": {
                        "digital_category": category,
                        "branch": "DIGITAL_EFFICIENCY_NOT_INCLUDED",
                        "warnings": warnings,
                    }
                },
                result_status="not_applicable",
            )

        if (
            category == INDUSTRIAL_DIGITALIZATION
            and not _has_explicit_digital_means(input_payload)
        ):
            basis = (
                "贷款投向行业目录命中产业数字化，但贷款用途、项目内容和交易品类"
                "未说明数字技术或数字化手段，不自动认定数字金融，需人工复核。"
            )
            return TechnologyFinanceStageBResult(
                labels=(),
                consistency_status="needs_review",
                consistency_basis=basis,
                consistency_evidence_refs=(
                    _digital_direction_ref(loan_direction_labels[0], category),
                    *direction_refs,
                    *auxiliary_refs,
                ),
                model_output={
                    "digital_decision": {
                        "digital_category": category,
                        "branch": "INDUSTRIAL_DIGITALIZATION_MEANS_UNCLEAR",
                        "warnings": [basis, *warnings],
                    }
                },
                result_status="needs_review",
            )

        enterprise_categories = {
            normalize_digital_category(label)
            for label in enterprise_labels
        }
        consistency_status = (
            "consistent" if category in enterprise_categories else "inconsistent"
        )
        consistency_basis = (
            f"贷款实际投向命中{category}，按该笔资金投向认定为数字金融；"
            + (
                "企业侧数字类别与贷款投向一致。"
                if consistency_status == "consistent"
                else "企业侧未命中相同数字类别，但企业属性不覆盖明确的贷款投向。"
            )
            + (f" 辅助证据预警：{'；'.join(warnings)}。" if warnings else "")
        )
        labels = tuple(
            _server_label(label, category, input_payload)
            for label in loan_direction_labels
        )
        return TechnologyFinanceStageBResult(
            labels=labels,
            consistency_status=consistency_status,
            consistency_basis=consistency_basis,
            consistency_evidence_refs=(
                _digital_direction_ref(loan_direction_labels[0], category),
                *auxiliary_refs,
            ),
            model_output={
                "digital_decision": {
                    "digital_category": category,
                    "branch": "DIGITAL_DIRECTION_INCLUDED",
                    "enterprise_category_match": consistency_status == "consistent",
                    "warnings": warnings,
                }
            },
        )


def _server_label(
    label: FiveArticlesMappingLabel,
    category: str,
    input_payload: Mapping[str, object],
) -> dict[str, object]:
    return {
        "mapping_version_id": label.mapping_version_id,
        "source_row": label.source_row,
        "NEIC_Code": label.neic_code,
        "NEIC_Name": label.neic_name,
        "subject": label.subject,
        "taxonomy_path": list(label.taxonomy_path),
        "match_method": label.match_method,
        "digital_category": category,
        "decision_policy_version": DIGITAL_FINANCE_DECISION_POLICY_VERSION,
        "matching_basis": f"贷款实际投向命中{category}服务器归一规则。",
        "evidence_refs": [
            {
                "type": "mapping",
                "mapping_version_id": label.mapping_version_id,
                "source_row": label.source_row,
                "NEIC_Code": label.neic_code,
                "NEIC_Name": label.neic_name,
                "taxonomy_path": list(label.taxonomy_path),
            },
            *_direction_evidence_refs(input_payload),
        ],
    }


def _digital_direction_ref(
    label: FiveArticlesMappingLabel,
    category: str,
) -> dict[str, object]:
    return {
        "type": "digital_direction",
        "digital_category": category,
        "decision_policy_version": DIGITAL_FINANCE_DECISION_POLICY_VERSION,
        "mapping_version_id": label.mapping_version_id,
        "source_row": label.source_row,
        "NEIC_Code": label.neic_code,
        "NEIC_Name": label.neic_name,
        "taxonomy_path": list(label.taxonomy_path),
    }


def _direction_evidence_refs(
    input_payload: Mapping[str, object],
) -> list[dict[str, object]]:
    labels = {
        "loan_purpose": "贷款用途详细描述",
        "project_name": "对应项目名称",
        "project_content": "项目建设 / 运营内容",
        "trade_goods_services": "核心交易品类 / 服务内容",
    }
    return [
        {
            "type": "business",
            "field_key": field_key,
            "field_label": labels[field_key],
            "excerpt": value[:160],
        }
        for field_key in _DIRECTION_FIELDS
        if (value := _clean(input_payload.get(field_key)))
    ]


def _direction_requires_review(input_payload: Mapping[str, object]) -> bool:
    values = [
        _clean(input_payload.get(field_key))
        for field_key in _DIRECTION_FIELDS
        if _clean(input_payload.get(field_key))
    ]
    if not values or all(value in _VAGUE_DIRECTION_TEXTS for value in values):
        return True
    combined = " ".join(values).lower()
    return any(keyword in combined for keyword in _DIGITAL_DIRECTION_KEYWORDS)


def _has_explicit_digital_means(input_payload: Mapping[str, object]) -> bool:
    combined = " ".join(
        _clean(input_payload.get(field_key))
        for field_key in _DIRECTION_FIELDS
    ).lower()
    return any(keyword in combined for keyword in _DIGITAL_DIRECTION_KEYWORDS)


def _auxiliary_evidence(
    input_payload: Mapping[str, object],
) -> tuple[tuple[dict[str, object], ...], list[str]]:
    industry_position = _clean(input_payload.get("industry_position_competitiveness"))
    digital_core = _clean(input_payload.get("digital_core_competitiveness"))
    rd_ip = _clean(input_payload.get("rd_ip_info"))
    core_material = " ".join(value for value in (digital_core, industry_position) if value)

    refs: list[dict[str, object]] = []
    warnings: list[str] = []

    industry_warning = None if industry_position else "企业数字行业定位佐证不足"
    refs.append(
        _auxiliary_ref(
            role="industry_positioning",
            field_key="industry_position_competitiveness",
            field_label="企业行业定位与核心竞争力",
            value=industry_position,
            status="positive" if industry_position else "missing",
            warning=industry_warning,
        )
    )
    if industry_warning:
        warnings.append(industry_warning)

    core_status = _recognition_status(
        core_material,
        _CORE_COMPETITIVENESS_KEYWORDS,
    )
    core_warning = (
        None
        if core_status == "positive"
        else "企业数字化核心竞争力佐证不足"
    )
    refs.append(
        _auxiliary_ref(
            role="core_competitiveness",
            field_key=(
                "digital_core_competitiveness"
                if digital_core
                else "industry_position_competitiveness"
            ),
            field_label=(
                "数字核心竞争力"
                if digital_core
                else "企业行业定位与核心竞争力"
            ),
            value=digital_core or industry_position,
            status=core_status,
            warning=core_warning,
        )
    )
    if core_warning:
        warnings.append(core_warning)

    ip_status = _recognition_status(rd_ip, _IP_POSITIVE_KEYWORDS)
    ip_warning = (
        None
        if ip_status == "positive"
        else "知识产权佐证不足"
    )
    refs.append(
        _auxiliary_ref(
            role="rd_ip",
            field_key="rd_ip_info",
            field_label="研发与知识产权情况",
            value=rd_ip,
            status=ip_status,
            warning=ip_warning,
        )
    )
    if ip_warning:
        warnings.append(ip_warning)

    return tuple(refs), warnings


def _recognition_status(
    value: str,
    positive_keywords: Sequence[str],
) -> AuxiliaryStatus:
    if not value:
        return "missing"
    normalized = value.lower()
    if any(keyword in normalized for keyword in positive_keywords):
        return "positive"
    return "unrecognized"


def _auxiliary_ref(
    *,
    role: str,
    field_key: str,
    field_label: str,
    value: str,
    status: AuxiliaryStatus,
    warning: str | None,
) -> dict[str, object]:
    return {
        "type": "digital_auxiliary",
        "evidence_role": role,
        "field_key": field_key,
        "field_label": field_label,
        "excerpt": value[:160],
        "evidence_status": status,
        "warning": warning,
    }


def _clean(value: object) -> str:
    return " ".join(str(value or "").split())


DIGITAL_FINANCE_POLICY = DigitalFinancePolicy(
    scenario_id=DIGITAL_FINANCE_SCENARIO,
    decision_policy_version=DIGITAL_FINANCE_DECISION_POLICY_VERSION,
)
