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
            "main_business": "水稻种植与销售",
            "core_products_services": "稻谷",
            "business_scope": "谷物种植",
            "loan_purpose": "购买种子和农机",
        },
        status="pending_classification",
    )


def _candidate() -> EvidenceSnapshot:
    return EvidenceSnapshot(
        industry_code="0111",
        industry_name="稻谷种植",
        vector_score=0.91,
        rerank_score=0.97,
        hits=(
            RecallHit(
                industry_code="0111",
                industry_name="稻谷种植",
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
    )


def test_build_query_uses_labeled_enterprise_fields_and_objection() -> None:
    query = build_classification_query(_case().input_payload, "补充：自产水稻占比 90%")

    assert "主营业务：水稻种植与销售" in query
    assert "核心产品 / 服务：稻谷" in query
    assert "营业执照经营范围：谷物种植" in query
    assert "贷款用途：购买种子和农机" in query
    assert "异议说明：补充：自产水稻占比 90%" in query


def test_initial_classification_saves_first_completed_version() -> None:
    session = MagicMock()
    case = _case()
    retrieval = MagicMock(return_value=(_candidate(),))
    classifier = MagicMock(return_value=_classification())

    result = classify_case(
        session,
        case,
        _settings(),
        retrieval=retrieval,
        classifier=classifier,
    )

    assert result.version == 1
    assert result.status == "completed"
    assert result.confidence == 92
    assert result.rationale == "主营业务和目录定义一致"
    assert result.ai_summary == "企业主要从事稻谷种植"
    assert case.status == "completed"
    assert "主营业务：水稻种植与销售" in retrieval.call_args.args[1]
    classifier.assert_called_once_with(case.input_payload, (_candidate(),), _settings(), None)
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

    result = reclassify_case(
        session,
        case,
        "  主营收入主要来自水稻  ",
        _settings(),
        retrieval=MagicMock(return_value=(_candidate(),)),
        classifier=classifier,
    )

    assert result.version == 2
    assert result.objection == objection
    assert original.version == 1
    assert original.industry_code == "0112"
    assert original.objection is None
    assert tuple(item.version for item in case.result_versions) == (1, 2)
    assert classifier.call_args.args[3] == objection


def test_blank_objection_is_rejected_without_reclassification() -> None:
    session = MagicMock()
    retrieval = MagicMock()
    classifier = MagicMock()

    with pytest.raises(ValueError, match="must not be blank"):
        reclassify_case(
            session,
            _case(),
            "  \n  ",
            _settings(),
            retrieval=retrieval,
            classifier=classifier,
        )

    retrieval.assert_not_called()
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

    with pytest.raises(RuntimeError, match="DeepSeek unavailable"):
        reclassify_case(
            session,
            case,
            "需要重判",
            _settings(),
            retrieval=MagicMock(return_value=(_candidate(),)),
            classifier=classifier,
        )

    assert case.status == "classification_failed"
    assert tuple(case.result_versions) == (original,)
    assert get_current_completed_result(case) is original
    session.rollback.assert_called_once_with()
    assert session.commit.call_count == 1


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
