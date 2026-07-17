from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.core.config import Settings
from app.services.five_articles_policies.technology import (
    TECHNOLOGY_FINANCE_DECISION_POLICY_VERSION,
    TECHNOLOGY_FINANCE_POLICY,
    parse_amount_wan,
    parse_rd_staff_ratio,
)
from app.services.scenario_registry import TECHNOLOGY_FINANCE_REGISTRATION
from app.services.technology_finance_classification_workflow import (
    _build_stage_b_result,
)
from app.services.technology_finance_mapping_query import (
    FiveArticlesMappingLabel,
    FiveArticlesMappingLookupResult,
)
from app.services.technology_finance_stage_b import classify_five_articles_stage_b


def _label(source_row: int = 18) -> FiveArticlesMappingLabel:
    return FiveArticlesMappingLabel(
        mapping_version_id=7,
        scenario_id="technology_finance",
        neic_code="3973",
        code_level=4,
        neic_name="集成电路制造",
        subject="科技产业",
        tier1="新一代信息技术产业",
        tier2="电子核心产业",
        tier3="集成电路",
        tier4=None,
        source_row=source_row,
    )


def _input(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "enterprise_name": "科技测试企业",
        "loan_purpose": "建设集成电路研发与生产线",
        "project_name": "芯片研发生产项目",
        "project_content": "建设研发实验室和集成电路生产线",
        "trade_goods_services": "集成电路设计与制造服务",
        "certifications": "高新技术企业、专精特新企业",
        "rd_staff_ratio": "10%",
        "rd_investment": "300万元",
        "annual_revenue": "10000万元",
        "patent_software_copyright_info": "拥有发明专利3项、软件著作权2项",
        "rd_ip_info": "",
    }
    payload.update(overrides)
    return payload


def _not_applicable_mapping(*, enterprise_hit: bool) -> FiveArticlesMappingLookupResult:
    return FiveArticlesMappingLookupResult(
        status="not_applicable",
        mapping_version_id=7,
        mapping_version=4,
        enterprise_labels=(_label(),) if enterprise_hit else (),
        loan_direction_labels=(),
        detail="loan_direction_has_no_explicit_mapping",
    )


@pytest.mark.parametrize(
    ("enterprise_hit", "certifications", "direction_hit", "expected_status", "expected_consistency", "expected_branch"),
    [
        (True, "高新技术企业", True, "completed", "consistent", "TECHNOLOGY_SUBJECT_AND_DIRECTION_HIT"),
        (False, "高新技术企业", True, "completed", "consistent", "TECHNOLOGY_SUBJECT_AND_DIRECTION_HIT"),
        (False, "无", True, "completed", "inconsistent", "NON_TECHNOLOGY_SUBJECT_DIRECTION_HIT"),
        (True, "无", False, "needs_review", "needs_review", "TECHNOLOGY_SUBJECT_NON_TECHNOLOGY_DIRECTION"),
        (False, "科技型中小企业", False, "needs_review", "needs_review", "TECHNOLOGY_SUBJECT_NON_TECHNOLOGY_DIRECTION"),
        (False, "无", False, "not_applicable", "not_applicable", "NON_TECHNOLOGY_SUBJECT_AND_DIRECTION"),
        (False, "", True, "completed", "inconsistent", "NON_TECHNOLOGY_SUBJECT_DIRECTION_HIT"),
    ],
)
def test_technology_finance_seven_business_matrix_cells(
    enterprise_hit: bool,
    certifications: str,
    direction_hit: bool,
    expected_status: str,
    expected_consistency: str,
    expected_branch: str,
) -> None:
    if direction_hit:
        decision = TECHNOLOGY_FINANCE_POLICY.preclassify_stage_b(
            _input(certifications=certifications),
            SimpleNamespace(),
            (_label(),) if enterprise_hit else (),
            (_label(),),
        )
        assert decision is not None
    else:
        resolution = TECHNOLOGY_FINANCE_POLICY.resolve_mapping(
            MagicMock(),
            _input(certifications=certifications),
            _not_applicable_mapping(enterprise_hit=enterprise_hit),
            Settings(_env_file=None),
            condition_candidate_retriever=MagicMock(),
            condition_label_selector=MagicMock(),
        )
        decision = resolution.terminal_result
        assert decision is not None

    assert decision.result_status == expected_status
    assert decision.consistency_status == expected_consistency
    assert decision.model_output["technology_decision"]["branch"] == expected_branch
    assert bool(decision.labels) is direction_hit


@pytest.mark.parametrize(
    ("raw", "state", "normalized"),
    [
        ("10%", "valid", Decimal("10")),
        ("9.99%", "valid", Decimal("9.99")),
        (10, "valid", Decimal("10")),
        ("10", "invalid", None),
        ("-1%", "invalid", None),
        ("101%", "invalid", None),
        ("研发人员较多", "invalid", None),
        ("", "missing", None),
    ],
)
def test_rd_staff_ratio_strict_parser(
    raw: object,
    state: str,
    normalized: Decimal | None,
) -> None:
    parsed = parse_rd_staff_ratio(raw)
    assert parsed.state == state
    assert parsed.normalized_value == normalized


