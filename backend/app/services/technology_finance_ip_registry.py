"""Read-only lookup for the published technology-finance IP registry."""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import TechnologyFinanceIpRegistryEntry, TechnologyFinanceIpRegistryVersion


@dataclass(frozen=True)
class TechnologyFinanceIpRegistryMatch:
    matched: bool
    source_row: int | None = None


def lookup_technology_finance_ip_registry_match(
    session: Session, enterprise_name: str | None
) -> TechnologyFinanceIpRegistryMatch:
    """Match a trimmed enterprise name against only the latest published registry."""
    normalized_name = enterprise_name.strip() if enterprise_name is not None else ""
    if not normalized_name:
        return TechnologyFinanceIpRegistryMatch(matched=False)

    latest_version_id = (
        select(TechnologyFinanceIpRegistryVersion.id)
        .where(TechnologyFinanceIpRegistryVersion.status == "published")
        .order_by(
            TechnologyFinanceIpRegistryVersion.version.desc(),
            TechnologyFinanceIpRegistryVersion.published_at.desc(),
            TechnologyFinanceIpRegistryVersion.id.desc(),
        )
        .limit(1)
        .scalar_subquery()
    )
    source_row = session.scalar(
        select(TechnologyFinanceIpRegistryEntry.source_row).where(
            TechnologyFinanceIpRegistryEntry.version_id == latest_version_id,
            TechnologyFinanceIpRegistryEntry.enterprise_name == normalized_name,
        )
    )
    if source_row is None:
        return TechnologyFinanceIpRegistryMatch(matched=False)
    return TechnologyFinanceIpRegistryMatch(matched=True, source_row=source_row)
