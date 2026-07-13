from pathlib import Path

from sqlalchemy.orm import Session

from app.models import NationalEconomyClassificationCase
from app.services.national_economy_case_ingestion import (
    PENDING_STATUS,
    parse_template_fields,
)
from app.services.scenario_registry import TECHNOLOGY_FINANCE_REGISTRATION


def parse_technology_finance_template(document_bytes: bytes) -> dict[str, str]:
    registration = TECHNOLOGY_FINANCE_REGISTRATION
    return parse_template_fields(
        document_bytes,
        {field.key: field.label for field in registration.field_schema},
        {
            field.key: field.aliases
            for field in registration.field_schema
            if field.aliases
        },
    )


def create_technology_finance_case_from_template(
    session: Session,
    document_bytes: bytes,
    original_filename: str,
) -> NationalEconomyClassificationCase:
    input_payload = parse_technology_finance_template(document_bytes)
    case = NationalEconomyClassificationCase(
        scenario=TECHNOLOGY_FINANCE_REGISTRATION.id,
        input_payload=input_payload,
        original_filename=Path(original_filename).name,
        status=PENDING_STATUS,
    )
    session.add(case)
    session.commit()
    session.refresh(case)
    return case
