from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
import re
from typing import Literal

from app.services.five_articles_policies.base import FiveArticlesScenarioPolicy
from app.services.five_articles_stage_b_types import (
    StageAResult,
    TechnologyFinanceStageBResult,
)
from app.services.scenario_registry import (
    PENSION_FINANCE_SCENARIO,
    ScenarioRegistration,
)
from app.services.technology_finance_mapping_query import FiveArticlesMappingLabel


PENSION_FINANCE_DECISION_POLICY_VERSION = "pension-direction-share-v2"
_THRESHOLD_PERCENT = Decimal("50")
_LOAN_SHARE_FIELD = "pension_loan_direction_share"
_REVENUE_SHARE_FIELD = "main_business_revenue_share"
_CERTIFICATIONS_FIELD = "certifications"
_PENSION_REVENUE_PERCENT_PATTERN = re.compile(
    r"养老[^，,；;\n]{0,40}?(-?\d+(?:\.\d+)?)\s*%"
)

PercentageState = Literal["valid", "missing", "invalid", "ambiguous"]


@dataclass(frozen=True)
class ParsedPercentage:
    raw_value: object
    normalized_percent: Decimal | None
    state: PercentageState
    detail: str | None = None

    @property
    def reaches_threshold(self) -> bool:
        return (
            self.state == "valid"
            and self.normalized_percent is not None
            and self.normalized_percent >= _THRESHOLD_PERCENT
        )


