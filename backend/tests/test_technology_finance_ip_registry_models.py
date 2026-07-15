import importlib.util
from pathlib import Path

from alembic import command
from alembic.config import Config
import pytest
from sqlalchemy import func, inspect, select
from sqlalchemy.exc import IntegrityError

from app.core.config import Settings
from app.db.session import get_engine, get_sessionmaker
from app.models import (
    TechnologyFinanceIpRegistryEntry,
    TechnologyFinanceIpRegistryVersion,
)
from scripts import sync_technology_finance_ip_registry as registry_sync


ROOT_DIR = Path(__file__).resolve().parents[2]
MIGRATION_PATH = ROOT_DIR / (
    "backend/alembic/versions/0014_technology_finance_ip_registry.py"
)
SOURCE_PDF = ROOT_DIR / "模板文件/江苏省高新技术企业备案公示名单.pdf"


def _fake_pdf(monkeypatch: pytest.MonkeyPatch, rows: list[list[str]]) -> None:
    class FakePage:
        def extract_tables(self) -> list[list[list[str]]]:
            return [rows]

    class FakePdf:
        pages = [FakePage()]

        def __enter__(self) -> "FakePdf":
            return self

        def __exit__(self, *_args: object) -> None:
            return None

    monkeypatch.setattr(registry_sync.pdfplumber, "open", lambda _path: FakePdf())


def _table(*names: str | None, numbers: list[str] | None = None) -> list[list[str]]:
    numbers = numbers or [str(index) for index in range(1, len(names) + 1)]
    return [["序号", "企业名称"], *[[number, name or ""] for number, name in zip(numbers, names)]]


def _sync(session, source_path: Path) -> registry_sync.RegistrySyncResult:
    with session.begin():
        return registry_sync.synchronize_technology_finance_ip_registry(
            session, source_path
        )


def test_registry_model_declares_fields_fk_and_unique_constraint() -> None:
    version_columns = TechnologyFinanceIpRegistryVersion.__table__.columns
    assert {
        "id", "version", "source_path", "source_hash", "row_count", "status", "published_at"
    } == set(version_columns.keys())
    entry_columns = TechnologyFinanceIpRegistryEntry.__table__.columns
    assert {"id", "version_id", "enterprise_name", "source_row"} == set(entry_columns.keys())
    assert {
        constraint.name
        for constraint in TechnologyFinanceIpRegistryEntry.__table__.constraints
    } >= {"uq_technology_finance_ip_registry_entries_version_name"}


def test_registry_source_path_has_default_and_environment_alias() -> None:
    assert Settings(_env_file=None).technology_finance_ip_registry_source_path == Path(
        "模板文件/江苏省高新技术企业备案公示名单.pdf"
    )
    assert Settings(
        _env_file=None,
        TECHNOLOGY_FINANCE_IP_REGISTRY_SOURCE_PATH="/mnt/assets/ip-registry.pdf",
    ).technology_finance_ip_registry_source_path == Path("/mnt/assets/ip-registry.pdf")


def test_registry_migration_creates_tables_fk_and_unique_constraint() -> None:
    inspector = inspect(get_engine())
    assert {
        "technology_finance_ip_registry_versions",
        "technology_finance_ip_registry_entries",
    } <= set(inspector.get_table_names())
    assert any(
        constraint["name"] == "uq_technology_finance_ip_registry_versions_version"
        for constraint in inspector.get_unique_constraints(
            "technology_finance_ip_registry_versions"
        )
    )
    assert any(
        constraint["name"] == "uq_technology_finance_ip_registry_entries_version_name"
        and constraint["column_names"] == ["version_id", "enterprise_name"]
        for constraint in inspector.get_unique_constraints(
            "technology_finance_ip_registry_entries"
        )
    )
    foreign_keys = inspector.get_foreign_keys("technology_finance_ip_registry_entries")
    assert any(
        foreign_key["referred_table"] == "technology_finance_ip_registry_versions"
        and foreign_key["options"].get("ondelete") == "CASCADE"
        for foreign_key in foreign_keys
    )


