from collections.abc import Sequence

from app.services.five_articles_policies.base import FiveArticlesScenarioPolicy
from app.services.scenario_registry import (
    PENSION_FINANCE_SCENARIO,
    ScenarioRegistration,
)
from app.services.technology_finance_mapping_query import FiveArticlesMappingLabel


class PensionFinancePolicy(FiveArticlesScenarioPolicy):
    def missing_enterprise_instruction(self) -> str:
        return (
            "企业侧未命中但贷款投向侧已命中时，应结合明确的贷款用途判为 "
            "inconsistent；"
        )

    def enterprise_labels_required_for_consistency(self) -> bool:
        return False

    def override_missing_enterprise_consistency(
        self,
        profile: ScenarioRegistration,
        *,
        business_evidence_is_insufficient: bool,
        enterprise_labels: Sequence[FiveArticlesMappingLabel],
        status: str,
        basis: str,
    ) -> tuple[str, str] | None:
        del status, basis
        if enterprise_labels or business_evidence_is_insufficient:
            return None
        return (
            "inconsistent",
            f"企业侧未命中已发布{profile.name}映射，贷款投向侧已命中{profile.name}标签，"
            "且贷款用途与投向依据明确，判定为不一致。",
        )


PENSION_FINANCE_POLICY = PensionFinancePolicy(
    scenario_id=PENSION_FINANCE_SCENARIO,
)

