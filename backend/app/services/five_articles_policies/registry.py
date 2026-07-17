from types import MappingProxyType
from typing import Mapping

from app.services.five_articles_policies.base import FiveArticlesScenarioPolicy
from app.services.five_articles_policies.digital import DIGITAL_FINANCE_POLICY
from app.services.five_articles_policies.green import GREEN_FINANCE_POLICY
from app.services.five_articles_policies.pension import PENSION_FINANCE_POLICY
from app.services.five_articles_policies.technology import TECHNOLOGY_FINANCE_POLICY


FIVE_ARTICLES_POLICIES: Mapping[str, FiveArticlesScenarioPolicy] = MappingProxyType(
    {
        policy.scenario_id: policy
        for policy in (
            TECHNOLOGY_FINANCE_POLICY,
            GREEN_FINANCE_POLICY,
            DIGITAL_FINANCE_POLICY,
            PENSION_FINANCE_POLICY,
        )
    }
)


def get_five_articles_policy(scenario_id: str) -> FiveArticlesScenarioPolicy:
    try:
        return FIVE_ARTICLES_POLICIES[scenario_id]
    except KeyError as exc:
        raise LookupError(f"场景 {scenario_id} 未注册五篇大文章策略") from exc

