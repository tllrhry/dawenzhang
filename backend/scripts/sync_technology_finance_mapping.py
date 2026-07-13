from app.core.config import get_settings
from app.db.session import get_sessionmaker
from app.services.technology_finance_mapping_sync import (
    synchronize_scenario_mapping,
)
from app.services.scenario_registry import TECHNOLOGY_FINANCE_REGISTRATION


def main() -> int:
    settings = get_settings()
    with get_sessionmaker()() as session:
        result = synchronize_scenario_mapping(
            session, TECHNOLOGY_FINANCE_REGISTRATION, settings
        )
        session.commit()

    version = result.version
    action = "reused" if result.reused else "created"
    print(
        f"technology-finance mapping version {action}: "
        f"version={version.version} status={version.status}"
    )
    return 0 if version.status == "published" else 1


if __name__ == "__main__":
    raise SystemExit(main())
