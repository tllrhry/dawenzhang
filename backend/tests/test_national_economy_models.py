from pgvector.sqlalchemy import Vector
from sqlalchemy import inspect
from sqlalchemy.dialects.postgresql import JSONB

from app.core.config import get_settings
from app.db.session import get_engine, get_sessionmaker
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
        "major_category_code",
        "major_category_name",
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
    assert columns["major_category_code"]["nullable"]
    assert columns["major_category_name"]["nullable"]


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
        "loan_industry_code",
        "loan_industry_name",
        "loan_matching_basis",
        "loan_matches_enterprise",
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
    assert result_columns["loan_industry_code"].nullable
    assert result_columns["loan_industry_name"].nullable
    assert result_columns["loan_matching_basis"].nullable
    assert result_columns["loan_matches_enterprise"].nullable
    assert next(iter(result_columns["case_id"].foreign_keys)).target_fullname == (
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
    for column_name in (
        "loan_industry_code",
        "loan_industry_name",
        "loan_matching_basis",
        "loan_matches_enterprise",
    ):
        assert column_name in result_columns
        assert result_columns[column_name]["nullable"]
    assert str(result_columns["loan_industry_code"]["type"]) == "VARCHAR(4)"
    assert str(result_columns["loan_industry_name"]["type"]) == "VARCHAR(255)"
    assert str(result_columns["loan_matching_basis"]["type"]) == "TEXT"
    assert str(result_columns["loan_matches_enterprise"]["type"]) == "BOOLEAN"
    foreign_keys = inspector.get_foreign_keys("national_economy_classification_results")
    assert any(
        foreign_key["constrained_columns"] == ["case_id"]
        and foreign_key["referred_table"] == "national_economy_classification_cases"
        for foreign_key in foreign_keys
    )


def test_pre_loan_direction_result_remains_readable_without_overwriting_enterprise_fields() -> None:
    session = get_sessionmaker()()
    case = NationalEconomyClassificationCase(
        scenario="pre-loan-direction-result",
        input_payload={"enterprise_name": "旧结果测试企业"},
        original_filename=None,
        status="completed",
    )
    result = NationalEconomyClassificationResult(
        case=case,
        version=1,
        status="completed",
        industry_code="3742",
        industry_name="航天器及运载火箭制造",
        confidence=91,
        rationale="旧版本企业匹配依据",
        ai_summary="旧版本结论",
        candidate_snapshot=[],
        objection=None,
        model_output={"legacy": True},
    )

    try:
        session.add(result)
        session.commit()
        result_id = result.id
        session.expire_all()

        loaded = session.get(NationalEconomyClassificationResult, result_id)
        assert loaded is not None
        assert loaded.industry_code == "3742"
        assert loaded.industry_name == "航天器及运载火箭制造"
        assert loaded.rationale == "旧版本企业匹配依据"
        assert loaded.loan_industry_code is None
        assert loaded.loan_industry_name is None
        assert loaded.loan_matching_basis is None
        assert loaded.loan_matches_enterprise is None
    finally:
        session.rollback()
        persisted_case = session.get(NationalEconomyClassificationCase, case.id)
        if persisted_case is not None:
            session.delete(persisted_case)
            session.commit()
        session.close()
