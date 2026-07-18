"""Read-only lookup for the published technology-finance IP registry."""

import unicodedata
from dataclasses import dataclass
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import TechnologyFinanceIpRegistryEntry, TechnologyFinanceIpRegistryVersion


TechnologyFinanceRegistryType = Literal["high_tech", "specialized_innovation"]
HIGH_TECH_REGISTRY: TechnologyFinanceRegistryType = "high_tech"
SPECIALIZED_INNOVATION_REGISTRY: TechnologyFinanceRegistryType = (
    "specialized_innovation"
)


@dataclass(frozen=True)
class TechnologyFinanceIpRegistryMatch:
    matched: bool
    registry_type: TechnologyFinanceRegistryType = HIGH_TECH_REGISTRY
    source_row: int | None = None
    registry_version_id: int | None = None
    registry_available: bool = True


_INVISIBLE_NAME_CHARACTERS = frozenset(
    {"\u200b", "\u200c", "\u200d", "\u2060", "\ufeff"}
)


def _normalized_enterprise_name(value: str) -> str:
    return "".join(
        character
        for character in unicodedata.normalize("NFKC", value)
        if not character.isspace() and character not in _INVISIBLE_NAME_CHARACTERS
    )


def lookup_technology_finance_ip_registry_match(
    session: Session,
    enterprise_name: str | None,
    *,
    registry_type: TechnologyFinanceRegistryType = HIGH_TECH_REGISTRY,
) -> TechnologyFinanceIpRegistryMatch:
    """Match a name against the latest published version of one registry type."""
    normalized_name = enterprise_name.strip() if enterprise_name is not None else ""
    if not normalized_name:
        return TechnologyFinanceIpRegistryMatch(
            matched=False, registry_type=registry_type
        )

    latest_version_id = session.scalar(
        select(TechnologyFinanceIpRegistryVersion.id)
        .where(
            TechnologyFinanceIpRegistryVersion.status == "published",
            TechnologyFinanceIpRegistryVersion.registry_type == registry_type,
        )
        .order_by(
            TechnologyFinanceIpRegistryVersion.version.desc(),
            TechnologyFinanceIpRegistryVersion.published_at.desc(),
            TechnologyFinanceIpRegistryVersion.id.desc(),
        )
        .limit(1)
    )
    if latest_version_id is None:
        return TechnologyFinanceIpRegistryMatch(
            matched=False,
            registry_type=registry_type,
            registry_available=False,
        )
    source_row = session.scalar(
        select(TechnologyFinanceIpRegistryEntry.source_row).where(
            TechnologyFinanceIpRegistryEntry.version_id == latest_version_id,
            TechnologyFinanceIpRegistryEntry.enterprise_name == normalized_name,
        )
    )
    if source_row is not None:
        return TechnologyFinanceIpRegistryMatch(
            matched=True,
            registry_type=registry_type,
            source_row=source_row,
            registry_version_id=latest_version_id,
        )

    normalized_lookup_name = _normalized_enterprise_name(normalized_name)
    normalized_matches = [
        row.source_row
        for row in session.execute(
            select(
                TechnologyFinanceIpRegistryEntry.enterprise_name,
                TechnologyFinanceIpRegistryEntry.source_row,
            ).where(TechnologyFinanceIpRegistryEntry.version_id == latest_version_id)
        )
        if _normalized_enterprise_name(row.enterprise_name) == normalized_lookup_name
    ]
    if len(normalized_matches) == 1:
        return TechnologyFinanceIpRegistryMatch(
            matched=True,
            registry_type=registry_type,
            source_row=normalized_matches[0],
            registry_version_id=latest_version_id,
        )
    return TechnologyFinanceIpRegistryMatch(
        matched=False,
        registry_type=registry_type,
        registry_version_id=latest_version_id,
    )
