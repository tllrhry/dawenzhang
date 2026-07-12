from collections.abc import Callable, Sequence
from dataclasses import dataclass

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import NationalEconomyIndustryChunk
from app.services.national_economy_catalog_chunks import embed_texts
from app.services.national_economy_decision_policy import (
    EvidenceFact,
    EvidenceLayer,
    EvidenceLevel,
    is_generic_loan_purpose,
)


RECALL_LIMIT = 30
MIN_RERANK_RESULTS = 5
MAX_RERANK_RESULTS = 8
CHUNK_TYPE_LABELS = {
    "definition": "定义",
    "include": "包括",
    "exclude": "不包括",
}
CHUNK_TYPE_ORDER = {chunk_type: index for index, chunk_type in enumerate(CHUNK_TYPE_LABELS)}
LOAN_PURPOSE_FIELD_LABEL = "贷款用途详细描述"
CREDIT_APPROVAL_FIELD_LABEL = "授信审批意见"
TRADE_GOODS_SERVICES_FIELD_LABEL = "贸易合同核心交易品类 / 服务内容"


def display_chunk_type(chunk_type: str) -> str:
    return CHUNK_TYPE_LABELS.get(chunk_type, chunk_type)


@dataclass(frozen=True)
class RecallHit:
    industry_code: str
    industry_name: str
    text: str
    chunk_type: str
    source_row: int
    distance: float
    major_category_code: str | None = None
    major_category_name: str | None = None


@dataclass(frozen=True)
class IndustryCandidate:
    industry_code: str
    industry_name: str
    distance: float
    hits: tuple[RecallHit, ...]
    evidence_traces: tuple["CandidateEvidenceTrace", ...] = ()
    major_category_code: str | None = None
    major_category_name: str | None = None

    @property
    def rerank_document(self) -> str:
        if self.evidence_traces:
            evidence = "\n".join(
                f"priority={int(trace.level)} level={trace.level.name} "
                f"evidence_fields={','.join(fact.field_label for fact in trace.facts)} "
                f"catalog_fragment=[{display_chunk_type(hit.chunk_type)}] {hit.text}"
                for trace in self.evidence_traces
                for hit in trace.hits
            )
        else:
            evidence = "\n".join(
                f"[{display_chunk_type(hit.chunk_type)}] {hit.text}" for hit in self.hits
            )
        return f"{self.industry_code} {self.industry_name}\n{evidence}"


@dataclass(frozen=True)
class EvidenceSnapshot:
    industry_code: str
    industry_name: str
    vector_score: float
    rerank_score: float
    hits: tuple[RecallHit, ...]
    evidence_traces: tuple["CandidateEvidenceTrace", ...] = ()
    major_category_code: str | None = None
    major_category_name: str | None = None


@dataclass(frozen=True)
class CandidateEvidenceTrace:
    level: EvidenceLevel
    facts: tuple[EvidenceFact, ...]
    hits: tuple[RecallHit, ...]


EmbeddingRequest = Callable[[Sequence[str]], Sequence[Sequence[float]]]


def recall_industry_chunks(
    session: Session,
    query_embedding: Sequence[float],
) -> tuple[RecallHit, ...]:
    distance = NationalEconomyIndustryChunk.embedding.cosine_distance(list(query_embedding))
    statement = (
        select(
            NationalEconomyIndustryChunk.major_category_code,
            NationalEconomyIndustryChunk.major_category_name,
            NationalEconomyIndustryChunk.industry_code,
            NationalEconomyIndustryChunk.industry_name,
            NationalEconomyIndustryChunk.text,
            NationalEconomyIndustryChunk.chunk_type,
            NationalEconomyIndustryChunk.source_row,
            distance.label("distance"),
        )
        .order_by(distance)
        .limit(RECALL_LIMIT)
    )
    rows = session.execute(statement).all()
    return tuple(
        RecallHit(
            industry_code=row.industry_code,
            industry_name=row.industry_name,
            text=row.text,
            chunk_type=row.chunk_type,
            source_row=row.source_row,
            distance=float(row.distance),
            major_category_code=getattr(row, "major_category_code", None),
            major_category_name=getattr(row, "major_category_name", None),
        )
        for row in rows
    )


