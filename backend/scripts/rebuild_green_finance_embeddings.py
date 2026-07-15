import argparse
from collections.abc import Sequence

from app.core.config import get_settings
from app.db.session import get_sessionmaker
from app.services.green_finance_mapping_maintenance import (
    inspect_green_finance_condition_index,
    rebuild_green_finance_condition_embeddings,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Inspect or fully rebuild the latest green-finance condition vectors."
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="overwrite every condition vector; without this flag only inspect",
    )
    args = parser.parse_args(argv)

    with get_sessionmaker()() as session:
        before = inspect_green_finance_condition_index(session)
        print(
            "before: "
            f"mapping_version={before.mapping_version} "
            f"mapping_version_id={before.mapping_version_id} "
            f"rows={before.total_rows} criteria={before.criteria_rows} "
            f"embeddings={before.embedding_rows} complete={before.complete}"
        )
        if not args.execute:
            print("dry-run only; pass --execute to rebuild all vectors")
            return 0 if before.complete else 1

        after = rebuild_green_finance_condition_embeddings(session, get_settings())
        if not after.complete:
            session.rollback()
            raise RuntimeError("rebuilt green-finance condition index is incomplete")
        session.commit()
        print(
            "rebuilt: "
            f"mapping_version={after.mapping_version} "
            f"mapping_version_id={after.mapping_version_id} "
            f"rows={after.total_rows} embeddings={after.embedding_rows}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
