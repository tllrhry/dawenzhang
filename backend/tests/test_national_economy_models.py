from pgvector.sqlalchemy import Vector
from sqlalchemy import inspect

from app.core.config import get_settings
from app.db.session import get_engine
from app.models import NationalEconomyCatalogVersion, NationalEconomyIndustryChunk


def test_model_metadata_contains_catalog_and_chunk_fields() -> None:
    version_columns = NationalEconomyCatalogVersion.__table__.columns
    assert {
        "id",
        "version",
        "source_hash",
        "embedding_model",
        "embedding_dimension",
        "created_at",
    } <= set(version_columns.keys())

    chunk_columns = NationalEconomyIndustryChunk.__table__.columns
    assert {
        "id",
        "catalog_version_id",
        "industry_code",
        "industry_name",
        "source_row",
        "text",
        "chunk_type",
        "embedding",
        "created_at",
    } <= set(chunk_columns.keys())
    assert isinstance(chunk_columns["embedding"].type, Vector)
    assert chunk_columns["embedding"].type.dim == get_settings().embedding_dimension


def test_migration_creates_tables_and_pgvector_column() -> None:
    inspector = inspect(get_engine())
    assert "national_economy_catalog_versions" in inspector.get_table_names()
    assert "national_economy_industry_chunks" in inspector.get_table_names()

    columns = {
        column["name"]: column
        for column in inspector.get_columns("national_economy_industry_chunks")
    }
    assert str(columns["embedding"]["type"]) == f"VECTOR({get_settings().embedding_dimension})"
