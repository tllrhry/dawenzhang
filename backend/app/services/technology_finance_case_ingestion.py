from sqlalchemy.orm import Session

from app.models import NationalEconomyClassificationCase
from app.services.five_articles_case_ingestion import (
    create_five_articles_case_from_template,
    parse_five_articles_template,
)
from app.services.scenario_registry import TECHNOLOGY_FINANCE_REGISTRATION


def parse_technology_finance_template(document_bytes: bytes) -> dict[str, str]:
    return parse_five_articles_template(
        document_bytes,
        TECHNOLOGY_FINANCE_REGISTRATION,
    )


def create_technology_finance_case_from_template(
    session: Session,
    document_bytes: bytes,
    original_filename: str,
) -> NationalEconomyClassificationCase:
    return create_five_articles_case_from_template(
        session,
        document_bytes,
        original_filename,
        TECHNOLOGY_FINANCE_REGISTRATION,
    )
