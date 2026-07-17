from collections.abc import Callable
from dataclasses import replace
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.services.five_articles_policies.base import (
    FiveArticlesScenarioPolicy,
    MappingResolution,
)
from app.services.green_finance_condition_matching import (
    ConditionSide,
    build_green_finance_condition_evidence,
    condition_candidates_from_labels,
)
from app.services.scenario_registry import GREEN_FINANCE_SCENARIO
from app.services.technology_finance_mapping_query import (
    FiveArticlesMappingLabel,
    FiveArticlesMappingLookupResult,
)


GREEN_FINANCE_DECISION_POLICY_VERSION = "green-condition-v2"


class GreenFinancePolicy(FiveArticlesScenarioPolicy):
    def resolve_mapping(
        self,
        session: Session,
        input_payload: dict[str, object],
        mapping_result: FiveArticlesMappingLookupResult,
        settings: Settings,
        *,
        condition_candidate_retriever: Callable[..., Any],
        condition_label_selector: Callable[..., Any],
    ) -> MappingResolution:
        enterprise_labels = self._resolve_side(
            session,
            input_payload,
            "enterprise",
            mapping_result.enterprise_labels,
            settings,
            condition_candidate_retriever,
            condition_label_selector,
        )
        loan_labels = self._resolve_side(
            session,
            input_payload,
            "loan_direction",
            mapping_result.loan_direction_labels,
            settings,
            condition_candidate_retriever,
            condition_label_selector,
        )
        if not loan_labels:
            return MappingResolution(
                replace(
                    mapping_result,
                    status="not_applicable",
                    enterprise_labels=enterprise_labels,
                    loan_direction_labels=(),
                    detail="green_finance_condition_no_match",
                ),
                not_applicable_basis=(
                    "贷款投向的行业编码候选及全库条件/标准均未与案例业务证据形成可靠匹配，"
                    "绿色金融判定不适用。"
                ),
                not_applicable_error_detail="green_finance_condition_no_match",
            )
        return MappingResolution(
            replace(
                mapping_result,
                status="mapping_hit",
                enterprise_labels=enterprise_labels,
                loan_direction_labels=loan_labels,
                detail="green_finance_condition_validated_mapping_hit",
            )
        )

    @staticmethod
    def _resolve_side(
        session: Session,
        input_payload: dict[str, object],
        side: ConditionSide,
        explicit_labels: tuple[FiveArticlesMappingLabel, ...],
        settings: Settings,
        candidate_retriever: Callable[..., Any],
        label_selector: Callable[..., Any],
    ) -> tuple[FiveArticlesMappingLabel, ...]:
        evidence_text = build_green_finance_condition_evidence(input_payload, side)
        explicit_candidates = condition_candidates_from_labels(explicit_labels)
        if explicit_candidates:
            selected = label_selector(explicit_candidates, evidence_text, settings)
            if selected is not None:
                return (replace(selected, match_method="neic_code"),)

        candidates = candidate_retriever(session, input_payload, side, settings)
        if not candidates:
            return ()
        selected = label_selector(candidates, evidence_text, settings)
        if selected is None:
            return ()
        return (replace(selected, match_method="condition_fallback"),)


GREEN_FINANCE_POLICY = GreenFinancePolicy(
    scenario_id=GREEN_FINANCE_SCENARIO,
    decision_policy_version=GREEN_FINANCE_DECISION_POLICY_VERSION,
)

