from pathlib import Path
from unittest.mock import Mock

import httpx
from sqlalchemy.dialects import postgresql

from app.core.config import Settings
from app.models import NationalEconomyCatalogVersion
from app.services.national_economy_catalog_chunks import (
    MAX_CHUNK_CHARACTERS,
    build_industry_chunks,
    embed_texts,
    full_resync_catalog,
)


def test_build_industry_chunks_preserves_types_and_character_limit() -> None:
    long_definition = "定" * (MAX_CHUNK_CHARACTERS + 1)
    rows = (("大类", "A01", "稻谷种植", "0111", long_definition, "包括内容", "不包括内容"),)

    chunks = build_industry_chunks(rows)

    assert [chunk.chunk_type for chunk in chunks] == [
        "definition",
        "definition",
        "include",
        "exclude",
    ]
    assert all(0 < len(chunk.text) <= MAX_CHUNK_CHARACTERS for chunk in chunks)
    assert chunks[0].source_row == 2
    assert chunks[0].industry_code == "0111"


def test_embed_texts_batches_requests_and_uses_configured_timeout() -> None:
    settings = Settings(
        SILICONFLOW_API_KEY="secret",
        SILICONFLOW_EMBEDDING_BATCH_SIZE=2,
        EMBEDDING_DIMENSION=3,
        SILICONFLOW_TIMEOUT_SECONDS=17,
        HTTP_CONNECT_TIMEOUT_SECONDS=4,
    )
    batch_sizes: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = __import__("json").loads(request.content)
        batch_sizes.append(len(payload["input"]))
        return httpx.Response(
            200,
            json={
                "data": [
                    {"index": index, "embedding": [float(index), 1.0, 2.0]}
                    for index in range(len(payload["input"]))
                ]
            },
        )

    with httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url=settings.siliconflow_base_url,
        timeout=httpx.Timeout(
            settings.siliconflow_timeout_seconds,
            connect=settings.http_connect_timeout_seconds,
        ),
    ) as client:
        embeddings = embed_texts(("a", "b", "c", "d", "e"), settings, client)

    assert batch_sizes == [2, 2, 1]
    assert len(embeddings) == 5


def test_full_resync_batches_embedding_and_builds_idempotent_upsert() -> None:
    settings = Settings(SILICONFLOW_EMBEDDING_BATCH_SIZE=2, EMBEDDING_DIMENSION=3)
    version = NationalEconomyCatalogVersion(
        id=7,
        version="version",
        source_hash="a" * 64,
        embedding_model="model",
        embedding_dimension=3,
    )
    rows = (
        ("大类", "A01", "稻谷种植", "0111", "定义", "包括", "不包括"),
        ("大类", "A01", "小麦种植", "0112", "定义二", None, None),
    )
    requested_batches: list[tuple[str, ...]] = []

    def embedding_request(texts):
        requested_batches.append(tuple(texts))
        return [[0.0, 1.0, 2.0] for _ in texts]

    session = Mock()
    full_resync_catalog(session, version, rows, settings, embedding_request)

    assert [len(batch) for batch in requested_batches] == [2, 2]
    statement = session.execute.call_args.args[0]
    sql = str(statement.compile(dialect=postgresql.dialect()))
    assert "ON CONFLICT ON CONSTRAINT uq_national_economy_industry_chunk_source DO UPDATE" in sql
    assert "embedding = excluded.embedding" in sql


def test_full_resync_does_not_create_large_index_files(tmp_path: Path) -> None:
    settings = Settings(SILICONFLOW_EMBEDDING_BATCH_SIZE=2, EMBEDDING_DIMENSION=3)
    version = NationalEconomyCatalogVersion(
        id=8,
        version="version",
        source_hash="b" * 64,
        embedding_model="model",
        embedding_dimension=3,
    )
    rows = (("大类", "A01", "稻谷种植", "0111", "定义", "包括", "不包括"),)

    full_resync_catalog(
        Mock(),
        version,
        rows,
        settings,
        lambda texts: [[0.0, 1.0, 2.0] for _ in texts],
    )

    assert list(tmp_path.rglob("*.md")) == []
    assert list(tmp_path.rglob("*.jsonl")) == []
