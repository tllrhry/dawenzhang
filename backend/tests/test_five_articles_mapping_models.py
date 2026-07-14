from pathlib import Path
from uuid import uuid4

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import inspect
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.exc import IntegrityError

from app.db.session import get_engine, get_sessionmaker
from app.models import FiveArticlesMappingRow, FiveArticlesMappingVersion


ROOT_DIR = Path(__file__).resolve().parents[2]


def _version(
    *, scenario_id: str, source_hash: str, status: str = "draft"
) -> FiveArticlesMappingVersion:
    return FiveArticlesMappingVersion(
        scenario_id=scenario_id,
        version=1,
        source_hash=source_hash,
        status=status,
        validation_report={},
    )


def _row(
    *, mapping_version_id: int, scenario_id: str, code_level: int = 4
) -> FiveArticlesMappingRow:
    return FiveArticlesMappingRow(
        mapping_version_id=mapping_version_id,
        scenario_id=scenario_id,
        neic_code={2: "27", 3: "271", 4: "2710"}.get(code_level, "2710"),
        code_level=code_level,
        neic_name="化学药品原料药制造",
        subject="高技术产业（制造业）",
        tier1="医药制造业",
        tier2="化学药品制造",
        tier3=None,
        tier4=None,
        source_row=2,
    )


def test_mapping_model_metadata_contains_design_fields_and_constraints() -> None:
    version_columns = FiveArticlesMappingVersion.__table__.columns
    assert {
        "id",
        "scenario_id",
        "version",
        "source_hash",
        "status",
        "validation_report",
        "created_at",
    } == set(version_columns.keys())
    assert isinstance(version_columns["validation_report"].type, JSONB)

    row_columns = FiveArticlesMappingRow.__table__.columns
    assert {
        "id",
        "mapping_version_id",
        "scenario_id",
        "neic_code",
        "code_level",
        "neic_name",
        "subject",
        "tier1",
        "tier2",
        "tier3",
        "tier4",
        "source_row",
        "created_at",
    } == set(row_columns.keys())
    assert row_columns["tier1"].nullable is False
    for tier in ("tier2", "tier3", "tier4"):
        assert row_columns[tier].nullable is True

    foreign_key = next(iter(row_columns["mapping_version_id"].foreign_keys))
    assert foreign_key.target_fullname == "five_articles_mapping_versions.id"
    assert foreign_key.ondelete == "CASCADE"

    version_constraints = {
        constraint.name for constraint in FiveArticlesMappingVersion.__table__.constraints
    }
    assert "uq_five_articles_mapping_versions_scenario_source_hash" in version_constraints
    assert "ck_five_articles_mapping_versions_status" in version_constraints

    row_constraints = {
        constraint.name for constraint in FiveArticlesMappingRow.__table__.constraints
    }
    assert "ck_five_articles_mapping_rows_code_level" in row_constraints
    assert "ck_five_articles_mapping_rows_code_length" in row_constraints


def test_migration_creates_mapping_tables_constraints_indexes_and_fk() -> None:
    inspector = inspect(get_engine())
    table_names = inspector.get_table_names()
    assert "five_articles_mapping_versions" in table_names
    assert "five_articles_mapping_rows" in table_names

    unique_constraints = inspector.get_unique_constraints(
        "five_articles_mapping_versions"
    )
    assert any(
        constraint["name"]
        == "uq_five_articles_mapping_versions_scenario_source_hash"
        and constraint["column_names"] == ["scenario_id", "source_hash"]
        for constraint in unique_constraints
    )

    version_checks = {
        constraint["name"]
        for constraint in inspector.get_check_constraints(
            "five_articles_mapping_versions"
        )
    }
    assert "ck_five_articles_mapping_versions_status" in version_checks
    row_checks = {
        constraint["name"]
        for constraint in inspector.get_check_constraints("five_articles_mapping_rows")
    }
    assert "ck_five_articles_mapping_rows_code_level" in row_checks
    assert "ck_five_articles_mapping_rows_code_length" in row_checks

    version_indexes = {
        index["name"]: index["column_names"]
        for index in inspector.get_indexes("five_articles_mapping_versions")
    }
    assert version_indexes["ix_five_articles_mapping_versions_scenario_status"] == [
        "scenario_id",
        "status",
    ]
    row_indexes = {
        index["name"]: index["column_names"]
        for index in inspector.get_indexes("five_articles_mapping_rows")
    }
    assert row_indexes["ix_five_articles_mapping_rows_lookup"] == [
        "mapping_version_id",
        "scenario_id",
        "code_level",
        "neic_code",
    ]

    foreign_keys = inspector.get_foreign_keys("five_articles_mapping_rows")
    assert any(
        foreign_key["constrained_columns"] == ["mapping_version_id"]
        and foreign_key["referred_table"] == "five_articles_mapping_versions"
        and foreign_key["options"].get("ondelete") == "CASCADE"
        for foreign_key in foreign_keys
    )


def test_database_enforces_source_hash_status_code_level_and_foreign_key() -> None:
    session = get_sessionmaker()()
    scenario_id = f"technology_finance_{uuid4().hex}"
    source_hash = uuid4().hex * 2
    valid_version = _version(scenario_id=scenario_id, source_hash=source_hash)

    try:
        session.add(valid_version)
        session.commit()

        session.add(_version(scenario_id=scenario_id, source_hash=source_hash))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

        session.add(
            _version(
                scenario_id=scenario_id,
                source_hash=uuid4().hex * 2,
                status="retired",
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

        session.add(
            _row(
                mapping_version_id=valid_version.id,
                scenario_id=scenario_id,
                code_level=5,
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

        session.add(_row(mapping_version_id=-1, scenario_id=scenario_id))
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()

        valid_row = _row(
            mapping_version_id=valid_version.id,
            scenario_id=scenario_id,
        )
        session.add(valid_row)
        session.commit()
        row_id = valid_row.id

        session.delete(valid_version)
        session.commit()
        assert session.get(FiveArticlesMappingRow, row_id) is None
    finally:
        session.rollback()
        persisted_version = session.get(FiveArticlesMappingVersion, valid_version.id)
        if persisted_version is not None:
            session.delete(persisted_version)
            session.commit()
        session.close()


def test_mapping_migration_downgrade_and_upgrade_round_trip() -> None:
    config = Config(str(ROOT_DIR / "backend" / "alembic.ini"))
    try:
        command.downgrade(config, "0006_result_major_codes")
        downgraded_tables = inspect(get_engine()).get_table_names()
        assert "five_articles_mapping_rows" not in downgraded_tables
        assert "five_articles_mapping_versions" not in downgraded_tables
    finally:
        command.upgrade(config, "head")

    upgraded_tables = inspect(get_engine()).get_table_names()
    assert "five_articles_mapping_versions" in upgraded_tables
    assert "five_articles_mapping_rows" in upgraded_tables
