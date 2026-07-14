from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
import re
import time
from typing import Any

import httpx
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import NationalEconomyCatalogVersion, NationalEconomyIndustryChunk


MAX_CHUNK_CHARACTERS = 1000
CHUNK_COLUMNS = (("definition", 7), ("include", 8), ("exclude", 9))
INDUSTRY_CODE_PATTERN = re.compile(r"(?:[A-Z])?(\d{2,4})")


@dataclass(frozen=True)
class IndustryChunk:
    category_name: str
    major_category_code: str
    major_category_name: str
    middle_category_code: str | None
    middle_category_name: str | None
    industry_code: str
    industry_name: str
    source_row: int
    text: str
    chunk_type: str


EmbeddingRequest = Callable[[Sequence[str]], Sequence[Sequence[float]]]


def split_bounded_text(text: str, max_characters: int = MAX_CHUNK_CHARACTERS) -> tuple[str, ...]:
    if max_characters <= 0:
        raise ValueError("max_characters must be greater than zero")
    normalized = "\n".join(line.strip() for line in text.splitlines() if line.strip())
    if not normalized:
        return ()
    return tuple(
        normalized[offset : offset + max_characters]
        for offset in range(0, len(normalized), max_characters)
    )


def build_industry_chunks(
    rows: Sequence[tuple[Any, ...]],
    max_characters: int = MAX_CHUNK_CHARACTERS,
) -> tuple[IndustryChunk, ...]:
    chunks: list[IndustryChunk] = []
    for source_row, row in enumerate(rows, start=2):
        category_name = _cell_text(row, 0)
        major_category_name = _cell_text(row, 1)
        major_category_code = _cell_text(row, 2)
        middle_category_name = _cell_text(row, 3) or None
        middle_category_code = _cell_text(row, 4) or None
        small_category_name = _cell_text(row, 5)
        raw_small_category_code = _cell_text(row, 6)
        raw_industry_code = raw_small_category_code or middle_category_code or major_category_code
        industry_name = small_category_name or middle_category_name or major_category_name
        if not industry_name or not raw_industry_code:
            continue
        if not category_name or not major_category_name or not major_category_code:
            raise ValueError(
                f"missing category or major category code or name at source row {source_row}"
            )
        if middle_category_name and not middle_category_code:
            raise ValueError(f"missing middle category code at source row {source_row}")
        if middle_category_code and not middle_category_name:
            raise ValueError(f"missing middle category name at source row {source_row}")
        industry_code = _normalize_industry_code(raw_industry_code, source_row)
        for chunk_type, column_index in CHUNK_COLUMNS:
            content = _cell_text(row, column_index)
            for text in split_bounded_text(content, max_characters):
                chunks.append(
                    IndustryChunk(
                        category_name=category_name,
                        major_category_code=major_category_code,
                        major_category_name=major_category_name,
                        middle_category_code=middle_category_code,
                        middle_category_name=middle_category_name,
                        industry_code=industry_code,
                        industry_name=industry_name,
                        source_row=source_row,
                        text=text,
                        chunk_type=chunk_type,
                    )
                )
    return tuple(chunks)