def aggregate_recall_hits(hits: Sequence[RecallHit]) -> tuple[IndustryCandidate, ...]:
    grouped: dict[str, list[RecallHit]] = {}
    for hit in hits:
        grouped.setdefault(hit.industry_code, []).append(hit)
    candidates = [
        IndustryCandidate(
            industry_code=industry_hits[0].industry_code,
            industry_name=industry_hits[0].industry_name,
            distance=min(hit.distance for hit in industry_hits),
            hits=tuple(sorted(industry_hits, key=lambda hit: hit.distance)),
            major_category_code=industry_hits[0].major_category_code,
            major_category_name=industry_hits[0].major_category_name,
        )
        for industry_hits in grouped.values()
    ]
    return tuple(sorted(candidates, key=lambda candidate: candidate.distance))


def aggregate_layer_recall_hits(
    layer_hits: Sequence[tuple[EvidenceLayer, Sequence[RecallHit]]],
) -> tuple[IndustryCandidate, ...]:
    grouped: dict[str, list[tuple[EvidenceLayer, RecallHit]]] = {}
    for layer, hits in layer_hits:
        for hit in hits:
            grouped.setdefault(hit.industry_code, []).append((layer, hit))

    candidates = []
    for matches in grouped.values():
        first_hit = matches[0][1]
        traces = tuple(
            CandidateEvidenceTrace(
                level=layer.level,
                facts=layer.usable_facts,
                hits=tuple(
                    sorted(
                        (
                            hit
                            for matched_layer, hit in matches
                            if matched_layer.level == layer.level
                        ),
                        key=lambda hit: hit.distance,
                    )
                ),
            )
            for layer, _ in layer_hits
            if any(matched_layer.level == layer.level for matched_layer, _ in matches)
        )
        unique_hits = {
            (
                hit.industry_code,
                hit.industry_name,
                hit.text,
                hit.chunk_type,
                hit.source_row,
            ): hit
            for _, hit in matches
        }
        candidates.append(
            IndustryCandidate(
                industry_code=first_hit.industry_code,
                industry_name=first_hit.industry_name,
                distance=min(hit.distance for _, hit in matches),
                hits=tuple(sorted(unique_hits.values(), key=lambda hit: hit.distance)),
                evidence_traces=traces,
                major_category_code=first_hit.major_category_code,
                major_category_name=first_hit.major_category_name,
            )
        )
    return tuple(sorted(candidates, key=lambda candidate: candidate.distance))


def rerank_candidates(
    evidence_layers: Sequence[EvidenceLayer],
    candidates: Sequence[IndustryCandidate],
    settings: Settings,
    top_n: int = MAX_RERANK_RESULTS,
    client: httpx.Client | None = None,
) -> tuple[EvidenceSnapshot, ...]:
    if not MIN_RERANK_RESULTS <= top_n <= MAX_RERANK_RESULTS:
        raise ValueError("top_n must be between 5 and 8")
    if not candidates:
        return ()
    ordered_evidence = _ordered_available_layers(evidence_layers)
    if not ordered_evidence:
        raise ValueError("at least one usable evidence layer is required")
    if not settings.siliconflow_api_key:
        raise RuntimeError("SILICONFLOW_API_KEY is required for reranking")

    owns_client = client is None
    http_client = client or httpx.Client(
        base_url=settings.siliconflow_base_url.rstrip("/"),
        timeout=httpx.Timeout(
            settings.siliconflow_timeout_seconds,
            connect=settings.http_connect_timeout_seconds,
        ),
    )
    try:
        response = http_client.post(
            "/rerank",
            headers={"Authorization": f"Bearer {settings.siliconflow_api_key}"},
            json={
                "model": settings.siliconflow_rerank_model,
                "query": serialize_ordered_evidence(ordered_evidence),
                "documents": [candidate.rerank_document for candidate in candidates],
                "top_n": min(top_n, len(candidates)),
                "return_documents": False,
            },
        )
        response.raise_for_status()
        payload = response.json()
        results = payload.get("results")
        if not isinstance(results, list):
            raise ValueError("rerank response results must be a list")

        snapshots: list[EvidenceSnapshot] = []
        for result in results:
            if not isinstance(result, dict) or "index" not in result or "relevance_score" not in result:
                raise ValueError("rerank response item is missing index or relevance_score")
            index = result["index"]
            if not isinstance(index, int) or not 0 <= index < len(candidates):
                raise ValueError("rerank response index is out of range")
            candidate = candidates[index]
            snapshots.append(
                EvidenceSnapshot(
                    industry_code=candidate.industry_code,
                    industry_name=candidate.industry_name,
                    vector_score=1.0 - candidate.distance,
                    rerank_score=float(result["relevance_score"]),
                    hits=candidate.hits,
                    evidence_traces=candidate.evidence_traces,
                    major_category_code=candidate.major_category_code,
                    major_category_name=candidate.major_category_name,
                )
            )
        return tuple(snapshots[:top_n])
    finally:
        if owns_client:
            http_client.close()