def parse_percentage(value: object) -> ParsedPercentage:
    """Parse an explicit percentage without silently coercing ambiguous text."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return ParsedPercentage(value, None, "missing")
    if isinstance(value, bool):
        return ParsedPercentage(value, None, "invalid", "布尔值不是有效比例")

    is_structured_number = isinstance(value, (int, float, Decimal))
    text = str(value).strip()
    has_percent_sign = text.endswith("%")
    numeric_text = text[:-1].strip() if has_percent_sign else text
    try:
        number = Decimal(numeric_text)
    except (InvalidOperation, ValueError):
        return ParsedPercentage(value, None, "invalid", "比例必须为数值")
    if not number.is_finite():
        return ParsedPercentage(value, None, "invalid", "比例必须为有限数值")

    if has_percent_sign:
        normalized = number
    elif is_structured_number and Decimal("0") <= number < Decimal("1"):
        normalized = number * Decimal("100")
    elif not is_structured_number and Decimal("0") < number < Decimal("1"):
        return ParsedPercentage(
            value,
            None,
            "ambiguous",
            "无百分号的小数文本无法确定表示百分数还是比例小数",
        )
    else:
        normalized = number

    if normalized < 0 or normalized > 100:
        return ParsedPercentage(value, None, "invalid", "比例必须在 0% 至 100% 之间")
    return ParsedPercentage(value, normalized, "valid")


class PensionFinancePolicy(FiveArticlesScenarioPolicy):
    def missing_enterprise_instruction(self) -> str:
        return (
            "企业侧未命中但贷款投向侧已命中时，应结合明确的贷款用途判为 "
            "inconsistent；"
        )

    def enterprise_labels_required_for_consistency(self) -> bool:
        return False

    def override_missing_enterprise_consistency(
        self,
        profile: ScenarioRegistration,
        *,
        business_evidence_is_insufficient: bool,
        enterprise_labels: Sequence[FiveArticlesMappingLabel],
        status: str,
        basis: str,
    ) -> tuple[str, str] | None:
        del status, basis
        if enterprise_labels or business_evidence_is_insufficient:
            return None
        return (
            "inconsistent",
            f"企业侧未命中已发布{profile.name}映射，贷款投向侧已命中{profile.name}标签，"
            "且贷款用途与投向依据明确，判定为不一致。",
        )

    def preclassify_stage_b(
        self,
        input_payload: Mapping[str, object],
        stage_a_result: StageAResult,
        enterprise_labels: Sequence[FiveArticlesMappingLabel],
        loan_direction_labels: Sequence[FiveArticlesMappingLabel],
    ) -> TechnologyFinanceStageBResult | None:
        del stage_a_result
        loan_share = parse_percentage(input_payload.get(_LOAN_SHARE_FIELD))
        revenue_share = parse_business_revenue_share(
            input_payload.get(_REVENUE_SHARE_FIELD)
        )

        # The loan-direction share is the primary matrix input.  Revenue share
        # is only a fallback when that primary share is missing, so ambiguity
        # in a revenue breakdown must not override an explicit loan share.
        invalid = []
        if loan_share.state in {"invalid", "ambiguous"}:
            invalid.append((_LOAN_SHARE_FIELD, loan_share))
        elif (
            loan_share.state == "missing"
            and revenue_share.state in {"invalid", "ambiguous"}
        ):
            invalid.append((_REVENUE_SHARE_FIELD, revenue_share))
        if invalid:
            details = "；".join(
                f"{_field_label(field_key)}：{parsed.detail}" for field_key, parsed in invalid
            )
            return self._decision(
                input_payload,
                loan_direction_labels,
                loan_share,
                revenue_share,
                matrix_branch="PENSION_REVIEW_INVALID_SHARE",
                result_status="needs_review",
                consistency_status="needs_review",
                basis=f"比例字段无法确定，需人工复核。{details}",
                qualifies=None,
            )

        enterprise_mapping_hit = bool(enterprise_labels)
        if loan_share.state == "valid":
            qualifies = loan_share.reaches_threshold
            branch = (
                "PENSION_ENTERPRISE_LOAN_SHARE_AT_LEAST_50"
                if enterprise_mapping_hit and qualifies
                else "PENSION_ENTERPRISE_LOAN_SHARE_BELOW_50"
                if enterprise_mapping_hit
                else "NON_PENSION_ENTERPRISE_LOAN_SHARE_AT_LEAST_50"
                if qualifies
                else "NON_PENSION_ENTERPRISE_LOAN_SHARE_BELOW_50"
            )
            normalized = _display_percent(loan_share)
            basis = (
                f"贷款实际投向已命中养老产业，养老投向占比为{normalized}，"
                f"{'达到' if qualifies else '未达到'}50%（含）阈值；"
                "按贷款实际投向优先规则判定。"
            )
        else:
            subject_basis = enterprise_mapping_hit or revenue_share.reaches_threshold
            qualifies = subject_basis
            if enterprise_mapping_hit:
                branch = "PENSION_ENTERPRISE_UNKNOWN_LOAN_SHARE"
                basis = (
                    "贷款实际投向已命中养老产业但养老投向占比未知；"
                    "企业侧命中养老产业映射，以主体养老属性辅助认定。"
                )
            elif revenue_share.reaches_threshold:
                branch = "PENSION_REVENUE_AT_LEAST_50_UNKNOWN_LOAN_SHARE"
                basis = (
                    "贷款实际投向已命中养老产业但养老投向占比未知；"
                    f"养老产业营业收入占比为{_display_percent(revenue_share)}，"
                    "达到50%（含），以主体养老属性辅助认定。"
                )
            else:
                branch = "NON_PENSION_SUBJECT_UNKNOWN_LOAN_SHARE"
                revenue_detail = (
                    f"养老产业营业收入占比为{_display_percent(revenue_share)}，未达到50%"
                    if revenue_share.state == "valid"
                    else "养老产业营业收入占比未知"
                )
                basis = (
                    "贷款实际投向已命中养老产业但养老投向占比未知；企业侧未命中养老产业映射，"
                    f"且{revenue_detail}，主体辅助条件不成立。"
                )

        return self._decision(
            input_payload,
            loan_direction_labels,
            loan_share,
            revenue_share,
            matrix_branch=branch,
            result_status="completed" if qualifies else "not_applicable",
            consistency_status=(
                "consistent" if enterprise_mapping_hit else "inconsistent"
            ),
            basis=basis,
            qualifies=qualifies,
        )

    def _decision(
        self,
        input_payload: Mapping[str, object],
        loan_direction_labels: Sequence[FiveArticlesMappingLabel],
        loan_share: ParsedPercentage,
        revenue_share: ParsedPercentage,
        *,
        matrix_branch: str,
        result_status: Literal["completed", "not_applicable", "needs_review"],
        consistency_status: Literal["consistent", "inconsistent", "needs_review"],
        basis: str,
        qualifies: bool | None,
    ) -> TechnologyFinanceStageBResult:
        qualification = str(input_payload.get(_CERTIFICATIONS_FIELD) or "").strip()
        warning = None if qualification else "未提供养老许可、备案或重点项目清单等辅助资质"
        refs = (
            _matrix_ref(_LOAN_SHARE_FIELD, loan_share, matrix_branch),
            _matrix_ref(_REVENUE_SHARE_FIELD, revenue_share, matrix_branch),
            {
                "type": "pension_qualification",
                "field_key": _CERTIFICATIONS_FIELD,
                "field_label": _field_label(_CERTIFICATIONS_FIELD),
                "excerpt": qualification,
                "warning": warning,
            },
        )
        labels = (
            tuple(_server_label(label, input_payload) for label in loan_direction_labels)
            if qualifies
            else ()
        )
        metadata = {
            "matrix_branch": matrix_branch,
            "qualifies": qualifies,
            "loan_direction_share": _parsed_payload(loan_share),
            "business_revenue_share": _parsed_payload(revenue_share),
            "enterprise_mapping_hit": consistency_status == "consistent",
            "qualification_warning": warning,
        }
        return TechnologyFinanceStageBResult(
            labels=labels,
            consistency_status=consistency_status,
            consistency_basis=basis + (f" 资质预警：{warning}；该预警不改变结论。" if warning else " 养老资质作为辅助正向佐证，不作为否决门槛。"),
            consistency_evidence_refs=refs,
            model_output={"pension_decision": metadata},
            result_status=result_status,
        )


def _server_label(
    label: FiveArticlesMappingLabel,
    input_payload: Mapping[str, object],
) -> dict[str, object]:
    evidence_refs = [
        {
            "type": "mapping",
            "mapping_version_id": label.mapping_version_id,
            "source_row": label.source_row,
            "NEIC_Code": label.neic_code,
            "NEIC_Name": label.neic_name,
            "taxonomy_path": list(label.taxonomy_path),
        }
    ]
    for field_key in ("loan_purpose", _LOAN_SHARE_FIELD, _REVENUE_SHARE_FIELD):
        value = str(input_payload.get(field_key) or "").strip()
        if value:
            evidence_refs.append(
                {
                    "type": "business",
                    "field_key": field_key,
                    "field_label": _field_label(field_key),
                    "excerpt": value[:160],
                }
            )
    return {
        "mapping_version_id": label.mapping_version_id,
        "source_row": label.source_row,
        "NEIC_Code": label.neic_code,
        "NEIC_Name": label.neic_name,
        "subject": label.subject,
        "taxonomy_path": list(label.taxonomy_path),
        "match_method": label.match_method,
        "matching_basis": "养老金融服务端投向占比矩阵认定。",
        "evidence_refs": evidence_refs,
    }


def parse_business_revenue_share(value: object) -> ParsedPercentage:
    """Extract one explicit养老 percentage from the reused主营构成 field."""
    parsed = parse_percentage(value)
    if parsed.state != "invalid" or not isinstance(value, str):
        return parsed
    matches = _PENSION_REVENUE_PERCENT_PATTERN.findall(value)
    if len(matches) == 1:
        extracted = parse_percentage(f"{matches[0]}%")
        return ParsedPercentage(
            raw_value=value,
            normalized_percent=extracted.normalized_percent,
            state=extracted.state,
            detail=extracted.detail,
        )
    if len(matches) > 1:
        return ParsedPercentage(
            value,
            None,
            "ambiguous",
            "主营业务及营收占比中存在多个养老比例，无法确定唯一值",
        )
    if "养老" not in value:
        return ParsedPercentage(
            value,
            None,
            "missing",
            "主营业务及营收占比未填写养老产业构成",
        )
    return ParsedPercentage(
        value,
        None,
        "ambiguous",
        "主营业务及营收占比提及养老产业但未明确对应比例",
    )


def _matrix_ref(
    field_key: str,
    parsed: ParsedPercentage,
    matrix_branch: str,
) -> dict[str, object]:
    return {
        "type": "pension_matrix",
        "field_key": field_key,
        "field_label": _field_label(field_key),
        "raw_value": parsed.raw_value,
        "normalized_percent": (
            float(parsed.normalized_percent)
            if parsed.normalized_percent is not None
            else None
        ),
        "parse_status": parsed.state,
        "matrix_branch": matrix_branch,
    }


def _parsed_payload(parsed: ParsedPercentage) -> dict[str, object]:
    return {
        "raw_value": parsed.raw_value,
        "normalized_percent": (
            float(parsed.normalized_percent)
            if parsed.normalized_percent is not None
            else None
        ),
        "parse_status": parsed.state,
        "detail": parsed.detail,
    }


def _display_percent(parsed: ParsedPercentage) -> str:
    assert parsed.normalized_percent is not None
    text = format(parsed.normalized_percent, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return f"{text}%"


def _field_label(field_key: str) -> str:
    return {
        _LOAN_SHARE_FIELD: "该笔贷款实际投向养老产业占总贷款额度比",
        _REVENUE_SHARE_FIELD: "主营业务及营收占比",
        _CERTIFICATIONS_FIELD: "企业核心资质与认证",
        "loan_purpose": "贷款用途详细描述",
    }[field_key]


PENSION_FINANCE_POLICY = PensionFinancePolicy(
    scenario_id=PENSION_FINANCE_SCENARIO,
    decision_policy_version=PENSION_FINANCE_DECISION_POLICY_VERSION,
)
