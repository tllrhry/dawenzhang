from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from typing import Any, Literal

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.services.five_articles_policies.base import (
    FiveArticlesScenarioPolicy,
    MappingResolution,
)
from app.services.five_articles_stage_b_types import TechnologyFinanceStageBResult
from app.services.green_finance_condition_matching import (
    ConditionSide,
    build_green_finance_condition_evidence,
    condition_candidates_from_labels,
)
from app.services.scenario_registry import GREEN_FINANCE_SCENARIO
from app.services.technology_finance_mapping_query import (
    FiveArticlesMappingLabel,
    FiveArticlesMappingLookupResult,
)


GREEN_FINANCE_DECISION_POLICY_VERSION = "green-direction-v3"

EnvironmentalViolationStatus = Literal["yes", "no", "unknown"]

_AUXILIARY_FIELDS = (
    (
        "green_certifications",
        "环保与绿色资质认证",
        "green_qualification",
        "缺少绿色资质",
    ),
    (
        "energy_saving_pollution_control",
        "节能减排 / 污染治理内容",
        "energy_saving_pollution_control",
        "缺少节能减排/污染治理内容",
    ),
    (
        "carbon_environmental_benefits",
        "碳排放与环境效益",
        "carbon_environmental_benefits",
        "无量化环境效益佐证",
    ),
)


class GreenFinancePolicy(FiveArticlesScenarioPolicy):
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
        enterprise_labels = self._resolve_side(
            session,
            input_payload,
            "enterprise",
            mapping_result.enterprise_labels,
            settings,
            condition_candidate_retriever,
            condition_label_selector,
        )
        loan_labels = self._resolve_side(
            session,
            input_payload,
            "loan_direction",
            mapping_result.loan_direction_labels,
            settings,
            condition_candidate_retriever,
            condition_label_selector,
        )
        if not loan_labels:
            return MappingResolution(
                replace(
                    mapping_result,
                    status="not_applicable",
                    enterprise_labels=enterprise_labels,
                    loan_direction_labels=(),
                    detail="green_finance_condition_no_match",
                ),
                not_applicable_basis=(
                    "贷款投向的行业编码候选及全库条件/标准均未与案例业务证据形成可靠匹配，"
                    "绿色金融判定不适用。"
                ),
                not_applicable_error_detail="green_finance_condition_no_match",
            )
        resolved_mapping = replace(
            mapping_result,
            status="mapping_hit",
            enterprise_labels=enterprise_labels,
            loan_direction_labels=loan_labels,
            detail="green_finance_condition_validated_mapping_hit",
        )
        return MappingResolution(
            resolved_mapping,
            terminal_result=_green_decision(
                input_payload,
                enterprise_labels,
                loan_labels,
            ),
        )

    @staticmethod
    def _resolve_side(
        session: Session,
        input_payload: dict[str, object],
        side: ConditionSide,
        explicit_labels: tuple[FiveArticlesMappingLabel, ...],
        settings: Settings,
        candidate_retriever: Callable[..., Any],
        label_selector: Callable[..., Any],
    ) -> tuple[FiveArticlesMappingLabel, ...]:
        evidence_text = build_green_finance_condition_evidence(input_payload, side)
        explicit_candidates = condition_candidates_from_labels(explicit_labels)
        if explicit_candidates:
            selected = label_selector(explicit_candidates, evidence_text, settings)
            if selected is not None:
                return (replace(selected, match_method="neic_code"),)

        candidates = candidate_retriever(session, input_payload, side, settings)
        if not candidates:
            return ()
        selected = label_selector(candidates, evidence_text, settings)
        if selected is None:
            return ()
        return (replace(selected, match_method="condition_fallback"),)


def parse_major_environmental_violation(value: object) -> EnvironmentalViolationStatus:
    """Normalize explicit major environmental violation disclosure."""
    text = _clean(value)
    if not text or text in {"未知", "不详", "待核验", "待确认", "无法确认", "未提供"}:
        return "unknown"
    if text in {"无", "否", "没有", "不存在", "未发生", "未发现", "无此情况"}:
        return "no"
    if any(
        phrase in text
        for phrase in (
            "无重大环保违法",
            "没有重大环保违法",
            "不存在重大环保违法",
            "未发生重大环保违法",
            "未发现重大环保违法",
            "无环保失信",
            "没有环保失信",
            "不存在环保失信",
            "未发现环保失信",
        )
    ):
        return "no"
    if text in {"有", "是", "存在"} or any(
        phrase in text
        for phrase in ("存在重大环保违法", "有重大环保违法", "环保失信", "重大环境违法")
    ):
        return "yes"
    return "unknown"


