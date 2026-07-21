"""Synchronize the technology-finance IP enterprise registry from its PDF source."""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from pathlib import Path

# Kept as a module attribute for compatibility with tests and operational
# monkeypatches that replace pdfplumber.open on this CLI module.
import pdfplumber

from app.core.config import get_settings
from app.db.session import get_sessionmaker
from app.services.technology_finance_ip_registry import (
    HIGH_TECH_REGISTRY,
    SPECIALIZED_INNOVATION_REGISTRY,
    TechnologyFinanceRegistryType,
)
from app.services.technology_finance_ip_registry_sync import (
    RegistryRow,
    RegistrySyncResult,
    TechnologyFinanceIpRegistryParseError,
    parse_technology_finance_ip_registry,
    synchronize_technology_finance_ip_registry,
)


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
