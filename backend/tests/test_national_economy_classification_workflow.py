from dataclasses import replace
from unittest.mock import MagicMock

import pytest

from app.core.config import Settings
from app.models import (
    NationalEconomyClassificationCase,
    NationalEconomyClassificationResult,
)
from app.services.national_economy_classification import ConstrainedClassificationResult
from app.services.national_economy_classification_workflow import (
    build_classification_query,
    classify_case,
    get_current_completed_result,
    reclassify_case,
)
from app.services.national_economy_decision_policy import EvidenceLevel
from app.services.national_economy_retrieval import EvidenceSnapshot, RecallHit


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        database_url="postgresql+psycopg://user:pass@localhost/test",
        siliconflow_api_key="siliconflow-key",
        deepseek_api_key="deepseek-key",
    )


def _case() -> NationalEconomyClassificationCase:
    return NationalEconomyClassificationCase(
        id=1,
        scenario="national_economy_classification",
        input_payload={
            "enterprise_name": "示例企业",
            "unified_social_credit_code": "91320000TEST",
            "main_business": "水稻种植与销售",
            "main_business_revenue_share": "水稻种植收入占 90%",
            "core_products_services": "稻谷",
            "counterparty_name": "示例采购方",
            "counterparty_business_industry": "粮食加工",
            "trade_goods_services": "稻谷销售",
            "industry_chain_position": "水稻种植上游",
            "industry_position_competitiveness": "本地水稻主产企业",
            "business_scope": "谷物种植",
            "loan_purpose": "购买种子和农机",
            "credit_approval_opinion": "支持种植经营周转",
        },
        status="pending_classification",
    )


def _candidate(
    industry_code: str = "0111",
    industry_name: str = "稻谷种植",
) -> EvidenceSnapshot:
    return EvidenceSnapshot(
        industry_code=industry_code,
        industry_name=industry_name,
        vector_score=0.91,
        rerank_score=0.97,
        hits=(
            RecallHit(
                industry_code=industry_code,
                industry_name=industry_name,
                source_row=2,
                chunk_type="definition",
                text="指水稻的种植活动",
                distance=0.09,
            ),
        ),
    )


def _classification(
    *,
    status: str = "completed",
    confidence: float | None = 91.6,
    objection: dict[str, object] | None = None,
    loan_industry_code: str | None = "0111",
    loan_industry_name: str | None = "稻谷种植",
    loan_matching_basis: str | None = "贷款用途与企业主营一致",
    loan_matches_enterprise: bool | None = True,
) -> ConstrainedClassificationResult:
    selected = status == "completed"
    return ConstrainedClassificationResult(
        status=status,
        industry_code="0111" if selected else None,
        industry_name="稻谷种植" if selected else None,
        confidence=confidence if selected else None,
        matching_basis="主营业务和目录定义一致",
        summary="企业主要从事稻谷种植" if selected else None,
        candidate_snapshot=({"industry_code": "0111"},),
        objection=objection,
        model_output={"no_match": not selected},
        loan_industry_code=loan_industry_code if selected else None,
        loan_industry_name=loan_industry_name if selected else None,
        loan_matching_basis=loan_matching_basis,
        loan_matches_enterprise=loan_matches_enterprise if selected else None,
    )


def test_build_query_maps_labeled_fields_to_ordered_evidence_layers() -> None:
    input_payload = dict(_case().input_payload)
    input_payload["main_business_revenue_share"] = "水稻45%；小麦30%；玉米5%"
    layers = build_classification_query(input_payload, "补充：自产水稻占比 90%")

    assert [layer.level for layer in layers] == list(EvidenceLevel)
    labels_by_level = {
        layer.level: [fact.field_label for fact in layer.facts] for layer in layers
    }
    assert labels_by_level[EvidenceLevel.MAIN_BUSINESS_REVENUE] == [
        "主营业务",
        "主营业务及营收占比",
        "核心产品 / 服务名称",
        "异议说明",
    ]
    assert labels_by_level[EvidenceLevel.TRADE_AND_INDUSTRY_CHAIN] == [
        "贸易合同核心交易品类 / 服务内容",
        "交易对手主营业务 / 所属行业",
        "企业产业链定位",
        "企业行业定位与核心竞争力",
    ]
    assert labels_by_level[EvidenceLevel.LOAN_PURPOSE] == [
        "贷款用途详细描述",
        "授信审批意见",
    ]
    assert labels_by_level[EvidenceLevel.BUSINESS_SCOPE] == [
        "营业执照经营范围（全文）"
    ]
    all_labels = {label for labels in labels_by_level.values() for label in labels}
    assert "企业名称" not in all_labels
    assert "统一社会信用代码" not in all_labels
    assert "贸易合同本次交易对手名称" not in all_labels
    assert layers[0].facts[-1].source == "objection"


