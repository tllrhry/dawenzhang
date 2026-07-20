from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.services.five_articles_policies.pension import (
    PENSION_FINANCE_POLICY,
    parse_business_revenue_share,
    parse_percentage,
)
from app.services.technology_finance_mapping_query import FiveArticlesMappingLabel


def _label(source_row: int = 12) -> FiveArticlesMappingLabel:
    return FiveArticlesMappingLabel(
        mapping_version_id=3,
        scenario_id="pension_finance",
        neic_code="8514",
        code_level=4,
        neic_name="老年人、残疾人养护服务",
        subject="养老产业",
        tier1="养老服务",
        tier2="机构养老",
        tier3=None,
        tier4=None,
        source_row=source_row,
    )


@pytest.mark.parametrize(
    ("raw", "state", "normalized"),
    [
        ("50", "valid", Decimal("50")),
        ("50%", "valid", Decimal("50")),
        (0.5, "valid", Decimal("50.0")),
        ("0.5", "ambiguous", None),
        ("", "missing", None),
        (None, "missing", None),
        ("-1%", "invalid", None),
        ("101", "invalid", None),
        ("约一半", "invalid", None),
    ],
)
def test_parse_percentage_contract(
    raw: object,
    state: str,
    normalized: Decimal | None,
) -> None:
    parsed = parse_percentage(raw)

    assert parsed.raw_value == raw
    assert parsed.state == state
    assert parsed.normalized_percent == normalized


@pytest.mark.parametrize(
    ("raw", "state", "normalized"),
    [
        ("养老服务占60%，物业管理占40%", "valid", Decimal("60")),
        ("物业管理占40%，养老服务占50%", "valid", Decimal("50")),
        ("养老服务占30%，养老用品占20%", "ambiguous", None),
        ("物业管理占100%", "missing", None),
    ],
)
def test_reused_main_business_share_extracts_explicit_pension_percentage(
    raw: str,
    state: str,
    normalized: Decimal | None,
) -> None:
    parsed = parse_business_revenue_share(raw)

    assert parsed.raw_value == raw
    assert parsed.state == state
    assert parsed.normalized_percent == normalized


@pytest.mark.parametrize(
    (
        "enterprise_hit",
        "loan_share",
        "revenue_share",
        "expected_status",
        "expected_branch",
    ),
    [
        (True, "50%", "", "completed", "PENSION_ENTERPRISE_LOAN_SHARE_AT_LEAST_50"),
        (True, "49.99%", "", "not_applicable", "PENSION_ENTERPRISE_LOAN_SHARE_BELOW_50"),
        (False, "50", "", "completed", "NON_PENSION_ENTERPRISE_LOAN_SHARE_AT_LEAST_50"),
        (False, "49", "80%", "not_applicable", "NON_PENSION_ENTERPRISE_LOAN_SHARE_BELOW_50"),
        (True, "", "", "completed", "PENSION_ENTERPRISE_UNKNOWN_LOAN_SHARE"),
        (False, "", "50%", "completed", "PENSION_REVENUE_AT_LEAST_50_UNKNOWN_LOAN_SHARE"),
        (False, "", "49.99%", "not_applicable", "NON_PENSION_SUBJECT_UNKNOWN_LOAN_SHARE"),
    ],
)
def test_pension_seven_cell_matrix(
    enterprise_hit: bool,
    loan_share: str,
    revenue_share: str,
    expected_status: str,
    expected_branch: str,
) -> None:
    label = _label()
    stage_a_result = SimpleNamespace(
        industry_name=(
            "老年人、残疾人养护服务" if enterprise_hit else "其他房屋建筑业"
        )
    )
    result = PENSION_FINANCE_POLICY.preclassify_stage_b(
        {
            "loan_purpose": "建设养老服务中心",
            "pension_loan_direction_share": loan_share,
            "main_business_revenue_share": revenue_share,
            "certifications": "民政部门养老机构备案",
        },
        stage_a_result,
        (label,) if enterprise_hit else (),
        (label,),
    )

    assert result is not None
    assert result.result_status == expected_status
    assert result.model_output["pension_decision"]["matrix_branch"] == expected_branch
    assert bool(result.labels) is (expected_status == "completed")


