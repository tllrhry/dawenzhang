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
    EvidenceSnapshot,
    IndustryCandidate,
    RecallHit,
    aggregate_recall_hits,
    complete_finalist_catalog_fragments,
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


def test_complete_finalists_adds_all_catalog_fragments_without_reordering() -> None:
    session = Mock()
    session.execute.return_value.all.return_value = [
        SimpleNamespace(
            major_category_code="F51",
            major_category_name="批发业",
            industry_code="5111",
            industry_name="谷物、豆及薯类批发",
            text="不包括面向最终消费者的粮油零售",
            chunk_type="exclude",
            source_row=11,
        ),
        SimpleNamespace(
            major_category_code="F51",
            major_category_name="批发业",
            industry_code="5111",
            industry_name="谷物、豆及薯类批发",
            text="包括谷物批发",
            chunk_type="include",
            source_row=11,
        ),
        SimpleNamespace(
            major_category_code="F51",
            major_category_name="批发业",
            industry_code="5111",
            industry_name="谷物、豆及薯类批发",
            text="目录中的重复定义",
            chunk_type="definition",
            source_row=11,
        ),
        SimpleNamespace(
            major_category_code="F52",
            major_category_name="零售业",
            industry_code="5221",
            industry_name="粮油零售",
            text="面向最终消费者的粮油零售",
            chunk_type="definition",
            source_row=22,
        ),
    ]
    finalists = (
        EvidenceSnapshot(
            "5221",
            "粮油零售",
            0.91,
            0.99,
            (RecallHit("5221", "粮油零售", "召回定义", "definition", 22, 0.09),),
        ),
        EvidenceSnapshot(
            "5111",
            "谷物、豆及薯类批发",
            0.88,
            0.97,
            (RecallHit("5111", "谷物、豆及薯类批发", "召回定义", "definition", 11, 0.12),),
        ),
    )

    completed = complete_finalist_catalog_fragments(session, finalists)

    statement = session.execute.call_args.args[0]
    assert set(statement.compile().params["industry_code_1"]) == {"5111", "5221"}
    assert [(item.industry_code, item.rerank_score) for item in completed] == [
        ("5221", 0.99),
        ("5111", 0.97),
    ]
    assert [(hit.chunk_type, hit.text) for hit in completed[1].hits] == [
        ("definition", "召回定义"),
        ("include", "包括谷物批发"),
        ("exclude", "不包括面向最终消费者的粮油零售"),
    ]
    assert len(completed[1].hits) == 3
    assert [(hit.chunk_type, hit.text) for hit in completed[0].hits] == [
        ("definition", "召回定义")
    ]


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


def test_enterprise_candidates_keep_full_trade_layer_and_their_own_ranking() -> None:
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
            industry_code="5263",
            industry_name="汽车零配件零售",
            text="汽车零配件零售",
            chunk_type="definition",
            source_row=3,
            distance=0.2,
        ),
    ]
    layers = (
        EvidenceLayer(
            EvidenceLevel.MAIN_BUSINESS_REVENUE,
            (EvidenceFact("主营业务及营收占比", "航天器制造 90%", "航天器制造"),),
        ),
        EvidenceLayer(
            EvidenceLevel.TRADE_AND_INDUSTRY_CHAIN,
            (
                EvidenceFact(
                    "贸易合同核心交易品类 / 服务内容",
                    "汽车零配件",
                    "汽车零配件",
                ),
                EvidenceFact("交易对手主营行业", "汽车零售", "汽车零售"),
                EvidenceFact("产业链定位", "下游销售", "下游销售"),
            ),
        ),
        EvidenceLayer(
            EvidenceLevel.LOAN_PURPOSE,
            (EvidenceFact("贷款用途详细描述", "采购零配件", "采购零配件"),),
        ),
        EvidenceLayer(
            EvidenceLevel.BUSINESS_SCOPE,
            (EvidenceFact("营业执照经营范围（全文）", "航天器制造；汽车销售", "航天器制造；汽车销售"),),
        ),
    )
    embedding_requests = []

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "results": [
                    {"index": 0, "relevance_score": 0.99},
                    {"index": 1, "relevance_score": 0.4},
                ]
            },
        )

    with httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url=settings.siliconflow_base_url,
    ) as client:
        snapshots = retrieve_industry_evidence(
            session,
            layers,
            settings,
            embedding_request=lambda texts: embedding_requests.append(tuple(texts))
            or [[0.1, 0.2, 0.3]] * 4,
            rerank_client=client,
        )

    assert len(embedding_requests[0]) == 4
    enterprise_trade_query = embedding_requests[0][1]
    assert "贸易合同核心交易品类 / 服务内容" in enterprise_trade_query
    assert "交易对手主营行业" in enterprise_trade_query
    assert "产业链定位" in enterprise_trade_query
    assert [snapshot.industry_code for snapshot in snapshots] == ["3742", "5263"]


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


