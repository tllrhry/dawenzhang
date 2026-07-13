import argparse
from collections.abc import Sequence

from app.core.config import get_settings
from app.db.session import get_sessionmaker
from app.services.scenario_registry import SCENARIO_REGISTRY
from app.services.technology_finance_mapping_sync import synchronize_scenario_mapping


def main(argv: Sequence[str] | None = None) -> int:
    profiles = {
        scenario_id: profile
        for scenario_id, profile in SCENARIO_REGISTRY.items()
        if profile.is_executable_profile
    }
    parser = argparse.ArgumentParser()
    parser.add_argument("scenario_id", choices=sorted(profiles))
    args = parser.parse_args(argv)

    settings = get_settings()
    profile = profiles[args.scenario_id]
    with get_sessionmaker()() as session:
        result = synchronize_scenario_mapping(session, profile, settings)
        session.commit()

    version = result.version
    action = "reused" if result.reused else "created"
    print(
        f"{profile.id} mapping version {action}: "
        f"version={version.version} status={version.status}"
    )
    return 0 if version.status == "published" else 1


if __name__ == "__main__":
    raise SystemExit(main())
