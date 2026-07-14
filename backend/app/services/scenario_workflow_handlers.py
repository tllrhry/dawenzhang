from dataclasses import dataclass
from types import MappingProxyType
from typing import Callable, Mapping

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AgricultureRelatedResult,
    FiveArticlesResult,
    InclusiveFinanceResult,
    NationalEconomyClassificationCase,
)
from app.services.agriculture_related_workflow import (
    AgricultureRelatedWorkflowResult,
    classify_agriculture_related_case,
    reclassify_agriculture_related_case,
)
from app.services.inclusive_finance_workflow import (
    InclusiveFinanceWorkflowResult,
    classify_inclusive_finance_case,
    reclassify_inclusive_finance_case,
)
from app.services.national_economy_case_export import export_case_workbook
from app.services.scenario_registry import ScenarioRegistration
from app.services.technology_finance_classification_workflow import (
    TechnologyFinanceWorkflowResult,
    classify_five_articles_case,
    reclassify_five_articles_case,
)


@dataclass(frozen=True)
class ScenarioWorkflowHandler:
    """Run and present a registered five-articles workflow family."""

    classify_callable: Callable | None = None
    reclassify_callable: Callable | None = None
    result_model: type[FiveArticlesResult] | type[InclusiveFinanceResult] | type[AgricultureRelatedResult] | None = None

    def classify(
        self,
        session: Session,
        case: NationalEconomyClassificationCase,
        profile: ScenarioRegistration,
    ) -> TechnologyFinanceWorkflowResult | InclusiveFinanceWorkflowResult | AgricultureRelatedWorkflowResult:
        self._validate_case_profile(case, profile)
        if self.classify_callable is not None:
            return self.classify_callable(session, case)
        if profile.workflow == "inclusive_finance_single_stage":
            return classify_inclusive_finance_case(session, case)
        if profile.workflow == "agriculture_related_single_stage":
            return classify_agriculture_related_case(session, case)
        return classify_five_articles_case(session, case, profile)

    def reclassify(
        self,
        session: Session,
        case: NationalEconomyClassificationCase,
        objection_text: str,
        profile: ScenarioRegistration,
    ) -> TechnologyFinanceWorkflowResult | InclusiveFinanceWorkflowResult | AgricultureRelatedWorkflowResult:
        self._validate_case_profile(case, profile)
        if self.reclassify_callable is not None:
            return self.reclassify_callable(session, case, objection_text)
        if profile.workflow == "inclusive_finance_single_stage":
            return reclassify_inclusive_finance_case(session, case, objection_text)
        if profile.workflow == "agriculture_related_single_stage":
            return reclassify_agriculture_related_case(session, case, objection_text)
        return reclassify_five_articles_case(session, case, objection_text, profile)

    def history(
        self,
        session: Session,
        case: NationalEconomyClassificationCase,
        profile: ScenarioRegistration,
    ) -> list[FiveArticlesResult] | list[InclusiveFinanceResult] | list[AgricultureRelatedResult]:
        self._validate_case_profile(case, profile)
        result_model = self.result_model or (
            InclusiveFinanceResult
            if profile.workflow == "inclusive_finance_single_stage"
            else AgricultureRelatedResult
            if profile.workflow == "agriculture_related_single_stage"
            else FiveArticlesResult
        )
        return list(
            session.scalars(
                select(result_model)
                .where(
                    result_model.case_id == case.id,
                    result_model.scenario_id == profile.id,
                )
                .order_by(result_model.version, result_model.id)
            ).all()
        )

    def export(
        self,
        session: Session,
        case: NationalEconomyClassificationCase,
        profile: ScenarioRegistration,
    ) -> bytes:
        results = self.history(session, case, profile)
        if profile.workflow == "inclusive_finance_single_stage":
            return export_case_workbook(
                case,
                inclusive_finance_results=results,
                profile=profile,
            )
        if profile.workflow == "agriculture_related_single_stage":
            return export_case_workbook(
                case,
                profile=profile,
            )
        return export_case_workbook(
            case,
            five_articles_results=results,
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
INCLUSIVE_FINANCE_WORKFLOW_HANDLER = ScenarioWorkflowHandler(
    classify_inclusive_finance_case,
    reclassify_inclusive_finance_case,
    InclusiveFinanceResult,
)
AGRICULTURE_RELATED_WORKFLOW_HANDLER = ScenarioWorkflowHandler(
    classify_agriculture_related_case,
    reclassify_agriculture_related_case,
    AgricultureRelatedResult,
)

SCENARIO_WORKFLOW_HANDLERS: Mapping[str, ScenarioWorkflowHandler] = MappingProxyType(
    {
        "technology_finance_two_stage": FIVE_ARTICLES_WORKFLOW_HANDLER,
        "inclusive_finance_single_stage": INCLUSIVE_FINANCE_WORKFLOW_HANDLER,
        "agriculture_related_single_stage": AGRICULTURE_RELATED_WORKFLOW_HANDLER,
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