def test_retrieve_loan_direction_merges_trade_hits_and_reranks_once() -> None:
    settings = _settings()
    session = Mock()
    loan_hits = Mock()
    loan_hits.all.return_value = [
        SimpleNamespace(
            industry_code="3742",
            industry_name="航天器及运载火箭制造",
            text="航天器制造",
            chunk_type="definition",
            source_row=2,
            distance=0.2,
        ),
        SimpleNamespace(
            industry_code="5173",
            industry_name="汽车及零配件批发",
            text="汽车及零配件批发",
            chunk_type="definition",
            source_row=3,
            distance=0.3,
        ),
    ]
    trade_hits = Mock()
    trade_hits.all.return_value = [
        SimpleNamespace(
            industry_code="5173",
            industry_name="汽车及零配件批发",
            text="汽车及零配件批发",
            chunk_type="definition",
            source_row=3,
            distance=0.05,
        ),
        SimpleNamespace(
            industry_code="5263",
            industry_name="汽车零配件零售",
            text="汽车零配件零售",
            chunk_type="definition",
            source_row=4,
            distance=0.1,
        ),
    ]
    completed_hits = Mock()
    completed_hits.all.return_value = []
    session.execute.side_effect = [loan_hits, trade_hits, completed_hits]
    layers = (
        EvidenceLayer(
            EvidenceLevel.TRADE_AND_INDUSTRY_CHAIN,
            (
                EvidenceFact(
                    "贸易合同核心交易品类 / 服务内容",
                    "汽车零配件",
                    "汽车零配件",
                ),
                EvidenceFact("交易对手主营行业", "钢铁制造", "钢铁制造"),
                EvidenceFact("产业链定位", "上游供应商", "上游供应商"),
            ),
        ),
        EvidenceLayer(
            EvidenceLevel.LOAN_PURPOSE,
            (
                EvidenceFact(
                    "贷款用途详细描述",
                    "航天器生产线建设",
                    "航天器生产线建设",
                ),
            ),
        ),
    )
    embedding_requests = []
    rerank_payloads = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = __import__("json").loads(request.content)
        rerank_payloads.append(payload)
        assert len(payload["documents"]) == 3
        assert sum("5173 汽车及零配件批发" in item for item in payload["documents"]) == 1
        return httpx.Response(
            200,
            json={
                "results": [
                    {"index": 1, "relevance_score": 0.98},
                    {"index": 0, "relevance_score": 0.91},
                    {"index": 2, "relevance_score": 0.25},
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
            or [[0.1, 0.2, 0.3], [0.3, 0.2, 0.1]],
            rerank_client=client,
        )

    assert len(embedding_requests) == 1
    assert len(embedding_requests[0]) == 2
    trade_query, loan_query = embedding_requests[0]
    assert "贸易合同核心交易品类 / 服务内容" in trade_query
    assert "汽车零配件" in trade_query
    assert "交易对手主营行业" not in trade_query
    assert "产业链定位" not in trade_query
    assert "贷款用途详细描述" in loan_query
    assert len(rerank_payloads) == 1
    assert rerank_payloads[0]["query"] == f"{trade_query}\n\n{loan_query}"
    assert [snapshot.industry_code for snapshot in snapshots] == [
        "5263",
        "5173",
        "3742",
    ]
    assert [trace.level for trace in snapshots[1].evidence_traces] == [
        EvidenceLevel.TRADE_AND_INDUSTRY_CHAIN,
        EvidenceLevel.LOAN_PURPOSE,
    ]


def test_retrieve_loan_direction_runs_for_generic_purpose_with_specific_trade() -> None:
    settings = _settings()
    session = Mock()
    loan_hits = Mock()
    loan_hits.all.return_value = []
    trade_hits = Mock()
    trade_hits.all.return_value = [
        SimpleNamespace(
            industry_code="5263",
            industry_name="汽车零配件零售",
            text="汽车零配件零售",
            chunk_type="definition",
            source_row=4,
            distance=0.1,
        )
    ]
    completed_hits = Mock()
    completed_hits.all.return_value = []
    session.execute.side_effect = [loan_hits, trade_hits, completed_hits]
    layers = (
        EvidenceLayer(
            EvidenceLevel.TRADE_AND_INDUSTRY_CHAIN,
            (
                EvidenceFact(
                    "贸易合同核心交易品类 / 服务内容",
                    "汽车零配件",
                    "汽车零配件",
                ),
            ),
        ),
        EvidenceLayer(
            EvidenceLevel.LOAN_PURPOSE,
            (EvidenceFact("贷款用途详细描述", "补充流动资金", "补充流动资金"),),
        ),
    )
    requested = []

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"results": [{"index": 0, "relevance_score": 0.97}]},
        )

    with httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url=settings.siliconflow_base_url,
    ) as client:
        snapshots = retrieve_loan_direction_evidence(
            session,
            layers,
            settings,
            embedding_request=lambda texts: requested.append(tuple(texts))
            or [[0.1, 0.2, 0.3], [0.3, 0.2, 0.1]],
            rerank_client=client,
        )

    assert len(requested[0]) == 2
    assert snapshots[0].industry_code == "5263"


