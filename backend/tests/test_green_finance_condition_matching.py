import json
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
from sqlalchemy.dialects import postgresql

from app.core.config import Settings
from app.services.green_finance_condition_matching import (
    GreenFinanceConditionIndexError,
    MAX_RERANK_RESULTS,
    NO_MATCH_SOURCE_ROW,
    RECALL_LIMIT,
    GreenFinanceConditionCandidate,
    GreenFinanceConditionSelectionError,
    retrieve_green_finance_condition_candidates,
    select_green_finance_condition_label,
)
from app.services.scenario_registry import GREEN_FINANCE_SCENARIO
from app.services.technology_finance_mapping_query import FiveArticlesMappingLabel


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        siliconflow_api_key="siliconflow-test-key",
        siliconflow_base_url="https://siliconflow.example/v1",
        siliconflow_rerank_model="rerank-test",
        siliconflow_timeout_seconds=17,
        deepseek_api_key="deepseek-test-key",
        deepseek_base_url="https://deepseek.example/v1",
        deepseek_model="deepseek-test",
        deepseek_timeout_seconds=19,
        http_connect_timeout_seconds=3,
        embedding_dimension=3,
    )


def _row(source_row: int, criteria: str) -> SimpleNamespace:
    return SimpleNamespace(
        mapping_version_id=9,
        scenario_id=GREEN_FINANCE_SCENARIO,
        neic_code="-",
        code_level=None,
        neic_name="无行业代码",
        subject=f"主题{source_row}",
        tier1="绿色产业",
        tier2=f"分类{source_row}",
        tier3=None,
        tier4=None,
        source_row=source_row,
        condition_criteria=criteria,
    )


def _candidate(source_row: int = 12, criteria: str = "节能改造项目") -> GreenFinanceConditionCandidate:
    return GreenFinanceConditionCandidate(
        label=FiveArticlesMappingLabel(
            mapping_version_id=9,
            scenario_id=GREEN_FINANCE_SCENARIO,
            neic_code="-",
            code_level=None,
            neic_name="无行业代码",
            subject="绿色产业主题",
            tier1="绿色产业",
            tier2="节能环保",
            tier3=None,
            tier4=None,
            source_row=source_row,
        ),
        condition_criteria=criteria,
        vector_score=0.8,
        rerank_score=0.9,
    )


def _selection_client(model_output: object, *, attempts: list[int] | None = None) -> httpx.Client:
    def handler(_request: httpx.Request) -> httpx.Response:
        if attempts is not None:
            attempts.append(1)
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(model_output, ensure_ascii=False)}}]},
        )

    return httpx.Client(transport=httpx.MockTransport(handler), base_url=_settings().deepseek_base_url)


def _mock_complete_index(session: Mock, recalled: object) -> None:
    session.scalar.return_value = SimpleNamespace(id=9, version=3)
    index_result = Mock()
    index_result.one.return_value = (1506, 1506, 1506)
    recall_result = Mock()
    recall_result.all.return_value = recalled
    session.execute.side_effect = (index_result, recall_result)


def test_retrieval_uses_green_published_rows_cosine_top_30_and_rerank_limit() -> None:
    session = Mock()
    # The database has already applied the SQL ORDER BY distance contract.
    _mock_complete_index(session, [
        (_row(20, "太阳能发电项目"), 0.08),
        (_row(10, "节能改造项目"), 0.21),
    ])
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={"results": [{"index": 1, "relevance_score": 0.98}, {"index": 0, "relevance_score": 0.88}]},
        )

    with httpx.Client(transport=httpx.MockTransport(handler), base_url=_settings().siliconflow_base_url) as client:
        candidates = retrieve_green_finance_condition_candidates(
            session,
            {"loan_purpose": "建设节能生产线", "trade_goods_services": "高效电机"},
            "loan_direction",
            _settings(),
            embedding_request=lambda texts, _settings: ((0.1, 0.2, 0.3),),
            rerank_client=client,
        )

    statement = session.execute.call_args_list[1].args[0]
    compiled = statement.compile(dialect=postgresql.dialect())
    sql = str(compiled)
    assert "<=>" in sql
    assert GREEN_FINANCE_SCENARIO in compiled.params.values()
    assert 9 in compiled.params.values()
    assert statement._limit_clause.value == RECALL_LIMIT
    assert captured["documents"] == ["太阳能发电项目", "节能改造项目"]
    assert captured["top_n"] == 2
    assert [candidate.source_row for candidate in candidates] == [10, 20]
    assert all(candidate.rerank_score > 0 for candidate in candidates)
    assert len(candidates) <= MAX_RERANK_RESULTS


def test_retrieval_uses_side_specific_evidence_and_propagates_embedding_failure() -> None:
    session = Mock()
    session.scalar.return_value = SimpleNamespace(id=9, version=3)
    session.execute.return_value.one.return_value = (1506, 1506, 1506)
    requested: list[tuple[str, ...]] = []

    with pytest.raises(RuntimeError, match="embedding unavailable"):
        retrieve_green_finance_condition_candidates(
            session,
            {"core_products_services": "污水处理设备", "main_business": "环保工程", "loan_purpose": "不应出现"},
            "enterprise",
            _settings(),
            embedding_request=lambda texts, _settings: requested.append(tuple(texts))
            or (_ for _ in ()).throw(RuntimeError("embedding unavailable")),
        )

    assert requested == [("核心产品 / 服务名称：污水处理设备\n主营业务：环保工程",)]
    assert session.execute.call_count == 1


