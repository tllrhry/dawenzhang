from collections.abc import Callable, Sequence
from dataclasses import dataclass

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import NationalEconomyIndustryChunk
from app.services.national_economy_catalog_chunks import embed_texts


RECALL_LIMIT = 30
MIN_RERANK_RESULTS = 5
MAX_RERANK_RESULTS = 8


@dataclass(frozen=True)
class RecallHit:
    industry_code: str
    industry_name: str
    text: str
    chunk_type: str
    source_row: int
    distance: float


@dataclass(frozen=True)
class IndustryCandidate:
    industry_code: str
    industry_name: str
    distance: float
    hits: tuple[RecallHit, ...]

    @property
    def rerank_document(self) -> str:
        evidence = "\n".join(
            f"[{hit.chunk_type}] {hit.text}" for hit in self.hits
        )
        return f"{self.industry_code} {self.industry_name}\n{evidence}"


@dataclass(frozen=True)
class EvidenceSnapshot:
    industry_code: str
    industry_name: str
    vector_score: float
    rerank_score: float
    hits: tuple[RecallHit, ...]


EmbeddingRequest = Callable[[Sequence[str]], Sequence[Sequence[float]]]


def recall_industry_chunks(
    session: Session,
    query_embedding: Sequence[float],
) -> tuple[RecallHit, ...]:
    distance = NationalEconomyIndustryChunk.embedding.cosine_distance(list(query_embedding))
    statement = (
        select(
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
        )
        for industry_hits in grouped.values()
    ]
    return tuple(sorted(candidates, key=lambda candidate: candidate.distance))


def rerank_candidates(
    query: str,
    candidates: Sequence[IndustryCandidate],
    settings: Settings,
    top_n: int = MAX_RERANK_RESULTS,
    client: httpx.Client | None = None,
) -> tuple[EvidenceSnapshot, ...]:
    if not MIN_RERANK_RESULTS <= top_n <= MAX_RERANK_RESULTS:
        raise ValueError("top_n must be between 5 and 8")
    if not candidates:
        return ()
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
                "query": query,
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
                )
            )
        return tuple(snapshots[:top_n])
    finally:
        if owns_client:
            http_client.close()


def retrieve_industry_evidence(
    session: Session,
    query: str,
    settings: Settings,
    top_n: int = MAX_RERANK_RESULTS,
    embedding_request: EmbeddingRequest | None = None,
    rerank_client: httpx.Client | None = None,
) -> tuple[EvidenceSnapshot, ...]:
    normalized_query = query.strip()
    if not normalized_query:
        raise ValueError("query must not be blank")
    request = embedding_request or (lambda texts: embed_texts(texts, settings))
    embeddings = tuple(request((normalized_query,)))
    if len(embeddings) != 1:
        raise ValueError("query embedding response must contain exactly one vector")
    if len(embeddings[0]) != settings.embedding_dimension:
        raise ValueError("query embedding dimension does not match configuration")
    hits = recall_industry_chunks(session, embeddings[0])
    candidates = aggregate_recall_hits(hits)
    return rerank_candidates(
        normalized_query,
        candidates,
        settings,
        top_n=top_n,
        client=rerank_client,
    )
