import importlib.util
from pathlib import Path

from app.models import InclusiveFinanceResult


ROOT_DIR = Path(__file__).resolve().parents[2]
MIGRATION_PATH = (
    ROOT_DIR / "backend/alembic/versions/0010_inclusive_finance_results.py"
)


def test_inclusive_finance_result_metadata_has_isolated_integrity_constraints() -> None:
    table = InclusiveFinanceResult.__table__

    assert table.name == "inclusive_finance_results"
    assert {foreign_key.target_fullname for foreign_key in table.foreign_keys} == {
        "national_economy_classification_cases.id",
        "national_economy_classification_results.id",
    }
    assert all(foreign_key.ondelete == "CASCADE" for foreign_key in table.foreign_keys)
    assert {
        constraint.name
        for constraint in table.constraints
        if constraint.name is not None
    } >= {
        "uq_inclusive_finance_results_case_version",
        "ck_inclusive_finance_results_status",
        "ck_inclusive_finance_results_borrower_type",
        "ck_inclusive_finance_results_computed_size",
    }

    completed_index = next(
        index
        for index in table.indexes
        if index.name == "uq_inclusive_finance_results_case_stage_a_completed"
    )
    assert completed_index.unique is True
    assert tuple(column.name for column in completed_index.columns) == (
        "case_id",
        "stage_a_result_id",
    )
    assert str(completed_index.dialect_options["postgresql"]["where"]) == (
        "status = 'completed'"
    )


def test_inclusive_finance_migration_follows_integrity_migration() -> None:
    spec = importlib.util.spec_from_file_location(
        "inclusive_finance_migration", MIGRATION_PATH
    )
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)

    assert migration.revision == "0010_inclusive_finance_results"
    assert migration.down_revision == "0009_five_articles_integrity"
    source = MIGRATION_PATH.read_text(encoding="utf-8")
    assert "inclusive_finance_results" in source
    assert "uq_inclusive_finance_results_case_stage_a_completed" in source
