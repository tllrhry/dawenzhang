from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.core.config import Settings
from app.services.five_articles_policies.digital import (
    DIGITAL_EFFICIENCY_IMPROVEMENT,
    DIGITAL_FINANCE_POLICY,
    DIGITAL_INDUSTRIALIZATION,
    INDUSTRIAL_DIGITALIZATION,
    normalize_digital_category,
)
from app.services.five_articles_stage_b_types import TechnologyFinanceStageBError
from app.services.scenario_registry import DIGITAL_FINANCE_REGISTRATION
from app.services.technology_finance_mapping_query import (
    FiveArticlesMappingLabel,
    FiveArticlesMappingLookupResult,
)
from app.services.technology_finance_classification_workflow import (
    _build_stage_b_result,
)
from app.services.technology_finance_stage_b import classify_five_articles_stage_b


def _label(
    *,
    tier1: str,
    tier2: str | None = None,
    scenario_id: str = "digital_finance",
    source_row: int = 2,
) -> FiveArticlesMappingLabel:
    return FiveArticlesMappingLabel(
        mapping_version_id=7,
        scenario_id=scenario_id,
        neic_code="6513",
        code_level=4,
        neic_name="应用软件开发",
        subject="数字经济及其核心产业",
        tier1=tier1,
        tier2=tier2,
        tier3=None,
        tier4=None,
        source_row=source_row,
    )


def _stage_a() -> SimpleNamespace:
    return SimpleNamespace(
        id=11,
        industry_code="3011",
        industry_major_code="30",
        industry_name="水泥制造",
        rationale="企业主营传统制造业",
        loan_industry_code="6513",
        loan_industry_major_code="65",
        loan_industry_name="应用软件开发",
        loan_matching_basis="贷款用于工业软件项目",
    )


@pytest.mark.parametrize(
    ("tier1", "tier2", "expected"),
    [
        ("数字产品制造业", "计算机制造", DIGITAL_INDUSTRIALIZATION),
        ("数字产品服务业", "数字产品批发", DIGITAL_INDUSTRIALIZATION),
        ("数字技术应用业", "软件开发", DIGITAL_INDUSTRIALIZATION),
        ("数字要素驱动业", "互联网平台", DIGITAL_INDUSTRIALIZATION),
        ("数字化效率提升业", "智能制造", INDUSTRIAL_DIGITALIZATION),
        (
            "数字化效率提升业",
            "其他数字化效率提升业",
            DIGITAL_EFFICIENCY_IMPROVEMENT,
        ),
    ],
)
def test_published_mapping_tiers_have_server_owned_digital_categories(
    tier1: str,
    tier2: str,
    expected: str,
) -> None:
    assert normalize_digital_category(_label(tier1=tier1, tier2=tier2)) == expected


def test_traditional_enterprise_with_digital_industrialization_direction_is_included() -> None:
    decision = DIGITAL_FINANCE_POLICY.preclassify_stage_b(
        {
            "loan_purpose": "采购工业软件开发服务",
            "industry_position_competitiveness": "传统制造企业",
            "digital_core_competitiveness": "",
            "rd_ip_info": "仅采购外部系统，无自主知识产权",
        },
        _stage_a(),
        (),
        (_label(tier1="数字技术应用业", tier2="软件开发"),),
    )

    assert decision is not None
    assert decision.result_status == "completed"
    assert decision.consistency_status == "inconsistent"
    assert decision.labels[0]["digital_category"] == DIGITAL_INDUSTRIALIZATION
    assert decision.labels[0]["decision_policy_version"] == "digital-direction-v2"
    assert "按该笔资金投向认定为数字金融" in decision.consistency_basis
    warnings = [
        ref.get("warning")
        for ref in decision.consistency_evidence_refs
        if ref.get("type") == "digital_auxiliary"
    ]
    assert "企业数字化核心竞争力佐证不足" in warnings
    assert "知识产权佐证不足" in warnings


