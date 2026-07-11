from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
from sqlalchemy.dialects import postgresql

from app.core.config import Settings
from app.services.national_economy_decision_policy import (
    EvidenceFact,
    EvidenceLayer,
    EvidenceLevel,
)
from app.services.national_economy_retrieval import (
    RECALL_LIMIT,
    IndustryCandidate,
    RecallHit,
    aggregate_recall_hits,
    recall_industry_chunks,
    rerank_candidates,
    retrieve_industry_evidence,
)


def _settings() -> Settings:
    return Settings(SILICONFLOW_API_KEY="secret", EMBEDDING_DIMENSION=3)


def _hit(code: str, name: str, text: str, distance: float) -> RecallHit:
    return RecallHit(code, name, text, "definition", 2, distance)


def _evidence_layers() -> tuple[EvidenceLayer, ...]:
    return (
        EvidenceLayer(
            EvidenceLevel.MAIN_BUSINESS_REVENUE,
            (EvidenceFact("主营业务及营收占比", "水稻 90%", "水稻 90%"),),
        ),
        EvidenceLayer(
            EvidenceLevel.BUSINESS_SCOPE,
            (EvidenceFact("营业执照经营范围（全文）", "谷物种植", "谷物种植"),),
        ),
    )


def test_recall_uses_pgvector_cosine_distance_and_top_30() -> None:
    session = Mock()
    session.execute.return_value.all.return_value = [
        SimpleNamespace(
            industry_code="0111",
            industry_name="稻谷种植",
            text="稻谷种植定义",
            chunk_type="definition",
            source_row=2,
            distance=0.12,
        )
    ]

    hits = recall_industry_chunks(session, [0.1, 0.2, 0.3])

    statement = session.execute.call_args.args[0]
    sql = str(statement.compile(dialect=postgresql.dialect()))
    assert "<=>" in sql
    assert statement._limit_clause.value == RECALL_LIMIT
    assert hits[0].industry_code == "0111"


def test_aggregate_recall_hits_groups_by_four_digit_industry_code() -> None:
    candidates = aggregate_recall_hits(
        (
            _hit("0111", "稻谷种植", "包括水稻", 0.2),
            _hit("0112", "小麦种植", "包括小麦", 0.3),
            _hit("0111", "稻谷种植", "稻谷定义", 0.1),
        )
    )

    assert [candidate.industry_code for candidate in candidates] == ["0111", "0112"]
    assert candidates[0].distance == 0.1
    assert [hit.text for hit in candidates[0].hits] == ["稻谷定义", "包括水稻"]


def test_rerank_returns_top_evidence_snapshots_with_configured_model() -> None:
    settings = _settings()
    candidates = tuple(
        IndustryCandidate(str(index).zfill(4), f"行业{index}", index / 100, (_hit(str(index).zfill(4), f"行业{index}", f"证据{index}", index / 100),))
        for index in range(10)
    )
    captured_payload = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured_payload.update(__import__("json").loads(request.content))
        return httpx.Response(
            200,
            json={"results": [{"index": index, "relevance_score": 1 - index / 10} for index in range(8)]},
        )

    with httpx.Client(transport=httpx.MockTransport(handler), base_url=settings.siliconflow_base_url) as client:
        snapshots = rerank_candidates(
            _evidence_layers(), candidates, settings, client=client
        )

    assert captured_payload["model"] == settings.siliconflow_rerank_model
    assert captured_payload["top_n"] == 8
    assert "priority=1" in captured_payload["query"]
    assert "主营业务及营收占比" in captured_payload["query"]
    assert captured_payload["query"].index("priority=1") < captured_payload["query"].index("priority=4")
    assert len(snapshots) == 8
    assert snapshots[0].hits[0].text == "证据0"


@pytest.mark.parametrize("top_n", [4, 9])
def test_rerank_rejects_result_count_outside_five_to_eight(top_n: int) -> None:
    with pytest.raises(ValueError, match="between 5 and 8"):
        rerank_candidates((), (), _settings(), top_n=top_n)


def test_retrieve_vectorizes_query_then_reranks_aggregated_candidates() -> None:
    settings = _settings()
    session = Mock()
    session.execute.return_value.all.return_value = [
        SimpleNamespace(industry_code="0111", industry_name="稻谷种植", text="定义", chunk_type="definition", source_row=2, distance=0.1),
        SimpleNamespace(industry_code="0111", industry_name="稻谷种植", text="包括", chunk_type="include", source_row=2, distance=0.2),
    ]
    requested = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = __import__("json").loads(request.content)
        assert len(payload["documents"]) == 1
        return httpx.Response(200, json={"results": [{"index": 0, "relevance_score": 0.88}]})

    with httpx.Client(transport=httpx.MockTransport(handler), base_url=settings.siliconflow_base_url) as client:
        snapshots = retrieve_industry_evidence(
            session,
            _evidence_layers(),
            settings,
            embedding_request=lambda texts: requested.append(tuple(texts))
            or [[0.1, 0.2, 0.3], [0.3, 0.2, 0.1]],
            rerank_client=client,
        )

    assert len(requested) == 1
    assert "priority=1" in requested[0][0]
    assert "priority=4" in requested[0][1]
    assert len(snapshots) == 1
    assert snapshots[0].industry_code == "0111"
    assert len(snapshots[0].hits) == 2
    assert [trace.level for trace in snapshots[0].evidence_traces] == [
        EvidenceLevel.MAIN_BUSINESS_REVENUE,
        EvidenceLevel.BUSINESS_SCOPE,
    ]
    assert snapshots[0].evidence_traces[0].facts[0].field_label == "主营业务及营收占比"


def test_retrieve_propagates_embedding_timeout() -> None:
    def timeout(_texts):
        raise httpx.ReadTimeout("embedding timeout")

    with pytest.raises(httpx.ReadTimeout, match="embedding timeout"):
        retrieve_industry_evidence(
            Mock(), _evidence_layers(), _settings(), embedding_request=timeout
        )


def test_rerank_propagates_non_success_response() -> None:
    candidate = IndustryCandidate("0111", "稻谷种植", 0.1, (_hit("0111", "稻谷种植", "定义", 0.1),))

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"message": "unavailable"})

    with httpx.Client(transport=httpx.MockTransport(handler), base_url=_settings().siliconflow_base_url) as client:
        with pytest.raises(httpx.HTTPStatusError):
            rerank_candidates(
                _evidence_layers(), (candidate,), _settings(), client=client
            )


def test_rerank_rejects_malformed_response() -> None:
    candidate = IndustryCandidate("0111", "稻谷种植", 0.1, (_hit("0111", "稻谷种植", "定义", 0.1),))

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": [{"index": 0}]})

    with httpx.Client(transport=httpx.MockTransport(handler), base_url=_settings().siliconflow_base_url) as client:
        with pytest.raises(ValueError, match="missing index or relevance_score"):
            rerank_candidates(
                _evidence_layers(), (candidate,), _settings(), client=client
            )