def embed_texts(
    texts: Sequence[str],
    settings: Settings,
    client: httpx.Client | None = None,
) -> tuple[tuple[float, ...], ...]:
    if not settings.siliconflow_api_key:
        raise RuntimeError("SILICONFLOW_API_KEY is required for catalog synchronization")
    owns_client = client is None
    http_client = client or httpx.Client(
        base_url=settings.siliconflow_base_url.rstrip("/"),
        timeout=httpx.Timeout(
            settings.siliconflow_timeout_seconds,
            connect=settings.http_connect_timeout_seconds,
        ),
    )
    try:
        embeddings: list[tuple[float, ...]] = []
        for batch in _batched(texts, settings.siliconflow_embedding_batch_size):
            for attempt in range(3):
                try:
                    response = http_client.post(
                        "/embeddings",
                        headers={"Authorization": f"Bearer {settings.siliconflow_api_key}"},
                        json={
                            "model": settings.siliconflow_embedding_model,
                            "input": list(batch),
                            "dimensions": settings.embedding_dimension,
                        },
                    )
                    break
                except (httpx.TimeoutException, httpx.NetworkError):
                    if attempt == 2:
                        raise
                    time.sleep(0.5 * (2**attempt))
            response.raise_for_status()
            data = sorted(response.json()["data"], key=lambda item: item["index"])
            if len(data) != len(batch):
                raise ValueError("embedding response count does not match request count")
            for item in data:
                vector = tuple(float(value) for value in item["embedding"])
                if len(vector) != settings.embedding_dimension:
                    raise ValueError("embedding response dimension does not match configuration")
                embeddings.append(vector)
        return tuple(embeddings)
    finally:
        if owns_client:
            http_client.close()


def full_resync_catalog(
    session: Session,
    version: NationalEconomyCatalogVersion,
    rows: Sequence[tuple[Any, ...]],
    settings: Settings,
    embedding_request: EmbeddingRequest | None = None,
) -> None:
    chunks = build_industry_chunks(rows)
    if not chunks:
        return
    shared_client = None
    if embedding_request is None:
        shared_client = httpx.Client(
            base_url=settings.siliconflow_base_url.rstrip("/"),
            timeout=httpx.Timeout(
                settings.siliconflow_timeout_seconds,
                connect=settings.http_connect_timeout_seconds,
            ),
        )
        request = lambda texts: embed_texts(texts, settings, shared_client)
    else:
        request = embedding_request
    embeddings: list[Sequence[float]] = []
    try:
        for batch in _batched(chunks, settings.siliconflow_embedding_batch_size):
            batch_embeddings = tuple(request([chunk.text for chunk in batch]))
            if len(batch_embeddings) != len(batch):
                raise ValueError("embedding response count does not match chunk count")
            embeddings.extend(batch_embeddings)
    finally:
        if shared_client is not None:
            shared_client.close()

    values = [
        {
            "catalog_version_id": version.id,
            "category_name": chunk.category_name,
            "major_category_code": chunk.major_category_code,
            "major_category_name": chunk.major_category_name,
            "middle_category_code": chunk.middle_category_code,
            "middle_category_name": chunk.middle_category_name,
            "industry_code": chunk.industry_code,
            "industry_name": chunk.industry_name,
            "source_row": chunk.source_row,
            "text": chunk.text,
            "chunk_type": chunk.chunk_type,
            "embedding": list(embedding),
        }
        for chunk, embedding in zip(chunks, embeddings, strict=True)
    ]
    statement = insert(NationalEconomyIndustryChunk).values(values)
    statement = statement.on_conflict_do_update(
        constraint="uq_national_economy_industry_chunk_source",
        set_={
            "major_category_code": statement.excluded.major_category_code,
            "major_category_name": statement.excluded.major_category_name,
            "middle_category_code": statement.excluded.middle_category_code,
            "middle_category_name": statement.excluded.middle_category_name,
            "category_name": statement.excluded.category_name,
            "industry_name": statement.excluded.industry_name,
            "embedding": statement.excluded.embedding,
        },
    )
    session.execute(statement)


def _cell_text(row: tuple[Any, ...], index: int) -> str:
    if index >= len(row) or row[index] is None:
        return ""
    return str(row[index]).strip()


def _normalize_industry_code(value: str, source_row: int) -> str:
    match = INDUSTRY_CODE_PATTERN.fullmatch(value)
    if match is None:
        raise ValueError(f"invalid 2/3/4-digit industry code at source row {source_row}: {value}")
    return match.group(1)


def _batched(values: Sequence[Any], batch_size: int) -> Iterable[Sequence[Any]]:
    if batch_size <= 0:
        raise ValueError("batch_size must be greater than zero")
    for offset in range(0, len(values), batch_size):
        yield values[offset : offset + batch_size]
