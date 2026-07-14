from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from sqlalchemy.orm import Session

from app.models import NationalEconomyClassificationCase
from app.schemas.national_economy import (
    CaseInputField,
    CaseResponse,
    ClassificationResultResponse,
)
from app.services.five_articles_case_ingestion import (
    create_five_articles_case_from_template,
)
from app.services.national_economy_classification_workflow import (
    get_current_completed_result,
)
from app.services.scenario_registry import ScenarioRegistration


@dataclass(frozen=True)
class ScenarioCaseHandler:
    """Create and present cases for one registered workflow family."""

    def create_case(
        self,
        session: Session,
        document_bytes: bytes,
        original_filename: str,
        profile: ScenarioRegistration,
    ) -> NationalEconomyClassificationCase:
        return create_five_articles_case_from_template(
            session,
            document_bytes,
            original_filename,
            profile,
        )

    def case_response(
        self,
        case: NationalEconomyClassificationCase,
        profile: ScenarioRegistration,
    ) -> CaseResponse:
        current_result = get_current_completed_result(case)
        return CaseResponse(
            id=case.id,
            scenario=case.scenario,
            status=case.status,
            original_filename=case.original_filename,
            input_fields=[
                CaseInputField(
                    field=field.key,
                    label=field.label,
                    value=case.input_payload.get(field.key, ""),
                )
                for field in profile.field_schema
            ],
            current_result=(
                ClassificationResultResponse.model_validate(current_result)
                if current_result is not None
                else None
            ),
            created_at=case.created_at,
            updated_at=case.updated_at,
        )


FIVE_ARTICLES_CASE_HANDLER = ScenarioCaseHandler()

SCENARIO_CASE_HANDLERS: Mapping[str, ScenarioCaseHandler] = MappingProxyType(
    {
        "technology_finance_two_stage": FIVE_ARTICLES_CASE_HANDLER,
        "inclusive_finance_single_stage": FIVE_ARTICLES_CASE_HANDLER,
        "agriculture_related_single_stage": FIVE_ARTICLES_CASE_HANDLER,
    }
)


def get_scenario_case_handler(
    profile: ScenarioRegistration,
) -> ScenarioCaseHandler:
    if profile.workflow is None:
        raise LookupError(f"场景 {profile.id} 未注册案例处理器")
    try:
        return SCENARIO_CASE_HANDLERS[profile.workflow]
    except KeyError as exc:
        raise LookupError(f"场景 {profile.id} 未注册案例处理器") from exc
