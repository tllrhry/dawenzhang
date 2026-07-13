from dataclasses import dataclass
from typing import Callable
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.models import FiveArticlesResult, InclusiveFinanceResult, NationalEconomyClassificationCase
from app.services.scenario_registry import ScenarioRegistration
from app.services.technology_finance_classification_workflow import classify_technology_finance_case, reclassify_technology_finance_case
from app.services.inclusive_finance_workflow import classify_inclusive_finance_case, reclassify_inclusive_finance_case

@dataclass(frozen=True)
class ScenarioWorkflowHandler:
    classify: Callable
    reclassify: Callable
    result_model: type
    def history(self, session: Session, case: NationalEconomyClassificationCase):
        return session.scalars(select(self.result_model).where(self.result_model.case_id == case.id).order_by(self.result_model.version, self.result_model.id)).all()

SCENARIO_WORKFLOW_HANDLERS = {
    "technology_finance_two_stage": ScenarioWorkflowHandler(classify_technology_finance_case, reclassify_technology_finance_case, FiveArticlesResult),
    "inclusive_finance_single_stage": ScenarioWorkflowHandler(classify_inclusive_finance_case, reclassify_inclusive_finance_case, InclusiveFinanceResult),
}
def get_scenario_workflow_handler(profile: ScenarioRegistration) -> ScenarioWorkflowHandler:
    if profile.workflow not in SCENARIO_WORKFLOW_HANDLERS: raise LookupError(f"场景 {profile.id} 未注册工作流处理器")
    return SCENARIO_WORKFLOW_HANDLERS[profile.workflow]