def test_industrial_digitalization_with_complete_auxiliary_evidence_has_no_warning() -> None:
    label = _label(tier1="数字化效率提升业", tier2="智能制造")
    decision = DIGITAL_FINANCE_POLICY.preclassify_stage_b(
        {
            "loan_purpose": "建设智能制造产线",
            "industry_position_competitiveness": "传统制造企业数字化转型主体",
            "digital_core_competitiveness": "拥有自研平台、稳定数字化业务订单和技术团队",
            "rd_ip_info": "拥有工业软件著作权 3 项",
        },
        _stage_a(),
        (label,),
        (label,),
    )

    assert decision is not None
    assert decision.result_status == "completed"
    assert decision.consistency_status == "consistent"
    assert decision.labels[0]["digital_category"] == INDUSTRIAL_DIGITALIZATION
    auxiliary = [
        ref
        for ref in decision.consistency_evidence_refs
        if ref.get("type") == "digital_auxiliary"
    ]
    assert {ref["evidence_status"] for ref in auxiliary} == {"positive"}
    assert all(ref["warning"] is None for ref in auxiliary)


def test_unclassified_efficiency_improvement_is_not_included() -> None:
    decision = DIGITAL_FINANCE_POLICY.preclassify_stage_b(
        {"loan_purpose": "采购通用办公系统提升内部效率"},
        _stage_a(),
        (),
        (
            _label(
                tier1="数字化效率提升业",
                tier2="其他数字化效率提升业",
            ),
        ),
    )

    assert decision is not None
    assert decision.result_status == "not_applicable"
    assert decision.labels == ()
    assert decision.consistency_basis == "数字化效率提升无法准确区分，暂不纳入统计"
    direction = next(
        ref
        for ref in decision.consistency_evidence_refs
        if ref.get("type") == "digital_direction"
    )
    assert direction["digital_category"] == DIGITAL_EFFICIENCY_IMPROVEMENT


def test_industrial_digitalization_mapping_without_digital_means_needs_review() -> None:
    decision = DIGITAL_FINANCE_POLICY.preclassify_stage_b(
        {
            "loan_purpose": "本次贷款资金用于采购汽车售卖",
            "trade_goods_services": "汽车",
            "industry_position_competitiveness": "数字金融技术服务商",
        },
        _stage_a(),
        (_label(tier1="数字技术应用业", tier2="软件开发"),),
        (
            _label(
                tier1="数字化效率提升业",
                tier2="数字商贸",
            ),
        ),
    )

    assert decision is not None
    assert decision.result_status == "needs_review"
    assert decision.consistency_status == "needs_review"
    assert decision.labels == ()
    assert "未说明数字技术或数字化手段" in decision.consistency_basis
    assert decision.model_output["digital_decision"]["branch"] == (
        "INDUSTRIAL_DIGITALIZATION_MEANS_UNCLEAR"
    )


def test_unmapped_vague_direction_becomes_needs_review() -> None:
    mapping_result = FiveArticlesMappingLookupResult(
        status="not_applicable",
        mapping_version_id=7,
        mapping_version=3,
        enterprise_labels=(),
        loan_direction_labels=(),
        detail="loan_direction_has_no_explicit_mapping",
    )

    resolution = DIGITAL_FINANCE_POLICY.resolve_mapping(
        MagicMock(),
        {"loan_purpose": "经营周转"},
        mapping_result,
        Settings(_env_file=None),
        condition_candidate_retriever=MagicMock(),
        condition_label_selector=MagicMock(),
    )

    assert resolution.terminal_result is not None
    assert resolution.terminal_result.result_status == "needs_review"
    assert "不得以企业数字属性替代" in resolution.terminal_result.consistency_basis