def complete_finalist_catalog_fragments(
    session: Session,
    snapshots: Sequence[EvidenceSnapshot],
) -> tuple[EvidenceSnapshot, ...]:
    if not snapshots:
        return ()

    finalist_codes = tuple(dict.fromkeys(snapshot.industry_code for snapshot in snapshots))
    statement = select(
        NationalEconomyIndustryChunk.major_category_code,
        NationalEconomyIndustryChunk.major_category_name,
        NationalEconomyIndustryChunk.industry_code,
        NationalEconomyIndustryChunk.industry_name,
        NationalEconomyIndustryChunk.text,
        NationalEconomyIndustryChunk.chunk_type,
        NationalEconomyIndustryChunk.source_row,
    ).where(NationalEconomyIndustryChunk.industry_code.in_(finalist_codes))
    rows = session.execute(statement).all()

    catalog_hits: dict[str, list[RecallHit]] = {}
    for row in sorted(
        rows,
        key=lambda item: (
            item.industry_code,
            CHUNK_TYPE_ORDER.get(item.chunk_type, len(CHUNK_TYPE_ORDER)),
            item.source_row,
            item.text,
        ),
    ):
        catalog_hits.setdefault(row.industry_code, []).append(
            RecallHit(
                industry_code=row.industry_code,
                industry_name=row.industry_name,
                text=row.text,
                chunk_type=row.chunk_type,
                source_row=row.source_row,
                distance=1.0,
                major_category_code=getattr(row, "major_category_code", None),
                major_category_name=getattr(row, "major_category_name", None),
            )
        )

    completed = []
    for snapshot in snapshots:
        unique_hits: dict[tuple[int, str], RecallHit] = {}
        for hit in (*snapshot.hits, *catalog_hits.get(snapshot.industry_code, ())):
            unique_hits.setdefault((hit.source_row, hit.chunk_type), hit)
        sorted_hits = tuple(
            sorted(
                unique_hits.values(),
                key=lambda hit: (
                    CHUNK_TYPE_ORDER.get(hit.chunk_type, len(CHUNK_TYPE_ORDER)),
                    hit.source_row,
                ),
            )
        )
        completed.append(
            EvidenceSnapshot(
                industry_code=snapshot.industry_code,
                industry_name=snapshot.industry_name,
                vector_score=snapshot.vector_score,
                rerank_score=snapshot.rerank_score,
                hits=sorted_hits,
                evidence_traces=snapshot.evidence_traces,
                major_category_code=snapshot.major_category_code,
                major_category_name=snapshot.major_category_name,
            )
        )
    return tuple(completed)


def retrieve_industry_evidence(
    session: Session,
    evidence_layers: Sequence[EvidenceLayer],
    settings: Settings,
    top_n: int = MAX_RERANK_RESULTS,
    embedding_request: EmbeddingRequest | None = None,
    rerank_client: httpx.Client | None = None,
) -> tuple[EvidenceSnapshot, ...]:
    ordered_evidence = _ordered_available_layers(evidence_layers)
    if not ordered_evidence:
        raise ValueError("at least one usable evidence layer is required")
    layer_queries = tuple(serialize_evidence_layer(layer) for layer in ordered_evidence)
    request = embedding_request or (lambda texts: embed_texts(texts, settings))
    embeddings = tuple(request(layer_queries))
    if len(embeddings) != len(layer_queries):
        raise ValueError("query embedding response must match usable evidence layers")
    if any(len(embedding) != settings.embedding_dimension for embedding in embeddings):
        raise ValueError("query embedding dimension does not match configuration")
    layer_hits = tuple(
        (layer, recall_industry_chunks(session, embedding))
        for layer, embedding in zip(ordered_evidence, embeddings, strict=True)
    )
    candidates = aggregate_layer_recall_hits(layer_hits)
    return complete_finalist_catalog_fragments(
        session,
        rerank_candidates(
            ordered_evidence,
            candidates,
            settings,
            top_n=top_n,
            client=rerank_client,
        ),
    )


