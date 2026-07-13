from app.core.config import get_settings
from app.db.session import get_sessionmaker
from app.services.technology_finance_mapping_sync import (
    read_mapping_source,
    synchronize_technology_finance_mapping,
)


def main() -> int:
    settings = get_settings()
    source = read_mapping_source(settings.technology_finance_mapping_path)
    with get_sessionmaker()() as session:
        result = synchronize_technology_finance_mapping(session, source, settings)
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
