import argparse
from collections.abc import Sequence

from app.core.config import get_settings
from app.db.session import get_sessionmaker
from app.services.national_economy_catalog_chunks import full_resync_catalog
from app.services.national_economy_catalog_sync import read_catalog_source, synchronize_catalog


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--force",
        action="store_true",
        help="re-embed and upsert the current catalog version",
    )
    args = parser.parse_args(argv)
    settings = get_settings()
    if settings.national_economy_catalog_path is None:
        raise RuntimeError("NATIONAL_ECONOMY_CATALOG_PATH is required")

    source = read_catalog_source(settings.national_economy_catalog_path)
    with get_sessionmaker()() as session:
        def full_resync(session, version, rows) -> None:
            full_resync_catalog(session, version, rows, settings)

        result = synchronize_catalog(
            session=session,
            source=source,
            embedding_model=settings.siliconflow_embedding_model,
            embedding_dimension=settings.embedding_dimension,
            full_resync=full_resync,
            force_resync=args.force,
        )
        if result.created:
            session.commit()
            print(f"catalog version created: {result.version.version}")
        elif result.resynchronized:
            session.commit()
            print(f"catalog version resynchronized: {result.version.version}")
        else:
            print(f"catalog version already exists: {result.version.version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
