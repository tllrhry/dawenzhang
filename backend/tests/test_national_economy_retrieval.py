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
    build_main_business_revenue_layer,
)
from app.services.national_economy_retrieval import (
    RECALL_LIMIT,
    IndustryCandidate,
    RecallHit,
    aggregate_recall_hits,
    display_chunk_type,
    recall_industry_chunks,
    rerank_candidates,
    retrieve_industry_evidence,
    retrieve_loan_direction_evidence,
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
            major_category_code="A01",
            major_category_name="农、林、牧、渔业",
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
    assert hits[0].major_category_code == "A01"
    assert hits[0].major_category_name == "农、林、牧、渔业"


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


@pytest.mark.parametrize(
    ("chunk_type", "expected"),
    [
        ("definition", "定义"),
        ("include", "包括"),
        ("exclude", "不包括"),
        ("unknown", "unknown"),
    ],
)
def test_display_chunk_type_uses_chinese_labels_with_safe_fallback(
    chunk_type: str, expected: str
) -> None:
    assert display_chunk_type(chunk_type) == expected


def test_rerank_document_uses_chinese_chunk_type_labels() -> None:
    hits = tuple(
        RecallHit("0111", "稻谷种植", label, chunk_type, 2, 0.1)
        for chunk_type, label in (
            ("definition", "行业定义"),
            ("include", "包括水稻"),
            ("exclude", "不包括其他谷物"),
        )
    )

    document = IndustryCandidate("0111", "稻谷种植", 0.1, hits).rerank_document

    assert "[定义] 行业定义" in document
    assert "[包括] 包括水稻" in document
    assert "[不包括] 不包括其他谷物" in document
    assert not any(label in document for label in ("definition", "include", "exclude"))


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


def test_retrieve_uses_only_dominant_business_text_for_locked_enterprise_query() -> None:
    settings = _settings()
    session = Mock()
    session.execute.return_value.all.return_value = [
        SimpleNamespace(
            industry_code="8514",
            industry_name="老年人、残疾人养护服务",
            text="养老服务定义",
            chunk_type="definition",
            source_row=2,
            distance=0.1,
        )
    ]
    requested = []

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"results": [{"index": 0, "relevance_score": 0.95}]},
        )

    dominant_layer = build_main_business_revenue_layer(
        "养老服务70%；计算机销售20%；网络工程10%"
    )
    layers = (
        EvidenceLayer(
            dominant_layer.level,
            (
                *dominant_layer.facts,
                EvidenceFact(
                    "异议说明",
                    "应按计算机销售判断",
                    "计算机销售",
                    source="objection",
                ),
            ),
        ),
        EvidenceLayer(
            EvidenceLevel.BUSINESS_SCOPE,
            (
                EvidenceFact(
                    "营业执照经营范围（全文）",
                    "养老服务；计算机销售",
                    "养老服务；计算机销售",
                ),
            ),
        ),
    )
    with httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url=settings.siliconflow_base_url,
    ) as client:
        retrieve_industry_evidence(
            session,
            layers,
            settings,
            embedding_request=lambda texts: requested.append(tuple(texts))
            or [[0.1, 0.2, 0.3], [0.3, 0.2, 0.1]],
            rerank_client=client,
        )

    assert "养老服务" in requested[0][0]
    assert "计算机销售" not in requested[0][0]
    assert "网络工程" not in requested[0][0]
    assert "应按计算机销售判断" not in requested[0][0]
    assert "计算机销售" in requested[0][1]


def test_retrieve_propagates_embedding_timeout() -> None:
    def timeout(_texts):
        raise httpx.ReadTimeout("embedding timeout")

    with pytest.raises(httpx.ReadTimeout, match="embedding timeout"):
        retrieve_industry_evidence(
            Mock(), _evidence_layers(), _settings(), embedding_request=timeout
        )


def test_retrieve_loan_direction_uses_only_specific_loan_purpose_for_rerank() -> None:
    settings = _settings()
    session = Mock()
    session.execute.return_value.all.return_value = [
        SimpleNamespace(
            industry_code="3742",
            industry_name="航天器及运载火箭制造",
            text="航天器制造",
            chunk_type="definition",
            source_row=2,
            distance=0.1,
        ),
        SimpleNamespace(
            industry_code="3670",
            industry_name="汽车零部件及配件制造",
            text="汽车零部件制造",
            chunk_type="definition",
            source_row=3,
            distance=0.2,
        ),
    ]
    layers = (
        EvidenceLayer(
            EvidenceLevel.MAIN_BUSINESS_REVENUE,
            (EvidenceFact("主营业务及营收占比", "导弹武器系统 90%", "导弹武器系统"),),
        ),
        EvidenceLayer(
            EvidenceLevel.LOAN_PURPOSE,
            (EvidenceFact("贷款用途详细描述", "采购汽车及零部件", "汽车及零部件采购"),),
        ),
        EvidenceLayer(
            EvidenceLevel.BUSINESS_SCOPE,
            (EvidenceFact("营业执照经营范围（全文）", "销售汽车及零部件", "销售汽车及零部件"),),
        ),
    )
    embedding_requests = []
    rerank_payload = {}

    def handler(request: httpx.Request) -> httpx.Response:
        rerank_payload.update(__import__("json").loads(request.content))
        return httpx.Response(
            200,
            json={
                "results": [
                    {"index": 1, "relevance_score": 0.96},
                    {"index": 0, "relevance_score": 0.21},
                ]
            },
        )

    with httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url=settings.siliconflow_base_url,
    ) as client:
        snapshots = retrieve_loan_direction_evidence(
            session,
            layers,
            settings,
            embedding_request=lambda texts: embedding_requests.append(tuple(texts))
            or [[0.1, 0.2, 0.3]],
            rerank_client=client,
        )

    assert len(embedding_requests) == 1
    assert len(embedding_requests[0]) == 1
    assert "priority=3" in embedding_requests[0][0]
    assert "贷款用途详细描述" in embedding_requests[0][0]
    assert "主营业务及营收占比" not in embedding_requests[0][0]
    assert rerank_payload["query"] == embedding_requests[0][0]
    assert "营业执照经营范围" not in rerank_payload["query"]
    assert [snapshot.industry_code for snapshot in snapshots] == ["3670", "3742"]
    assert snapshots[0].evidence_traces[0].level is EvidenceLevel.LOAN_PURPOSE


@pytest.mark.parametrize("loan_purpose", ["经营周转", "补充流动资金"])
def test_retrieve_loan_direction_skips_cloud_calls_for_generic_purpose(
    loan_purpose: str,
) -> None:
    embedding_request = Mock()
    rerank_client = Mock()
    layers = (
        *_evidence_layers(),
        EvidenceLayer(
            EvidenceLevel.LOAN_PURPOSE,
            (EvidenceFact("贷款用途详细描述", loan_purpose, loan_purpose),),
        ),
    )

    snapshots = retrieve_loan_direction_evidence(
        Mock(),
        layers,
        _settings(),
        embedding_request=embedding_request,
        rerank_client=rerank_client,
    )

    assert snapshots == ()
    embedding_request.assert_not_called()
    rerank_client.post.assert_not_called()


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
