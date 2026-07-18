from sqlalchemy import func, select

from app.db.session import get_sessionmaker
from app.models import TechnologyFinanceIpRegistryEntry, TechnologyFinanceIpRegistryVersion
from app.services.technology_finance_ip_registry import (
    HIGH_TECH_REGISTRY,
    SPECIALIZED_INNOVATION_REGISTRY,
    lookup_technology_finance_ip_registry_match,
)


def _next_version(session) -> int:
    return (session.scalar(select(func.max(TechnologyFinanceIpRegistryVersion.version))) or 0) + 1


def _published_version(
    session,
    version: int,
    *entries: tuple[str, int],
    registry_type: str = HIGH_TECH_REGISTRY,
) -> None:
    registry_version = TechnologyFinanceIpRegistryVersion(
        version=version,
        registry_type=registry_type,
        source_path=f"registry-{version}.pdf",
        source_hash=f"{version:064x}",
        row_count=len(entries),
        status="published",
    )
    registry_version.entries = [
        TechnologyFinanceIpRegistryEntry(enterprise_name=name, source_row=source_row)
        for name, source_row in entries
    ]
    session.add(registry_version)
    session.flush()


def test_lookup_matches_trimmed_name_only_in_latest_published_version() -> None:
    session = get_sessionmaker()()
    try:
        first_version = _next_version(session)
        _published_version(session, first_version, ("历史企业", 8), ("最新企业", 9))
        _published_version(session, first_version + 1, ("最新企业", 17))
        session.commit()

        matched = lookup_technology_finance_ip_registry_match(session, "  最新企业  ")
        historical_only = lookup_technology_finance_ip_registry_match(session, "历史企业")
        missing = lookup_technology_finance_ip_registry_match(session, "不存在企业")

        assert matched.matched is True
        assert matched.source_row == 17
        assert historical_only.matched is False
        assert historical_only.source_row is None
        assert missing.matched is False
        assert missing.source_row is None
    finally:
        session.close()


def test_lookup_empty_name_short_circuits_without_database_query() -> None:
    class NoQuerySession:
        def scalar(self, _statement):
            raise AssertionError("empty enterprise names must not query the database")

    session = NoQuerySession()

    assert lookup_technology_finance_ip_registry_match(session, None).matched is False
    assert lookup_technology_finance_ip_registry_match(session, "   ").matched is False


def test_lookup_normalizes_invisible_name_characters_in_latest_version() -> None:
    session = get_sessionmaker()()
    try:
        version = _next_version(session)
        _published_version(
            session,
            version,
            ("江苏超盛汽车零部件有限公司", 11),
        )
        session.commit()

        matched = lookup_technology_finance_ip_registry_match(
            session, "江苏超盛\u200b汽车零部件有限公司"
        )

        assert matched.matched is True
        assert matched.source_row == 11
    finally:
        session.close()


def test_lookup_rejects_ambiguous_normalized_registry_names() -> None:
    session = get_sessionmaker()()
    try:
        version = _next_version(session)
        _published_version(
            session,
            version,
            ("江苏超盛 汽车零部件有限公司", 11),
            ("江苏超盛汽车零部件有限公司", 12),
        )
        session.commit()

        matched = lookup_technology_finance_ip_registry_match(
            session, "江苏超盛\u200b汽车零部件有限公司"
        )

        assert matched.matched is False
        assert matched.source_row is None
    finally:
        session.close()


def test_lookup_keeps_high_tech_and_specialized_innovation_versions_independent() -> None:
    session = get_sessionmaker()()
    try:
        version = _next_version(session)
        _published_version(
            session,
            version,
            ("仅高新企业", 10),
            registry_type=HIGH_TECH_REGISTRY,
        )
        _published_version(
            session,
            version + 1,
            ("仅专精特新企业", 20),
            registry_type=SPECIALIZED_INNOVATION_REGISTRY,
        )
        session.commit()

        high_tech = lookup_technology_finance_ip_registry_match(
            session,
            "仅高新企业",
            registry_type=HIGH_TECH_REGISTRY,
        )
        high_tech_in_specialized = lookup_technology_finance_ip_registry_match(
            session,
            "仅高新企业",
            registry_type=SPECIALIZED_INNOVATION_REGISTRY,
        )
        specialized = lookup_technology_finance_ip_registry_match(
            session,
            "仅专精特新企业",
            registry_type=SPECIALIZED_INNOVATION_REGISTRY,
        )

        assert high_tech.matched is True
        assert high_tech.source_row == 10
        assert high_tech_in_specialized.matched is False
        assert high_tech_in_specialized.registry_available is True
        assert specialized.matched is True
        assert specialized.source_row == 20
    finally:
        session.close()
