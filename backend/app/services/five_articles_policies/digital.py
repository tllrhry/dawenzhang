from app.services.five_articles_policies.base import FiveArticlesScenarioPolicy
from app.services.scenario_registry import DIGITAL_FINANCE_SCENARIO


DIGITAL_FINANCE_POLICY = FiveArticlesScenarioPolicy(
    scenario_id=DIGITAL_FINANCE_SCENARIO,
)