def test_direction_catalog_match_does_not_turn_non_pension_enterprise_into_pension_subject() -> None:
    label = _label()
    result = PENSION_FINANCE_POLICY.preclassify_stage_b(
        {
            "loan_purpose": "建设养老服务中心",
            "pension_loan_direction_share": "",
            "main_business_revenue_share": (
                "商品房、商业建筑土建施工83%；市政道路配套工程12%；"
                "建筑设备租赁劳务5%"
            ),
            "certifications": "建筑工程施工总承包一级资质",
        },
        SimpleNamespace(industry_name="其他房屋建筑业"),
        (label,),
        (label,),
    )

    assert result is not None
    assert result.result_status == "not_applicable"
    assert result.consistency_status == "inconsistent"
    assert result.labels == ()
    assert result.model_output["pension_decision"]["qualifies"] is False
    assert "企业行业不属于养老产业" in result.consistency_basis
    assert "不属于养老金融" in result.consistency_basis
    assert (
        result.model_output["pension_decision"]["matrix_branch"]
        == "NON_PENSION_SUBJECT_UNKNOWN_LOAN_SHARE"
    )


@pytest.mark.parametrize("field_value", ["0.5", "-1", "101%", "未知"])
def test_invalid_or_ambiguous_share_requires_review(field_value: str) -> None:
    label = _label()
    result = PENSION_FINANCE_POLICY.preclassify_stage_b(
        {
            "loan_purpose": "建设养老服务中心",
            "pension_loan_direction_share": field_value,
            "main_business_revenue_share": "",
        },
        SimpleNamespace(),
        (label,),
        (label,),
    )

    assert result is not None
    assert result.result_status == "needs_review"
    assert result.consistency_status == "needs_review"
    assert field_value in str(result.model_output)


@pytest.mark.parametrize(
    ("loan_share", "expected_status", "expected_branch"),
    [
        ("60%", "completed", "PENSION_ENTERPRISE_LOAN_SHARE_AT_LEAST_50"),
        ("40%", "not_applicable", "PENSION_ENTERPRISE_LOAN_SHARE_BELOW_50"),
    ],
)
def test_explicit_loan_share_takes_priority_over_ambiguous_revenue_breakdown(
    loan_share: str,
    expected_status: str,
    expected_branch: str,
) -> None:
    label = _label()
    result = PENSION_FINANCE_POLICY.preclassify_stage_b(
        {
            "loan_purpose": "建设养老服务中心",
            "pension_loan_direction_share": loan_share,
            "main_business_revenue_share": (
                "1. 机构养老服务：65% "
                "2. 社区居家养老及政府购买服务：25% "
                "3. 适老化产品研发与销售：10%"
            ),
            "certifications": "民政部门养老机构备案",
        },
        SimpleNamespace(),
        (label,),
        (label,),
    )

    assert result is not None
    assert result.result_status == expected_status
    assert result.model_output["pension_decision"]["matrix_branch"] == expected_branch
    assert result.consistency_status == "consistent"
    assert loan_share in result.consistency_basis


def test_ambiguous_revenue_breakdown_requires_review_when_loan_share_is_missing() -> None:
    label = _label()
    result = PENSION_FINANCE_POLICY.preclassify_stage_b(
        {
            "loan_purpose": "建设养老服务中心",
            "pension_loan_direction_share": "",
            "main_business_revenue_share": "养老服务占65%，养老用品占35%",
        },
        SimpleNamespace(),
        (),
        (label,),
    )

    assert result is not None
    assert result.result_status == "needs_review"
    assert result.consistency_status == "needs_review"
    assert "主营业务及营收占比" in result.consistency_basis


def test_pension_enterprise_identity_takes_priority_over_ambiguous_revenue_breakdown() -> None:
    label = _label()
    result = PENSION_FINANCE_POLICY.preclassify_stage_b(
        {
            "loan_purpose": "扩建社区医养综合体",
            "pension_loan_direction_share": "",
            "main_business_revenue_share": (
                "机构养老服务65%；社区居家养老服务25%；适老化产品销售10%"
            ),
            "certifications": "养老服务标准化试点单位",
        },
        SimpleNamespace(industry_name="老年人、残疾人养护服务"),
        (label,),
        (label,),
    )

    assert result is not None
    assert result.result_status == "completed"
    assert result.consistency_status == "consistent"
    assert result.labels
    assert (
        result.model_output["pension_decision"]["matrix_branch"]
        == "PENSION_ENTERPRISE_UNKNOWN_LOAN_SHARE"
    )


def test_missing_qualification_warns_without_changing_positive_decision() -> None:
    label = _label()
    result = PENSION_FINANCE_POLICY.preclassify_stage_b(
        {
            "loan_purpose": "建设养老服务中心",
            "pension_loan_direction_share": "75%",
            "main_business_revenue_share": "",
            "certifications": "",
        },
        SimpleNamespace(),
        (),
        (label,),
    )

    assert result is not None
    assert result.result_status == "completed"
    assert "不改变结论" in result.consistency_basis
    qualification_ref = result.consistency_evidence_refs[-1]
    assert qualification_ref["type"] == "pension_qualification"
    assert qualification_ref["warning"]