def test_retrieve_loan_direction_runs_for_specific_credit_approval() -> None:
    settings = _settings()
    session = Mock()
    recall_result = Mock()
    recall_result.all.return_value = [
        SimpleNamespace(
            industry_code="3562",
            industry_name="半导体器件专用设备制造",
            text="半导体器件专用设备制造",
            chunk_type="definition",
            source_row=4,
            distance=0.1,
        )
    ]
    completed_result = Mock()
    completed_result.all.return_value = []
    session.execute.side_effect = [recall_result, completed_result]
    layers = (
        EvidenceLayer(
            EvidenceLevel.LOAN_PURPOSE,
            (
                EvidenceFact("贷款用途详细描述", "补充流动资金", "补充流动资金"),
                EvidenceFact(
                    "授信审批意见",
                    "本笔贷款只可用于购买半导体生产设备",
                    "购买半导体生产设备",
                ),
            ),
        ),
    )
    requested = []

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"results": [{"index": 0, "relevance_score": 0.98}]},
        )

    with httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url=settings.siliconflow_base_url,
    ) as client:
        snapshots = retrieve_loan_direction_evidence(
            session,
            layers,
            settings,
            embedding_request=lambda texts: requested.append(tuple(texts))
            or [[0.1, 0.2, 0.3]],
            rerank_client=client,
        )

    assert len(requested[0]) == 1
    assert "补充流动资金" in requested[0][0]
    assert "授信审批意见" in requested[0][0]
    assert "本笔贷款只可用于购买半导体生产设备" in requested[0][0]
    assert snapshots[0].industry_code == "3562"
    assert snapshots[0].evidence_traces[0].facts == layers[0].usable_facts


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