def test_retrieval_propagates_rerank_service_failure() -> None:
    session = Mock()
    _mock_complete_index(session, [(_row(10, "节能改造项目"), 0.1)])

    with httpx.Client(
        transport=httpx.MockTransport(lambda _request: httpx.Response(503)),
        base_url=_settings().siliconflow_base_url,
    ) as client, pytest.raises(httpx.HTTPStatusError):
        retrieve_green_finance_condition_candidates(
            session,
            {"loan_purpose": "建设节能生产线"},
            "loan_direction",
            _settings(),
            embedding_request=lambda _texts, _settings: ((0.1, 0.2, 0.3),),
            rerank_client=client,
        )


def test_retrieval_caps_rerank_response_at_eight_candidates() -> None:
    session = Mock()
    _mock_complete_index(session, [
        (_row(index, f"条件{index}"), index / 100) for index in range(1, 10)
    ])

    with httpx.Client(
        transport=httpx.MockTransport(
            lambda _request: httpx.Response(
                200,
                json={
                    "results": [
                        {"index": index, "relevance_score": 1 - index / 10}
                        for index in range(9)
                    ]
                },
            )
        ),
        base_url=_settings().siliconflow_base_url,
    ) as client:
        candidates = retrieve_green_finance_condition_candidates(
            session,
            {"loan_purpose": "节能建设"},
            "loan_direction",
            _settings(),
            embedding_request=lambda _texts, _settings: ((0.1, 0.2, 0.3),),
            rerank_client=client,
        )

    assert len(candidates) == MAX_RERANK_RESULTS


def test_retrieval_rejects_incomplete_latest_condition_index_before_cloud_call() -> None:
    session = Mock()
    session.scalar.return_value = SimpleNamespace(id=9, version=3)
    session.execute.return_value.one.return_value = (1506, 1506, 1499)
    embedding_request = Mock()

    with pytest.raises(GreenFinanceConditionIndexError, match="index incomplete"):
        retrieve_green_finance_condition_candidates(
            session,
            {"loan_purpose": "节能改造"},
            "loan_direction",
            _settings(),
            embedding_request=embedding_request,
        )

    embedding_request.assert_not_called()


def test_loan_condition_evidence_uses_all_structured_green_fields() -> None:
    from app.services.green_finance_condition_matching import (
        build_green_finance_condition_evidence,
    )

    evidence = build_green_finance_condition_evidence(
        {
            "loan_purpose": "生产线技改",
            "green_project_name": "绿色工厂项目",
            "project_content": "建设余热回收系统",
            "energy_saving_pollution_control": "单位能耗下降30%",
            "green_certifications": "ISO14001",
            "carbon_environmental_benefits": "年减碳100吨",
            "trade_goods_services": "高效节能设备",
        },
        "loan_direction",
    )

    assert "生产线技改" in evidence
    assert "余热回收系统" in evidence
    assert "单位能耗下降30%" in evidence
    assert "ISO14001" in evidence
    assert "年减碳100吨" in evidence


def test_selection_accepts_candidate_and_explicit_no_match() -> None:
    candidate = _candidate()
    evidence = "贷款用于节能改造生产线"
    with _selection_client({"selected_source_row": 12, "selection_basis": "节能改造项目"}) as client:
        assert select_green_finance_condition_label((candidate,), evidence, _settings(), client=client) is candidate.label
    with _selection_client(
        {
            "selected_source_row": NO_MATCH_SOURCE_ROW,
            "selection_basis": "候选条件与当前业务证据不一致。",
        }
    ) as client:
        assert select_green_finance_condition_label((candidate,), evidence, _settings(), client=client) is None


def test_selection_rejects_ungrounded_basis_without_retry() -> None:
    attempts: list[int] = []
    with _selection_client({"selected_source_row": 12, "selection_basis": "完全无关的说明"}, attempts=attempts) as client, pytest.raises(
        GreenFinanceConditionSelectionError, match="must quote"
    ):
        select_green_finance_condition_label((_candidate(),), "贷款用于节能改造生产线", _settings(), client=client)

    assert len(attempts) == 1


def test_selection_retries_only_network_failures_with_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts = 0
    delays: list[float] = []
    monkeypatch.setattr("app.services.green_finance_condition_matching.time.sleep", delays.append)

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise httpx.ConnectTimeout("temporary connection failure")
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({"selected_source_row": 12, "selection_basis": "节能改造项目"}, ensure_ascii=False)}}]})

    with httpx.Client(transport=httpx.MockTransport(handler), base_url=_settings().deepseek_base_url) as client:
        selected = select_green_finance_condition_label((_candidate(),), "贷款用于节能改造生产线", _settings(), client=client)

    assert selected is not None
    assert attempts == 3
    assert delays == [0.5, 1.0]


def test_selection_http_error_is_not_retried() -> None:
    attempts: list[int] = []
    with httpx.Client(
        transport=httpx.MockTransport(lambda _request: attempts.append(1) or httpx.Response(500)),
        base_url=_settings().deepseek_base_url,
    ) as client, pytest.raises(GreenFinanceConditionSelectionError):
        select_green_finance_condition_label((_candidate(),), "贷款用于节能改造生产线", _settings(), client=client)

    assert len(attempts) == 1
