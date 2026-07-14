import importlib.util
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from app.db.session import get_engine, get_sessionmaker
from app.models import (
    AgricultureRelatedResult,
    NationalEconomyClassificationCase,
    NationalEconomyClassificationResult,
)


ROOT_DIR = Path(__file__).resolve().parents[2]
MIGRATION_PATH = ROOT_DIR / "backend/alembic/versions/0012_agriculture_related_results.py"


def _case_and_stage_a() -> tuple[NationalEconomyClassificationCase, NationalEconomyClassificationResult]:
    case = NationalEconomyClassificationCase(
        scenario="agriculture_related",
        input_payload={"enterprise_name": "涉农模型测试企业"},
        status="completed",
    )
    stage_a = NationalEconomyClassificationResult(
        case=case,
        version=1,
        status="completed",
        candidate_snapshot=[],
        model_output={"stage": "a"},
    )
    return case, stage_a


def _result(
    case: NationalEconomyClassificationCase,
    stage_a: NationalEconomyClassificationResult,
    *,
    version: int,
    status: str = "completed",
    stage_a_result_id: int | None = None,
) -> AgricultureRelatedResult:
    return AgricultureRelatedResult(
        case_id=case.id,
        scenario_id=case.scenario,
        version=version,
        status=status,
        stage_a_result_id=stage_a_result_id or stage_a.id,
        is_agriculture_related=True if status == "completed" else None,
        matched_categories=[],
        evidence_refs=[],
    )


def test_model_declares_fields_fks_constraints_and_partial_unique_index() -> None:
    table = AgricultureRelatedResult.__table__
    assert {
        "id", "case_id", "scenario_id", "version", "status", "stage_a_result_id",
        "is_agriculture_related", "matched_categories", "basis", "evidence_refs",
        "model_output", "error_detail", "created_at",
    } == set(table.columns.keys())
    assert {foreign_key.target_fullname for foreign_key in table.foreign_keys} == {
        "national_economy_classification_cases.id",
        "national_economy_classification_results.id",
    }
    assert {
        constraint.name for constraint in table.constraints if constraint.name is not None
    } >= {
        "uq_agriculture_related_results_case_version",
        "ck_agriculture_related_results_status",
    }
    partial_index = next(
        index for index in table.indexes
        if index.name == "uq_agriculture_related_results_case_stage_a_completed"
    )
    assert partial_index.unique
    assert tuple(column.name for column in partial_index.columns) == (
        "case_id", "stage_a_result_id"
    )
    assert str(partial_index.dialect_options["postgresql"]["where"]) == "status = 'completed'"


def test_migration_has_one_head_and_creates_integrity_objects() -> None:
    inspector = inspect(get_engine())
    assert "agriculture_related_results" in inspector.get_table_names()
    assert {column["name"] for column in inspector.get_columns("agriculture_related_results")} == {
        "id", "case_id", "scenario_id", "version", "status", "stage_a_result_id",
        "is_agriculture_related", "matched_categories", "basis", "evidence_refs",
        "model_output", "error_detail", "created_at",
    }
    assert any(
        constraint["name"] == "uq_agriculture_related_results_case_version"
        and constraint["column_names"] == ["case_id", "version"]
        for constraint in inspector.get_unique_constraints("agriculture_related_results")
    )
    assert any(
        index["name"] == "uq_agriculture_related_results_case_stage_a_completed"
        and index["unique"]
        for index in inspector.get_indexes("agriculture_related_results")
    )
    assert len(inspector.get_foreign_keys("agriculture_related_results")) == 2


def test_database_rejects_duplicate_case_version_and_invalid_status() -> None:
    session = get_sessionmaker()()
    case, stage_a = _case_and_stage_a()
    session.add(case)
    session.commit()
    session.refresh(stage_a)
    session.add(_result(case, stage_a, version=1))
    session.commit()
    session.add(_result(case, stage_a, version=1, status="needs_review"))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()
    session.add(_result(case, stage_a, version=2, status="invalid"))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()
    session.delete(case)
    session.commit()
    session.close()


def test_partial_unique_index_only_rejects_completed_duplicates() -> None:
    session = get_sessionmaker()()
    case, stage_a = _case_and_stage_a()
    session.add(case)
    session.commit()
    session.refresh(stage_a)
    session.add(_result(case, stage_a, version=1, status="needs_review"))
    session.add(_result(case, stage_a, version=2, status="classification_failed"))
    session.commit()
    session.add(_result(case, stage_a, version=3, status="completed"))
    session.commit()
    session.add(_result(case, stage_a, version=4, status="completed"))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()
    session.delete(case)
    session.commit()
    session.close()


@pytest.mark.parametrize("column", ["case_id", "stage_a_result_id"])
def test_database_rejects_missing_foreign_keys(column: str) -> None:
    session = get_sessionmaker()()
    case, stage_a = _case_and_stage_a()
    session.add(case)
    session.commit()
    session.refresh(stage_a)
    values = {
        "case_id": case.id,
        "scenario_id": "agriculture_related",
        "version": 1,
        "status": "completed",
        "stage_a_result_id": stage_a.id,
        "matched_categories": [],
        "evidence_refs": [],
    }
    values[column] = 999999999
    session.add(AgricultureRelatedResult(**values))
    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()
    session.delete(case)
    session.commit()
    session.close()


def test_migration_downgrade_upgrade_round_trip_is_repeatable() -> None:
    config = Config(str(ROOT_DIR / "backend/alembic.ini"))
    command.downgrade(config, "0012_five_middle")
    command.upgrade(config, "head")
    command.upgrade(config, "head")
    assert "agriculture_related_results" in inspect(get_engine()).get_table_names()

    spec = importlib.util.spec_from_file_location("agriculture_migration", MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    assert migration.revision == "0012_agriculture_related_results"
    assert migration.down_revision == "0012_five_middle"