def test_build_query_locks_dominant_business_and_excludes_distracting_fields() -> None:
    input_payload = dict(_case().input_payload)
    input_payload.update(
        {
            "main_business": "综合养老与信息技术服务",
            "main_business_revenue_share": (
                "养老服务70%；计算机销售20%；网络工程10%"
            ),
            "core_products_services": "服务器；养老床位",
        }
    )

    layers = build_classification_query(input_payload, "应按计算机销售判断")

    assert layers[0].is_available
    assert [fact.field_label for fact in layers[0].facts] == [
        "主营业务及营收占比（主导主营）",
        "异议说明",
    ]
    assert layers[0].facts[0].indicated_business == "养老服务"
    assert layers[0].facts[0].raw_text == input_payload["main_business_revenue_share"]


def test_build_query_without_dominant_business_keeps_existing_evidence_fields() -> None:
    input_payload = dict(_case().input_payload)
    input_payload["main_business_revenue_share"] = "计算机45%；软件30%；网络工程5%"

    layers = build_classification_query(input_payload)

    assert [fact.field_label for fact in layers[0].facts] == [
        "主营业务",
        "主营业务及营收占比",
        "核心产品 / 服务名称",
    ]


def test_build_query_marks_empty_layers_unavailable_without_stringifying_none() -> None:
    layers = build_classification_query(
        {"main_business": None, "business_scope": "软件开发"}
    )

    assert not layers[0].is_available
    assert layers[0].facts == ()
    assert layers[3].is_available
    assert layers[3].facts[0].raw_text == "软件开发"


def test_initial_classification_saves_first_completed_version() -> None:
    session = MagicMock()
    case = _case()
    case.input_payload["loan_purpose"] = "流动资金"
    case.input_payload["credit_approval_opinion"] = "支持经营周转"
    retrieval = MagicMock(return_value=(_candidate(),))
    loan_retrieval = MagicMock(return_value=())
    classifier = MagicMock(return_value=_classification())

    result = classify_case(
        session,
        case,
        _settings(),
        retrieval=retrieval,
        loan_retrieval=loan_retrieval,
        classifier=classifier,
    )

    assert result.version == 1
    assert result.status == "completed"
    assert result.confidence is None
    assert result.rationale == "主营业务和目录定义一致"
    assert result.ai_summary is None
    assert result.loan_industry_code == "0111"
    assert result.loan_industry_name == "稻谷种植"
    assert result.loan_matching_basis == "贷款用途与企业主营一致"
    assert result.loan_matches_enterprise is True
    assert case.status == "completed"
    evidence_layers = retrieval.call_args.args[1]
    assert evidence_layers[0].level is EvidenceLevel.MAIN_BUSINESS_REVENUE
    assert evidence_layers[0].facts[0].field_label == "主营业务及营收占比（主导主营）"
    assert evidence_layers[0].facts[0].indicated_business == "水稻种植收入占"
    loan_retrieval.assert_called_once_with(session, evidence_layers, _settings())
    classifier.assert_called_once_with(
        evidence_layers,
        (_candidate(),),
        _settings(),
        None,
        loan_direction_candidates=(),
    )
    session.add.assert_called_once_with(result)
    session.commit.assert_called_once_with()


def test_objection_reclassification_appends_version_and_preserves_history() -> None:
    session = MagicMock()
    case = _case()
    original = NationalEconomyClassificationResult(
        case=case,
        version=1,
        status="completed",
        industry_code="0112",
        industry_name="小麦种植",
        confidence=70,
        rationale="原依据",
        ai_summary="原总结",
        candidate_snapshot=[{"industry_code": "0112"}],
        objection=None,
        model_output={"no_match": False},
    )
    objection = {"description": "主营收入主要来自水稻"}
    classifier = MagicMock(return_value=_classification(objection=objection))
    loan_candidate = _candidate("5263", "汽车零配件零售")
    loan_retrieval = MagicMock(return_value=(loan_candidate,))

    result = reclassify_case(
        session,
        case,
        "  主营收入主要来自水稻  ",
        _settings(),
        retrieval=MagicMock(return_value=(_candidate(),)),
        loan_retrieval=loan_retrieval,
        classifier=classifier,
    )

    assert result.version == 2
    assert result.objection == objection
    assert original.version == 1
    assert original.industry_code == "0112"
    assert original.confidence == 70
    assert original.ai_summary == "原总结"
    assert original.objection is None
    assert tuple(item.version for item in case.result_versions) == (1, 2)
    assert classifier.call_args.args[3] == objection
    evidence_layers = classifier.call_args.args[0]
    loan_retrieval.assert_called_once_with(session, evidence_layers, _settings())
    assert classifier.call_args.kwargs["loan_direction_candidates"] == (
        loan_candidate,
    )
    assert evidence_layers[0].facts[-1].source == "objection"
    assert evidence_layers[0].facts[-1].field_label == "异议说明"