def test_workflow_persists_policy_terminal_needs_review_without_model_call() -> None:
    mapping_result = FiveArticlesMappingLookupResult(
        status="not_applicable",
        mapping_version_id=7,
        mapping_version=3,
        enterprise_labels=(),
        loan_direction_labels=(),
        detail="loan_direction_has_no_explicit_mapping",
    )
    session = MagicMock()
    session.scalar.return_value = None
    case = SimpleNamespace(
        id=21,
        scenario="digital_finance",
        input_payload={"loan_purpose": "经营周转"},
    )
    stage_b_classifier = MagicMock()

    result = _build_stage_b_result(
        session,
        case,
        _stage_a(),
        mapping_result,
        Settings(_env_file=None),
        DIGITAL_FINANCE_REGISTRATION,
        MagicMock(),
        stage_b_classifier,
        MagicMock(),
        MagicMock(),
    )

    assert result.status == "needs_review"
    assert result.decision_policy_version == "digital-direction-v2"
    assert result.model_output["digital_decision"]["branch"] == (
        "DIGITAL_DIRECTION_EVIDENCE_INSUFFICIENT"
    )
    stage_b_classifier.assert_not_called()


def test_unmapped_explicit_non_digital_direction_stays_not_applicable() -> None:
    mapping_result = FiveArticlesMappingLookupResult(
        status="not_applicable",
        mapping_version_id=7,
        mapping_version=3,
        enterprise_labels=(),
        loan_direction_labels=(),
        detail="loan_direction_has_no_explicit_mapping",
    )

    resolution = DIGITAL_FINANCE_POLICY.resolve_mapping(
        MagicMock(),
        {"loan_purpose": "采购水泥熟料用于传统建材生产"},
        mapping_result,
        Settings(_env_file=None),
        condition_candidate_retriever=MagicMock(),
        condition_label_selector=MagicMock(),
    )

    assert resolution.terminal_result is None
    assert resolution.mapping_result.status == "not_applicable"


def test_digital_enterprise_with_explicit_non_digital_direction_needs_review() -> None:
    mapping_result = FiveArticlesMappingLookupResult(
        status="not_applicable",
        mapping_version_id=7,
        mapping_version=3,
        enterprise_labels=(
            _label(tier1="数字技术应用业", tier2="软件开发"),
        ),
        loan_direction_labels=(),
        detail="loan_direction_has_no_explicit_mapping",
    )

    resolution = DIGITAL_FINANCE_POLICY.resolve_mapping(
        MagicMock(),
        {
            "loan_purpose": "采购汽车售卖",
            "trade_goods_services": "汽车",
        },
        mapping_result,
        Settings(_env_file=None),
        condition_candidate_retriever=MagicMock(),
        condition_label_selector=MagicMock(),
    )

    assert resolution.terminal_result is not None
    assert resolution.terminal_result.result_status == "needs_review"
    assert resolution.terminal_result.consistency_status == "needs_review"
    assert "企业属性与资金投向冲突" in resolution.terminal_result.consistency_basis
    assert resolution.terminal_result.model_output["digital_decision"]["branch"] == (
        "DIGITAL_ENTERPRISE_DIRECTION_CONFLICT"
    )


def test_old_template_combined_field_can_supply_core_competitiveness_evidence() -> None:
    decision = DIGITAL_FINANCE_POLICY.preclassify_stage_b(
        {
            "loan_purpose": "开发云计算平台",
            "industry_position_competitiveness": "软件企业，拥有自研 SaaS 平台",
            "rd_ip_info": "拥有软件著作权",
        },
        _stage_a(),
        (),
        (_label(tier1="数字技术应用业", tier2="软件开发"),),
    )

    assert decision is not None
    core_ref = next(
        ref
        for ref in decision.consistency_evidence_refs
        if ref.get("evidence_role") == "core_competitiveness"
    )
    assert core_ref["field_key"] == "industry_position_competitiveness"
    assert core_ref["evidence_status"] == "positive"


def test_cross_scenario_label_is_rejected_before_digital_policy_runs() -> None:
    wrong_label = _label(
        tier1="数字技术应用业",
        tier2="软件开发",
        scenario_id="technology_finance",
    )

    with pytest.raises(
        TechnologyFinanceStageBError,
        match="deterministic labels must belong to scenario digital_finance",
    ):
        classify_five_articles_stage_b(
            DIGITAL_FINANCE_REGISTRATION,
            {"loan_purpose": "开发软件平台"},
            _stage_a(),
            (),
            (wrong_label,),
            Settings(_env_file=None),
        )
