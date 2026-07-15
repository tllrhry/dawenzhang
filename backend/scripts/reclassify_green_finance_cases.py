import argparse
from collections.abc import Sequence

from app.core.config import get_settings
from app.db.session import get_sessionmaker
from app.services.green_finance_batch_reclassification import (
    list_stale_green_finance_cases,
    reclassify_stale_green_finance_cases,
)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Recompute stale green-finance Stage B results using the latest "
            "mapping and decision policy while reusing Stage A."
        )
    )
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--after-case-id", type=int, default=0)
    parser.add_argument("--limit", type=int)
    args = parser.parse_args(argv)

    with get_sessionmaker()() as session:
        if not args.execute:
            candidates = list_stale_green_finance_cases(
                session, after_case_id=args.after_case_id, limit=args.limit
            )
            ids = [candidate.case.id for candidate in candidates]
            print(f"dry-run: selected={len(ids)} case_ids={ids[:50]}")
            if len(ids) > 50:
                print(f"... {len(ids) - 50} more cases omitted")
            print("pass --execute to run Stage B for these cases")
            return 0

        summary = reclassify_stale_green_finance_cases(
            session,
            get_settings(),
            after_case_id=args.after_case_id,
            limit=args.limit,
        )
        print(
            "finished: "
            f"selected={summary.selected} completed={summary.completed} "
            f"not_applicable={summary.not_applicable} "
            f"needs_review={summary.needs_review} "
            f"classification_failed={summary.classification_failed} "
            f"last_case_id={summary.last_case_id}"
        )
        return 1 if summary.classification_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