def test_specific_loan_direction_candidates_and_result_are_persisted() -> None:
    session = MagicMock()
    case = _case()
    enterprise_candidate = _candidate()
    loan_candidate = _candidate("5263", "汽车零配件零售")
    retrieval = MagicMock(return_value=(enterprise_candidate,))
    loan_retrieval = MagicMock(return_value=(loan_candidate,))
    classifier = MagicMock(
        return_value=_classification(
            loan_industry_code="5263",
            loan_industry_name="汽车零配件零售",
            loan_matching_basis=(
                "实际投向为汽车零部件采购，匹配经营范围内汽车零部件销售项，"
                "对应 5263"
            ),
            loan_matches_enterprise=False,
        )
    )

    result = classify_case(
        session,
        case,
        _settings(),
        retrieval=retrieval,
        loan_retrieval=loan_retrieval,
        classifier=classifier,
    )

    evidence_layers = retrieval.call_args.args[1]
    loan_retrieval.assert_called_once_with(session, evidence_layers, _settings())
    classifier.assert_called_once_with(
        evidence_layers,
        (enterprise_candidate,),
        _settings(),
        None,
        loan_direction_candidates=(loan_candidate,),
    )
    assert result.loan_industry_code == "5263"
    assert result.loan_industry_name == "汽车零配件零售"
    assert "汽车零部件采购" in result.loan_matching_basis
    assert result.loan_matches_enterprise is False


def test_enterprise_and_loan_major_codes_are_persisted_by_workflow() -> None:
    session = MagicMock()
    case = _case()
    enterprise_candidate = replace(_candidate(), major_category_code="A01")
    loan_candidate = replace(
        _candidate("5263", "汽车零配件零售"),
        major_category_code="F52",
    )
    classification = replace(
        _classification(
            loan_industry_code="5263",
            loan_industry_name="汽车零配件零售",
            loan_matches_enterprise=False,
        ),
        industry_major_code="A01",
        loan_industry_major_code="F52",
    )

    result = classify_case(
        session,
        case,
        _settings(),
        retrieval=MagicMock(return_value=(enterprise_candidate,)),
        loan_retrieval=MagicMock(return_value=(loan_candidate,)),
        classifier=MagicMock(return_value=classification),
    )

    assert result.industry_major_code == "A01"
    assert result.loan_industry_major_code == "F52"


def test_blank_objection_is_rejected_without_reclassification() -> None:
    session = MagicMock()
    retrieval = MagicMock()
    loan_retrieval = MagicMock()
    classifier = MagicMock()

    with pytest.raises(ValueError, match="must not be blank"):
        reclassify_case(
            session,
            _case(),
            "  \n  ",
            _settings(),
            retrieval=retrieval,
            loan_retrieval=loan_retrieval,
            classifier=classifier,
        )

    retrieval.assert_not_called()
    loan_retrieval.assert_not_called()
    classifier.assert_not_called()
    session.commit.assert_not_called()


def test_failed_reclassification_does_not_overwrite_latest_completed_result() -> None:
    session = MagicMock()
    case = _case()
    original = NationalEconomyClassificationResult(
        case=case,
        version=1,
        status="completed",
        industry_code="0111",
        industry_name="稻谷种植",
        confidence=88,
        rationale="成功依据",
        ai_summary="成功总结",
        candidate_snapshot=[{"industry_code": "0111"}],
        objection=None,
        model_output={"no_match": False},
    )
    classifier = MagicMock(side_effect=RuntimeError("DeepSeek unavailable"))
    loan_retrieval = MagicMock(return_value=(_candidate(),))

    with pytest.raises(RuntimeError, match="DeepSeek unavailable"):
        reclassify_case(
            session,
            case,
            "需要重判",
            _settings(),
            retrieval=MagicMock(return_value=(_candidate(),)),
            loan_retrieval=loan_retrieval,
            classifier=classifier,
        )

    assert case.status == "classification_failed"
    assert tuple(case.result_versions) == (original,)
    assert get_current_completed_result(case) is original
    session.rollback.assert_called_once_with()
    assert session.commit.call_count == 1
    loan_retrieval.assert_called_once()


def test_current_result_is_latest_completed_version_not_latest_attempt() -> None:
    case = _case()
    first = NationalEconomyClassificationResult(
        case=case,
        version=1,
        status="completed",
        candidate_snapshot=[],
    )
    NationalEconomyClassificationResult(
        case=case,
        version=2,
        status="needs_review",
        candidate_snapshot=[],
    )
    latest = NationalEconomyClassificationResult(
        case=case,
        version=3,
        status="completed",
        candidate_snapshot=[],
    )

    assert get_current_completed_result(case) is latest
    assert get_current_completed_result(case) is not first
