from collections.abc import Sequence
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_sessionmaker
from app.models import NationalEconomyCatalogVersion
from app.services.national_economy_catalog_sync import read_catalog_source, synchronize_catalog


def full_resync_skeleton(
    session: Session,
    version: NationalEconomyCatalogVersion,
    rows: Sequence[tuple[Any, ...]],
) -> None:
    del session, version, rows


def main() -> int:
    settings = get_settings()
    if settings.national_economy_catalog_path is None:
        raise RuntimeError("NATIONAL_ECONOMY_CATALOG_PATH is required")

    source = read_catalog_source(settings.national_economy_catalog_path)
    with get_sessionmaker()() as session:
        result = synchronize_catalog(
            session=session,
            source=source,
            embedding_model=settings.siliconflow_embedding_model,
            embedding_dimension=settings.embedding_dimension,
            full_resync=full_resync_skeleton,
        )
        if result.created:
            session.commit()
            print(f"catalog version created: {result.version.version}")
        else:
            print(f"catalog version already exists: {result.version.version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
