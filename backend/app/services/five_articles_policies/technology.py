from collections.abc import Mapping, Sequence

from sqlalchemy.orm import Session

from app.services.five_articles_policies.base import FiveArticlesScenarioPolicy
from app.services.scenario_registry import TECHNOLOGY_FINANCE_SCENARIO
from app.services.technology_finance_ip_registry import (
    lookup_technology_finance_ip_registry_match,
)


_IP_INTENSIVE_INDUSTRY_SUBJECTS = frozenset(
    {"知识产权（专利）密集型产业", "知识产权(专利)密集型产业"}
)


class TechnologyFinancePolicy(FiveArticlesScenarioPolicy):
    def postprocess_labels(
        self,
        session: Session,
        input_payload: dict[str, object],
        labels: Sequence[Mapping[str, object]],
    ) -> list[dict[str, object]]:
        enterprise_name = input_payload.get("enterprise_name")
        display_name = (
            enterprise_name.strip() if isinstance(enterprise_name, str) else ""
        )
        display_name = display_name or "（未填写）"
        result_labels: list[dict[str, object]] = []
        for label in labels:
            result_label = dict(label)
            if result_label.get("subject") in _IP_INTENSIVE_INDUSTRY_SUBJECTS:
                match = lookup_technology_finance_ip_registry_match(
                    session,
                    enterprise_name if isinstance(enterprise_name, str) else None,
                )
                if match.matched:
                    result_label["ip_intensive_industry_status"] = "satisfied"
                    result_label["ip_intensive_industry_basis"] = (
                        f"企业名称『{display_name}』能在江苏省高新技术企业备案名单中匹配到"
                        f"（来源序号 {match.source_row}），知识产权（专利）密集型产业条件满足。"
                    )
                else:
                    result_label["ip_intensive_industry_status"] = "unsatisfied"
                    result_label["ip_intensive_industry_basis"] = (
                        f"企业名称『{display_name}』未能在江苏省高新技术企业备案名单中匹配到，"
                        "知识产权（专利）密集型产业条件不满足。"
                    )
            result_labels.append(result_label)
        return result_labels


TECHNOLOGY_FINANCE_POLICY = TechnologyFinancePolicy(
    scenario_id=TECHNOLOGY_FINANCE_SCENARIO,
    narrows_loan_labels=False,
)