@pytest.mark.parametrize(
    ("raw", "state", "normalized"),
    [
        ("300万元", "valid", Decimal("300")),
        ("1亿元", "valid", Decimal("10000")),
        ("10000元", "valid", Decimal("1")),
        (300, "valid", Decimal("300")),
        ("-1万元", "invalid", None),
        ("约300万元", "invalid", None),
        ("", "missing", None),
    ],
)
def test_rd_investment_strict_parser(
    raw: object,
    state: str,
    normalized: Decimal | None,
) -> None:
    parsed = parse_amount_wan(raw)
    assert parsed.state == state
    assert parsed.normalized_value == normalized


@pytest.mark.parametrize(
    ("staff_ratio", "rd_investment", "revenue", "expected_staff", "expected_investment"),
    [
        ("10%", "300万元", "10000万元", "satisfied", "satisfied"),
        ("9.99%", "299万元", "10000万元", "unsatisfied", "unsatisfied"),
        ("-1%", "-1万元", "10000万元", "unknown", "unknown"),
        ("", "300万元", "", "unknown", "unknown"),
    ],
)
def test_auxiliary_thresholds_and_invalid_values_do_not_override_direction(
    staff_ratio: str,
    rd_investment: str,
    revenue: str,
    expected_staff: str,
    expected_investment: str,
) -> None:
    decision = TECHNOLOGY_FINANCE_POLICY.preclassify_stage_b(
        _input(
            rd_staff_ratio=staff_ratio,
            rd_investment=rd_investment,
            annual_revenue=revenue,
        ),
        SimpleNamespace(),
        (),
        (_label(),),
    )

    assert decision is not None
    assert decision.result_status == "completed"
    refs = {
        ref["evidence_role"]: ref
        for ref in decision.consistency_evidence_refs
        if ref.get("type") == "technology_auxiliary"
    }
    assert refs["rd_staff_ratio"]["status"] == expected_staff
    assert refs["rd_investment_ratio"]["status"] == expected_investment
    if expected_investment == "satisfied":
        assert refs["rd_investment_ratio"]["derived_ratio_percent"] == 3.0


def test_legacy_combined_rd_field_is_parsed_as_auxiliary_fallback() -> None:
    decision = TECHNOLOGY_FINANCE_POLICY.preclassify_stage_b(
        _input(
            rd_staff_ratio="",
            rd_investment="",
            patent_software_copyright_info="",
            rd_ip_info="研发人员占比12%，研发投入400万元，拥有软件著作权5项",
        ),
        SimpleNamespace(),
        (),
        (_label(),),
    )

    assert decision is not None
    refs = {
        ref["evidence_role"]: ref
        for ref in decision.consistency_evidence_refs
        if ref.get("type") == "technology_auxiliary"
    }
    assert refs["rd_staff_ratio"]["normalized_percent"] == 12.0
    assert refs["rd_investment_ratio"]["derived_ratio_percent"] == 4.0
    assert refs["patent_software_copyright"]["status"] == "satisfied"


def test_negative_qualification_enumeration_is_not_a_false_positive() -> None:
    decision = TECHNOLOGY_FINANCE_POLICY.preclassify_stage_b(
        _input(
            certifications=(
                "仅普通工商营业执照；无高新技术企业、科技型中小企业、"
                "专精特新、企业研发中心等任何科创类资质"
            )
        ),
        SimpleNamespace(),
        (),
        (_label(),),
    )

    assert decision is not None
    qualification = next(
        ref
        for ref in decision.consistency_evidence_refs
        if ref.get("evidence_role") == "official_qualification"
    )
    assert qualification["status"] == "unsatisfied"
    assert qualification["warning"] == "企业明确未持有官方科技企业资质"
    assert decision.consistency_status == "inconsistent"


def test_workflow_uses_server_owned_technology_decision_before_model_call() -> None:
    mapping_result = FiveArticlesMappingLookupResult(
        status="mapping_hit",
        mapping_version_id=7,
        mapping_version=4,
        enterprise_labels=(),
        loan_direction_labels=(_label(),),
        detail="loan_direction_mapping_hit",
    )
    session = MagicMock()
    session.scalar.return_value = None
    case = SimpleNamespace(
        id=21,
        scenario="technology_finance",
        input_payload=_input(),
    )
    stage_a = SimpleNamespace(
        id=31,
        case_id=21,
        industry_code="3011",
        industry_major_code="30",
        industry_middle_code="301",
        industry_name="水泥制造",
        rationale="企业主营水泥制造",
        loan_industry_code="3973",
        loan_industry_major_code="39",
        loan_industry_middle_code="397",
        loan_industry_name="集成电路制造",
        loan_matching_basis="贷款建设集成电路研发生产线",
    )

    result = _build_stage_b_result(
        session,
        case,
        stage_a,
        mapping_result,
        Settings(_env_file=None),
        TECHNOLOGY_FINANCE_REGISTRATION,
        MagicMock(side_effect=AssertionError("科技确定性规则不应调用标签选择模型")),
        classify_five_articles_stage_b,
        MagicMock(),
        MagicMock(),
    )

    assert result.status == "completed"
    assert result.decision_policy_version == TECHNOLOGY_FINANCE_DECISION_POLICY_VERSION
    assert result.labels[0]["decision_policy_version"] == TECHNOLOGY_FINANCE_DECISION_POLICY_VERSION
    assert result.consistency_status == "consistent"
