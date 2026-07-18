"""Synchronize the technology-finance IP enterprise registry from its PDF source."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

import pdfplumber
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.session import get_sessionmaker
from app.models import TechnologyFinanceIpRegistryEntry, TechnologyFinanceIpRegistryVersion
from app.services.technology_finance_ip_registry import (
    HIGH_TECH_REGISTRY,
    SPECIALIZED_INNOVATION_REGISTRY,
    TechnologyFinanceRegistryType,
)


class TechnologyFinanceIpRegistryParseError(ValueError):
    """The source PDF does not contain a valid continuous registry."""


@dataclass(frozen=True)
class RegistryRow:
    source_row: int
    enterprise_name: str


@dataclass(frozen=True)
class RegistrySyncResult:
    version: TechnologyFinanceIpRegistryVersion
    reused: bool


def parse_technology_finance_ip_registry(source_path: Path) -> list[RegistryRow]:
    """Parse and validate all registry rows from *source_path*."""
    rows: list[RegistryRow] = []
    found_header = False
    with pdfplumber.open(source_path) as pdf:
        for page in pdf.pages:
            for table in page.extract_tables():
                for raw_row in table:
                    cells = [str(cell or "").strip() for cell in raw_row]
                    is_header = any(cell == "序号" for cell in cells) and any(
                        cell == "企业名称" for cell in cells
                    )
                    if not found_header:
                        if is_header:
                            found_header = True
                        continue
                    # Excel-generated PDFs repeat the table header on every
                    # page. It is metadata, not an invalid registry row.
                    if is_header:
                        continue
                    if not any(cells):
                        continue
                    if len(cells) < 2 or not cells[0].isdigit():
                        raise TechnologyFinanceIpRegistryParseError(
                            f"invalid registry row: {raw_row!r}"
                        )
                    enterprise_name = cells[1].strip()
                    if not enterprise_name:
                        raise TechnologyFinanceIpRegistryParseError(
                            f"enterprise name is blank at source row {cells[0]}"
                        )
                    rows.append(RegistryRow(int(cells[0]), enterprise_name))

    if not found_header:
        raise TechnologyFinanceIpRegistryParseError("registry table header not found")
    for expected, row in enumerate(rows, start=1):
        if row.source_row != expected:
            raise TechnologyFinanceIpRegistryParseError(
                f"registry source rows must be continuous: expected {expected}, got {row.source_row}"
            )
    if not rows:
        raise TechnologyFinanceIpRegistryParseError("registry contains no data rows")
    return rows


def synchronize_technology_finance_ip_registry(
    session: Session,
    source_path: Path,
    *,
    registry_type: TechnologyFinanceRegistryType = HIGH_TECH_REGISTRY,
    settings: Settings | None = None,
) -> RegistrySyncResult:
    """Validate and publish a source file; the caller owns the transaction/commit."""
    source_bytes = source_path.read_bytes()
    source_hash = sha256(source_bytes).hexdigest()
    latest = session.scalar(
        select(TechnologyFinanceIpRegistryVersion)
        .where(
            TechnologyFinanceIpRegistryVersion.status == "published",
            TechnologyFinanceIpRegistryVersion.registry_type == registry_type,
        )
        .order_by(TechnologyFinanceIpRegistryVersion.version.desc())
        .limit(1)
    )
    if latest is not None and latest.source_hash == source_hash:
        return RegistrySyncResult(version=latest, reused=True)

    rows = parse_technology_finance_ip_registry(source_path)
    next_version = (session.scalar(select(func.max(TechnologyFinanceIpRegistryVersion.version))) or 0) + 1
    version = TechnologyFinanceIpRegistryVersion(
        version=next_version,
        registry_type=registry_type,
        source_path=str(source_path),
        source_hash=source_hash,
        row_count=len(rows),
        status="published",
    )
    version.entries = [
        TechnologyFinanceIpRegistryEntry(
            enterprise_name=row.enterprise_name,
            source_row=row.source_row,
        )
        for row in rows
    ]
    session.add(version)
    session.flush()
    return RegistrySyncResult(version=version, reused=False)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-path", type=Path, default=None)
    parser.add_argument(
        "--registry-type",
        choices=(HIGH_TECH_REGISTRY, SPECIALIZED_INNOVATION_REGISTRY),
        default=None,
    )
    args = parser.parse_args(argv)
    settings = get_settings()
    default_paths = {
        HIGH_TECH_REGISTRY: settings.technology_finance_ip_registry_source_path,
        SPECIALIZED_INNOVATION_REGISTRY: (
            settings.technology_finance_specialized_innovation_registry_source_path
        ),
    }
    registry_types: tuple[TechnologyFinanceRegistryType, ...] = (
        (args.registry_type,)
        if args.registry_type is not None
        else (HIGH_TECH_REGISTRY,)
        if args.source_path is not None
        else (HIGH_TECH_REGISTRY, SPECIALIZED_INNOVATION_REGISTRY)
    )
    results: list[tuple[TechnologyFinanceRegistryType, RegistrySyncResult]] = []
    with get_sessionmaker()() as session:
        with session.begin():
            for registry_type in registry_types:
                result = synchronize_technology_finance_ip_registry(
                    session,
                    args.source_path or default_paths[registry_type],
                    registry_type=registry_type,
                    settings=settings,
                )
                results.append((registry_type, result))
    for registry_type, result in results:
        action = "reused" if result.reused else "published"
        print(
            "technology-finance registry "
            f"{registry_type} {action}: version={result.version.version} "
            f"rows={result.version.row_count}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