def test_registry_database_rejects_duplicate_enterprise_name_per_version() -> None:
    session = get_sessionmaker()()
    try:
        version = TechnologyFinanceIpRegistryVersion(
            version=900000,
            source_path="test.pdf",
            source_hash="a" * 64,
            row_count=2,
            status="published",
        )
        version.entries = [
            TechnologyFinanceIpRegistryEntry(enterprise_name="重复企业", source_row=1),
            TechnologyFinanceIpRegistryEntry(enterprise_name="重复企业", source_row=2),
        ]
        session.add(version)
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()
    finally:
        session.close()


def test_registry_migration_downgrade_upgrade_round_trip_is_repeatable() -> None:
    config = Config(str(ROOT_DIR / "backend/alembic.ini"))
    command.downgrade(config, "0013_green_condition_mapping")
    command.upgrade(config, "head")
    command.upgrade(config, "head")

    assert {
        "technology_finance_ip_registry_versions",
        "technology_finance_ip_registry_entries",
    } <= set(inspect(get_engine()).get_table_names())
    spec = importlib.util.spec_from_file_location("technology_finance_ip_migration", MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    assert migration.revision == "0014_tech_finance_ip_registry"
    assert migration.down_revision == "0013_green_condition_mapping"


def test_real_registry_pdf_has_571_continuous_rows() -> None:
    rows = registry_sync.parse_technology_finance_ip_registry(SOURCE_PDF)
    assert len(rows) == 571
    assert [row.source_row for row in rows] == list(range(1, 572))
    assert all(row.enterprise_name == row.enterprise_name.strip() for row in rows)
    assert all(row.enterprise_name for row in rows)


@pytest.mark.parametrize(
    ("names", "numbers"),
    [
        (("企业一", "企业二"), ["1", "3"]),
        (("企业一", "企业二"), ["1", "1"]),
        (("企业一", None), ["1", "2"]),
    ],
    ids=["sequence-gap", "duplicate-sequence", "blank-name"],
)
def test_invalid_registry_rows_reject_without_partial_publication(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    names: tuple[str | None, ...],
    numbers: list[str],
) -> None:
    source_path = tmp_path / "registry.pdf"
    source_path.write_bytes(b"valid-source")
    _fake_pdf(monkeypatch, _table("企业一"))
    session = get_sessionmaker()()
    try:
        original = _sync(session, source_path)
        source_path.write_bytes(b"invalid-source")
        _fake_pdf(monkeypatch, _table(*names, numbers=numbers))
        with pytest.raises(registry_sync.TechnologyFinanceIpRegistryParseError):
            _sync(session, source_path)
        published = session.scalars(
            select(TechnologyFinanceIpRegistryVersion).order_by(
                TechnologyFinanceIpRegistryVersion.version
            )
        ).all()
        assert len(published) == 1
        assert published[0].id == original.version.id
        assert published[0].source_hash == original.version.source_hash
    finally:
        session.close()


def test_same_source_is_idempotent_and_changed_source_publishes_new_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_path = tmp_path / "registry.pdf"
    source_path.write_bytes(b"source-one")
    _fake_pdf(monkeypatch, _table("企业一"))
    session = get_sessionmaker()()
    try:
        count_before = session.scalar(
            select(func.count(TechnologyFinanceIpRegistryVersion.id))
        )
        session.commit()
        first = _sync(session, source_path)
        second = _sync(session, source_path)
        assert not first.reused
        assert second.reused
        assert second.version.id == first.version.id
        assert session.scalar(
            select(func.count(TechnologyFinanceIpRegistryVersion.id))
        ) == count_before + 1
        session.commit()

        source_path.write_bytes(b"source-two")
        _fake_pdf(monkeypatch, _table("企业一", "企业二"))
        changed = _sync(session, source_path)
        assert not changed.reused
        assert changed.version.id != first.version.id
        assert changed.version.source_hash != first.version.source_hash
        assert changed.version.row_count == 2
    finally:
        session.close()
