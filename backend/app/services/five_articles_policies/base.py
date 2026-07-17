from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.services.scenario_registry import ScenarioRegistration
from app.services.technology_finance_mapping_query import (
    FiveArticlesMappingLabel,
    FiveArticlesMappingLookupResult,
)


LEGACY_DECISION_POLICY_VERSION = "legacy-v1"


@dataclass(frozen=True)
class MappingResolution:
    mapping_result: FiveArticlesMappingLookupResult
    not_applicable_basis: str | None = None
    not_applicable_error_detail: str | None = None


@dataclass(frozen=True)
class FiveArticlesScenarioPolicy:
    scenario_id: str
    decision_policy_version: str = LEGACY_DECISION_POLICY_VERSION
    narrows_loan_labels: bool = True

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
        del session, input_payload, settings, condition_candidate_retriever
        del condition_label_selector
        return MappingResolution(
            mapping_result,
            not_applicable_error_detail=(
                mapping_result.detail
                if mapping_result.status == "not_applicable"
                else None
            ),
        )

    def build_not_applicable_basis(
        self,
        profile: ScenarioRegistration,
        resolution: MappingResolution,
    ) -> str:
        return resolution.not_applicable_basis or (
            f"贷款投向未命中已发布{profile.name}映射，"
            f"{profile.name}一致性判定不适用。"
        )

    def postprocess_labels(
        self,
        session: Session,
        input_payload: dict[str, object],
        labels: Sequence[Mapping[str, object]],
    ) -> list[dict[str, object]]:
        del session, input_payload
        return [dict(label) for label in labels]

    def missing_enterprise_instruction(self) -> str:
        return "企业侧未命中、"

    def enterprise_labels_required_for_consistency(self) -> bool:
        return True

    def override_missing_enterprise_consistency(
        self,
        profile: ScenarioRegistration,
        *,
        business_evidence_is_insufficient: bool,
        enterprise_labels: Sequence[FiveArticlesMappingLabel],
        status: str,
        basis: str,
    ) -> tuple[str, str] | None:
        del profile, business_evidence_is_insufficient, enterprise_labels
        del status, basis
        return None
