from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import FiveArticlesResult, NationalEconomyClassificationCase
from app.services.national_economy_case_export import export_case_workbook
from app.services.scenario_registry import ScenarioRegistration
from app.services.technology_finance_classification_workflow import (
    TechnologyFinanceWorkflowResult,
    classify_five_articles_case,
    reclassify_five_articles_case,
)


@dataclass(frozen=True)
class ScenarioWorkflowHandler:
    """Run and present the registered five-articles workflow family."""

    def classify(
        self,
        session: Session,
        case: NationalEconomyClassificationCase,
        profile: ScenarioRegistration,
    ) -> TechnologyFinanceWorkflowResult:
        self._validate_case_profile(case, profile)
        return classify_five_articles_case(session, case, profile)

    def reclassify(
        self,
        session: Session,
        case: NationalEconomyClassificationCase,
        objection_text: str,
        profile: ScenarioRegistration,
    ) -> TechnologyFinanceWorkflowResult:
        self._validate_case_profile(case, profile)
        return reclassify_five_articles_case(
            session,
            case,
            objection_text,
            profile,
        )

    def history(
        self,
        session: Session,
        case: NationalEconomyClassificationCase,
        profile: ScenarioRegistration,
    ) -> list[FiveArticlesResult]:
        self._validate_case_profile(case, profile)
        return list(
            session.scalars(
                select(FiveArticlesResult)
                .where(
                    FiveArticlesResult.case_id == case.id,
                    FiveArticlesResult.scenario_id == profile.id,
                )
                .order_by(FiveArticlesResult.version, FiveArticlesResult.id)
            ).all()
        )

    def export(
        self,
        session: Session,
        case: NationalEconomyClassificationCase,
        profile: ScenarioRegistration,
    ) -> bytes:
        return export_case_workbook(
            case,
            five_articles_results=self.history(session, case, profile),
            profile=profile,
        )

    @staticmethod
    def _validate_case_profile(
        case: NationalEconomyClassificationCase,
        profile: ScenarioRegistration,
    ) -> None:
        if case.scenario != profile.id:
            raise ValueError("案例与场景 profile 不一致")


FIVE_ARTICLES_WORKFLOW_HANDLER = ScenarioWorkflowHandler()

SCENARIO_WORKFLOW_HANDLERS: Mapping[str, ScenarioWorkflowHandler] = MappingProxyType(
    {
        "technology_finance_two_stage": FIVE_ARTICLES_WORKFLOW_HANDLER,
    }
)


def get_scenario_workflow_handler(
    profile: ScenarioRegistration,
) -> ScenarioWorkflowHandler:
    if profile.workflow is None:
        raise LookupError(f"场景 {profile.id} 未注册工作流处理器")
    try:
        return SCENARIO_WORKFLOW_HANDLERS[profile.workflow]
    except KeyError as exc:
        raise LookupError(f"场景 {profile.id} 未注册工作流处理器") from exc
