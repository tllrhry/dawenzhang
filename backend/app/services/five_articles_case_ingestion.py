from pathlib import Path

from sqlalchemy.orm import Session

from app.models import NationalEconomyClassificationCase
from app.services.national_economy_case_ingestion import (
    PENDING_STATUS,
    parse_template_fields,
)
from app.services.scenario_registry import ScenarioRegistration


def parse_five_articles_template(
    document_bytes: bytes,
    profile: ScenarioRegistration,
) -> dict[str, str]:
    """Parse a five-articles document against one explicit scenario schema."""
    return parse_template_fields(
        document_bytes,
        {field.key: field.label for field in profile.field_schema},
        {
            field.key: field.aliases
            for field in profile.field_schema
            if field.aliases
        },
    )


def create_five_articles_case_from_template(
    session: Session,
    document_bytes: bytes,
    original_filename: str,
    profile: ScenarioRegistration,
) -> NationalEconomyClassificationCase:
    input_payload = parse_five_articles_template(document_bytes, profile)
    case = NationalEconomyClassificationCase(
        scenario=profile.id,
        input_payload=input_payload,
        original_filename=Path(original_filename).name,
        status=PENDING_STATUS,
    )
    session.add(case)
    session.commit()
    session.refresh(case)
    return case