def retrieve_loan_direction_evidence(
    session: Session,
    evidence_layers: Sequence[EvidenceLayer],
    settings: Settings,
    top_n: int = MAX_RERANK_RESULTS,
    embedding_request: EmbeddingRequest | None = None,
    rerank_client: httpx.Client | None = None,
) -> tuple[EvidenceSnapshot, ...]:
    ordered_evidence = _ordered_available_layers(evidence_layers)
    loan_purpose_layer = next(
        (
            layer
            for layer in ordered_evidence
            if layer.level is EvidenceLevel.LOAN_PURPOSE
        ),
        None,
    )
    loan_purpose_facts = (
        tuple(
            fact
            for fact in loan_purpose_layer.usable_facts
            if fact.field_label == LOAN_PURPOSE_FIELD_LABEL
        )
        if loan_purpose_layer is not None
        else ()
    )
    credit_approval_facts = (
        tuple(
            fact
            for fact in loan_purpose_layer.usable_facts
            if fact.field_label == CREDIT_APPROVAL_FIELD_LABEL
        )
        if loan_purpose_layer is not None
        else ()
    )
    trade_layer = next(
        (
            layer
            for layer in ordered_evidence
            if layer.level is EvidenceLevel.TRADE_AND_INDUSTRY_CHAIN
        ),
        None,
    )
    trade_goods_facts = (
        tuple(
            fact
            for fact in trade_layer.usable_facts
            if fact.field_label == TRADE_GOODS_SERVICES_FIELD_LABEL
        )
        if trade_layer is not None
        else ()
    )
    loan_purpose_is_generic = not loan_purpose_facts or all(
        is_generic_loan_purpose(fact.raw_text) for fact in loan_purpose_facts
    )
    credit_approval_is_specific = any(
        not is_generic_loan_purpose(fact.raw_text) for fact in credit_approval_facts
    )
    if (
        loan_purpose_is_generic
        and not trade_goods_facts
        and not credit_approval_is_specific
    ):
        return ()

    query_layers = _ordered_available_layers(
        tuple(
            layer
            for layer in (
                loan_purpose_layer,
                EvidenceLayer(
                    level=EvidenceLevel.TRADE_AND_INDUSTRY_CHAIN,
                    facts=trade_goods_facts,
                )
                if trade_goods_facts
                else None,
            )
            if layer is not None
        )
    )
    queries = tuple(serialize_evidence_layer(layer) for layer in query_layers)
    request = embedding_request or (lambda texts: embed_texts(texts, settings))
    embeddings = tuple(request(queries))
    if len(embeddings) != len(queries):
        raise ValueError("query embedding response must match loan direction queries")
    if any(len(embedding) != settings.embedding_dimension for embedding in embeddings):
        raise ValueError("query embedding dimension does not match configuration")

    layer_hits = tuple(
        (layer, recall_industry_chunks(session, embedding))
        for layer, embedding in zip(query_layers, embeddings, strict=True)
    )
    candidates = aggregate_layer_recall_hits(layer_hits)
    return complete_finalist_catalog_fragments(
        session,
        rerank_candidates(
            query_layers,
            candidates,
            settings,
            top_n=top_n,
            client=rerank_client,
        ),
    )


def serialize_evidence_layer(layer: EvidenceLayer) -> str:
    dominant_facts = tuple(
        fact
        for fact in layer.usable_facts
        if fact.field_label == "主营业务及营收占比（主导主营）"
    )
    facts_for_query = dominant_facts or layer.usable_facts
    serialized_facts = []
    for fact in facts_for_query:
        query_text = (
            fact.indicated_business
            if fact.field_label == "主营业务及营收占比（主导主营）"
            else fact.raw_text
        )
        serialized_facts.append(
            f"- [{fact.field_label}] {query_text.strip()} (source={fact.source})"
        )
    facts = "\n".join(serialized_facts)
    return f"priority={int(layer.level)} level={layer.level.name}\n{facts}"


def serialize_ordered_evidence(evidence_layers: Sequence[EvidenceLayer]) -> str:
    return "\n\n".join(
        serialize_evidence_layer(layer)
        for layer in _ordered_available_layers(evidence_layers)
    )


def _ordered_available_layers(
    evidence_layers: Sequence[EvidenceLayer],
) -> tuple[EvidenceLayer, ...]:
    ordered = tuple(sorted(evidence_layers, key=lambda layer: layer.level))
    levels = tuple(layer.level for layer in ordered)
    if len(levels) != len(set(levels)):
        raise ValueError("evidence levels must be unique")
    return tuple(layer for layer in ordered if layer.is_available)
