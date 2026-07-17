from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.core.config import Settings
from app.services.five_articles_policies.green import (
    GREEN_FINANCE_DECISION_POLICY_VERSION,
    GREEN_FINANCE_POLICY,
    _green_decision,
    parse_major_environmental_violation,
)
from app.services.scenario_registry import GREEN_FINANCE_REGISTRATION
from app.services.technology_finance_classification_workflow import (
    _build_stage_b_result,
)
from app.services.technology_finance_mapping_query import (
    FiveArticlesMappingLabel,
    FiveArticlesMappingLookupResult,
)


def _label(
    *,
    source_row: int = 12,
    match_method: str = "neic_code",
) -> FiveArticlesMappingLabel:
    return FiveArticlesMappingLabel(
        mapping_version_id=7,
        scenario_id="green_finance",
        neic_code="4415",
        code_level=4,
        neic_name="太阳能发电",
        subject="绿色金融支持项目目录（2025年版）",
        tier1="清洁能源产业",
        tier2="太阳能利用",
        tier3=None,
        tier4=None,
        source_row=source_row,
        condition_criteria="贷款用于光伏发电项目建设",
        match_method=match_method,  # type: ignore[arg-type]
    )


def _input(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "loan_purpose": "建设分布式光伏发电项目",
        "main_business": "建设和运营清洁能源发电设施",
        "green_project_name": "园区分布式光伏项目",
        "project_content": "建设屋顶光伏组件及配套储能设施",
        "green_certifications": "绿色项目认定文件",
        "energy_saving_pollution_control": "以可再生能源替代火电",
        "carbon_environmental_benefits": "预计每年减少碳排放1200吨",
        "major_environmental_violation": "无",
    }
    payload.update(overrides)
    return payload


def _stage_a() -> SimpleNamespace:
    return SimpleNamespace(
        id=11,
        industry_code="3011",
        industry_major_code="30",
        industry_name="水泥制造",
        rationale="企业主营水泥制造",
        loan_industry_code="4415",
        loan_industry_major_code="44",
        loan_industry_name="太阳能发电",
        loan_matching_basis="贷款用于光伏项目建设",
    )


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("有", "yes"),
        ("存在重大环保违法失信记录", "yes"),
        ("无", "no"),
        ("没有重大环保违法记录", "no"),
        ("", "unknown"),
        ("待核验", "unknown"),
        ("材料表述不明确", "unknown"),
    ],
)
def test_major_environmental_violation_has_three_state_parser(
    raw: str,
    expected: str,
) -> None:
    assert parse_major_environmental_violation(raw) == expected


@pytest.mark.parametrize(
    ("enterprise_hit", "expected_consistency"),
    [(True, "consistent"), (False, "inconsistent")],
)
def test_green_direction_hit_controls_inclusion_independent_of_enterprise(
    enterprise_hit: bool,
    expected_consistency: str,
) -> None:
    label = _label()
    decision = _green_decision(
        _input(),
        (label,) if enterprise_hit else (),
        (label,),
    )

    assert decision is not None
    assert decision.result_status == "completed"
    assert decision.consistency_status == expected_consistency
    assert decision.labels[0]["decision_policy_version"] == (
        GREEN_FINANCE_DECISION_POLICY_VERSION
    )
    assert "贷款实际投向" in decision.consistency_basis


@pytest.mark.parametrize("enterprise_hit", [True, False])
def test_non_green_direction_is_not_applicable_even_for_green_enterprise(
    enterprise_hit: bool,
) -> None:
    mapping_result = FiveArticlesMappingLookupResult(
        status="not_applicable",
        mapping_version_id=7,
        mapping_version=3,
        enterprise_labels=(_label(),) if enterprise_hit else (),
        loan_direction_labels=(),
        detail="loan_direction_has_no_explicit_mapping",
    )
    candidate_retriever = MagicMock(return_value=())

    resolution = GREEN_FINANCE_POLICY.resolve_mapping(
        MagicMock(),
        _input(),
        mapping_result,
        Settings(_env_file=None),
        condition_candidate_retriever=candidate_retriever,
        condition_label_selector=MagicMock(return_value=_label()),
    )

    assert resolution.mapping_result.status == "not_applicable"
    assert resolution.terminal_result is None
    assert resolution.not_applicable_error_detail == "green_finance_condition_no_match"


def test_missing_auxiliary_materials_warn_without_overriding_green_result() -> None:
    label = _label()
    decision = _green_decision(
        _input(
            green_certifications="",
            energy_saving_pollution_control="",
            carbon_environmental_benefits="",
        ),
        (),
        (label,),
    )

    assert decision is not None
    assert decision.result_status == "completed"
    warnings = {
        ref["warning"]
        for ref in decision.consistency_evidence_refs
        if ref.get("type") == "green_auxiliary"
    }
    assert warnings == {
        "缺少绿色资质",
        "缺少节能减排/污染治理内容",
        "无量化环境效益佐证",
    }


def test_complete_auxiliary_materials_have_no_warning() -> None:
    decision = _green_decision(
        _input(),
        (_label(),),
        (_label(),),
    )

    assert decision is not None
    assert all(
        ref.get("warning") is None
        for ref in decision.consistency_evidence_refs
        if ref.get("type") in {"green_auxiliary", "green_violation"}
    )


def test_major_environmental_violation_requires_review_and_keeps_green_evidence() -> None:
    label = replace(_label(), match_method="condition_fallback")
    decision = _green_decision(
        _input(major_environmental_violation="存在重大环保违法失信记录"),
        (label,),
        (label,),
    )

    assert decision is not None
    assert decision.result_status == "needs_review"
    assert decision.consistency_status == "needs_review"
    assert decision.labels[0]["match_method"] == "condition_fallback"
    direction = next(
        ref
        for ref in decision.consistency_evidence_refs
        if ref.get("type") == "green_direction"
    )
    assert direction["condition_criteria"] == "贷款用于光伏发电项目建设"
    assert "潜在漂绿" in decision.consistency_basis


def test_unknown_violation_is_not_treated_as_no_violation() -> None:
    decision = _green_decision(
        _input(major_environmental_violation=""),
        (),
        (_label(),),
    )

    assert decision is not None
    assert decision.result_status == "completed"
    violation = next(
        ref
        for ref in decision.consistency_evidence_refs
        if ref.get("type") == "green_violation"
    )
    assert violation["violation_status"] == "unknown"
    assert violation["warning"] == "重大环保违法失信信息未知，需补充核验"


def test_workflow_persists_server_owned_green_decision_without_model_call() -> None:
    label = _label(match_method="condition_fallback")
    mapping_result = FiveArticlesMappingLookupResult(
        status="mapping_hit",
        mapping_version_id=7,
        mapping_version=3,
        enterprise_labels=(),
        loan_direction_labels=(label,),
        detail="loan_direction_mapping_hit",
    )
    session = MagicMock()
    session.scalar.return_value = None
    case = SimpleNamespace(
        id=21,
        scenario="green_finance",
        input_payload=_input(),
    )
    selector = MagicMock(return_value=label)
    stage_b_classifier = MagicMock()

    result = _build_stage_b_result(
        session,
        case,
        _stage_a(),
        mapping_result,
        Settings(_env_file=None),
        GREEN_FINANCE_REGISTRATION,
        selector,
        stage_b_classifier,
        MagicMock(return_value=()),
        selector,
    )

    assert result.status == "completed"
    assert result.decision_policy_version == GREEN_FINANCE_DECISION_POLICY_VERSION
    assert result.labels[0]["match_method"] == "neic_code"
    stage_b_classifier.assert_not_called()
