from pgvector.sqlalchemy import Vector
from sqlalchemy import inspect
from sqlalchemy.dialects.postgresql import JSONB

from app.core.config import get_settings
from app.db.session import get_engine
from app.models import (
    NationalEconomyCatalogVersion,
    NationalEconomyClassificationCase,
    NationalEconomyClassificationResult,
    NationalEconomyIndustryChunk,
)


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


def test_model_metadata_contains_case_and_result_history_fields() -> None:
    case_columns = NationalEconomyClassificationCase.__table__.columns
    assert {
        "id",
        "scenario",
        "input_payload",
        "original_filename",
        "status",
        "created_at",
        "updated_at",
    } <= set(case_columns.keys())
    assert isinstance(case_columns["input_payload"].type, JSONB)
    assert not case_columns["status"].nullable

    result_columns = NationalEconomyClassificationResult.__table__.columns
    assert {
        "id",
        "case_id",
        "version",
        "status",
        "industry_code",
        "industry_name",
        "confidence",
        "rationale",
        "ai_summary",
        "candidate_snapshot",
        "objection",
        "model_output",
        "created_at",
    } <= set(result_columns.keys())
    assert isinstance(result_columns["candidate_snapshot"].type, JSONB)
    assert isinstance(result_columns["objection"].type, JSONB)
    assert isinstance(result_columns["model_output"].type, JSONB)
    assert not result_columns["status"].nullable
    assert result_columns["case_id"].foreign_keys.pop().target_fullname == (
        "national_economy_classification_cases.id"
    )


def test_migration_creates_case_and_result_history_tables() -> None:
    inspector = inspect(get_engine())
    table_names = inspector.get_table_names()
    assert "national_economy_classification_cases" in table_names
    assert "national_economy_classification_results" in table_names

    case_columns = {
        column["name"]: column
        for column in inspector.get_columns("national_economy_classification_cases")
    }
    assert str(case_columns["input_payload"]["type"]) == "JSONB"
    assert not case_columns["status"]["nullable"]

    result_columns = {
        column["name"]: column
        for column in inspector.get_columns("national_economy_classification_results")
    }
    assert str(result_columns["candidate_snapshot"]["type"]) == "JSONB"
    assert str(result_columns["objection"]["type"]) == "JSONB"
    assert str(result_columns["model_output"]["type"]) == "JSONB"
    assert not result_columns["status"]["nullable"]
    foreign_keys = inspector.get_foreign_keys("national_economy_classification_results")
    assert any(
        foreign_key["constrained_columns"] == ["case_id"]
        and foreign_key["referred_table"] == "national_economy_classification_cases"
        for foreign_key in foreign_keys
    )