def _green_decision(
    input_payload: Mapping[str, object],
    enterprise_labels: Sequence[FiveArticlesMappingLabel],
    loan_direction_labels: Sequence[FiveArticlesMappingLabel],
) -> TechnologyFinanceStageBResult:
    violation_raw = input_payload.get("major_environmental_violation")
    violation_status = parse_major_environmental_violation(violation_raw)
    auxiliary_refs, warnings = _auxiliary_evidence(input_payload)
    violation_warning = (
        "存在重大环保违法失信，需开展人工尽职调查并核验潜在漂绿风险"
        if violation_status == "yes"
        else "重大环保违法失信信息未知，需补充核验"
        if violation_status == "unknown"
        else None
    )
    if violation_warning:
        warnings.append(violation_warning)

    direction_ref = _green_direction_ref(loan_direction_labels[0])
    violation_ref = {
        "type": "green_violation",
        "field_key": "major_environmental_violation",
        "field_label": "重大环保违法失信情况",
        "raw_value": violation_raw,
        "excerpt": _clean(violation_raw),
        "violation_status": violation_status,
        "warning": violation_warning,
    }
    enterprise_hit = bool(enterprise_labels)
    labels = tuple(_server_label(label, input_payload) for label in loan_direction_labels)
    if violation_status == "yes":
        basis = (
            "贷款实际投向已命中当前发布的绿色目录，但输入明确存在重大环保违法失信；"
            "系统不自动形成最终绿色结论，转人工尽职调查并保留潜在漂绿证据。"
        )
        status = "needs_review"
        consistency_status = "needs_review"
        branch = "GREEN_DIRECTION_HIT_ENVIRONMENTAL_VIOLATION_REVIEW"
    else:
        consistency_status = "consistent" if enterprise_hit else "inconsistent"
        basis = (
            "贷款实际投向已命中当前发布的绿色目录，按该笔资金实际投向认定为绿色金融；"
            + (
                "企业侧同时命中绿色目录，企业属性与贷款投向一致。"
                if enterprise_hit
                else "企业侧未命中绿色目录，但企业属性不覆盖明确的贷款实际投向。"
            )
            + (
                f" 辅助证据预警：{'；'.join(warnings)}；"
                "上述预警不改变绿色投向结论。"
                if warnings
                else ""
            )
        )
        status = "completed"
        branch = "GREEN_DIRECTION_INCLUDED"

    return TechnologyFinanceStageBResult(
        labels=labels,
        consistency_status=consistency_status,
        consistency_basis=basis,
        consistency_evidence_refs=(direction_ref, *auxiliary_refs, violation_ref),
        model_output={
            "green_decision": {
                "branch": branch,
                "enterprise_mapping_hit": enterprise_hit,
                "violation_status": violation_status,
                "warnings": warnings,
                "decision_policy_version": GREEN_FINANCE_DECISION_POLICY_VERSION,
            }
        },
        result_status=status,
    )


def _server_label(
    label: FiveArticlesMappingLabel,
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
        "decision_policy_version": GREEN_FINANCE_DECISION_POLICY_VERSION,
        "matching_basis": "贷款实际投向命中当前发布的两大绿色目录服务端映射。",
        "evidence_refs": [
            {
                "type": "mapping",
                "mapping_version_id": label.mapping_version_id,
                "source_row": label.source_row,
                "NEIC_Code": label.neic_code,
                "NEIC_Name": label.neic_name,
                "taxonomy_path": list(label.taxonomy_path),
                "match_method": label.match_method,
                "condition_criteria": label.condition_criteria,
            },
            *_business_evidence_refs(input_payload),
        ],
    }


def _green_direction_ref(label: FiveArticlesMappingLabel) -> dict[str, object]:
    return {
        "type": "green_direction",
        "mapping_version_id": label.mapping_version_id,
        "source_row": label.source_row,
        "NEIC_Code": label.neic_code,
        "NEIC_Name": label.neic_name,
        "subject": label.subject,
        "taxonomy_path": list(label.taxonomy_path),
        "match_method": label.match_method,
        "condition_criteria": label.condition_criteria,
        "decision_policy_version": GREEN_FINANCE_DECISION_POLICY_VERSION,
    }


def _auxiliary_evidence(
    input_payload: Mapping[str, object],
) -> tuple[tuple[dict[str, object], ...], list[str]]:
    refs: list[dict[str, object]] = []
    warnings: list[str] = []
    for field_key, field_label, role, missing_warning in _AUXILIARY_FIELDS:
        value = _clean(input_payload.get(field_key))
        warning = None if value else missing_warning
        refs.append(
            {
                "type": "green_auxiliary",
                "evidence_role": role,
                "field_key": field_key,
                "field_label": field_label,
                "excerpt": value,
                "evidence_status": "provided" if value else "missing",
                "warning": warning,
            }
        )
        if warning:
            warnings.append(warning)
    return tuple(refs), warnings


def _business_evidence_refs(
    input_payload: Mapping[str, object],
) -> list[dict[str, object]]:
    labels = {
        "loan_purpose": "贷款用途详细描述",
        "green_project_name": "对应绿色项目名称",
        "project_content": "项目建设 / 运营内容",
        "trade_goods_services": "核心交易品类 / 服务内容",
    }
    return [
        {
            "type": "business",
            "field_key": field_key,
            "field_label": field_label,
            "excerpt": value[:160],
        }
        for field_key, field_label in labels.items()
        if (value := _clean(input_payload.get(field_key)))
    ]


def _clean(value: object) -> str:
    return " ".join(str(value or "").split())


GREEN_FINANCE_POLICY = GreenFinancePolicy(
    scenario_id=GREEN_FINANCE_SCENARIO,
    decision_policy_version=GREEN_FINANCE_DECISION_POLICY_VERSION,
)
