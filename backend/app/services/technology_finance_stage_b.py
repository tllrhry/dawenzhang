import json
import time
from collections.abc import Mapping, Sequence

import httpx

from app.core.config import Settings
from app.services.five_articles_stage_b_evidence import (
    build_business_sources as _build_business_sources,
)
from app.services.five_articles_stage_b_prompt import (
    build_stage_b_request_payload as _build_stage_b_request_payload,
)
from app.services.five_articles_stage_b_types import (
    StageAResult,
    TechnologyFinanceConsistencyStatus,
    TechnologyFinanceStageBError,
    TechnologyFinanceStageBResult,
)
from app.services.five_articles_stage_b_validation import (
    has_same_neic_code_match as _has_same_neic_code_match,
    serialize_stage_a_result as _serialize_stage_a_result,
    validate_deterministic_labels as _validate_deterministic_labels,
    validate_stage_b_model_response as _validate_stage_b_model_response,
)
from app.services.scenario_registry import (
    ScenarioRegistration,
    TECHNOLOGY_FINANCE_REGISTRATION,
)
from app.services.technology_finance_mapping_query import FiveArticlesMappingLabel


def classify_technology_finance_stage_b(
    input_payload: Mapping[str, object],
    stage_a_result: StageAResult,
    enterprise_labels: Sequence[FiveArticlesMappingLabel],
    loan_direction_labels: Sequence[FiveArticlesMappingLabel],
    settings: Settings,
    client: httpx.Client | None = None,
) -> TechnologyFinanceStageBResult:
    """Compatibility wrapper for the technology-finance Stage B profile."""
    return classify_five_articles_stage_b(
        TECHNOLOGY_FINANCE_REGISTRATION,
        input_payload,
        stage_a_result,
        enterprise_labels,
        loan_direction_labels,
        settings,
        client=client,
    )


def classify_five_articles_stage_b(
    profile: ScenarioRegistration,
    input_payload: Mapping[str, object],
    stage_a_result: StageAResult,
    enterprise_labels: Sequence[FiveArticlesMappingLabel],
    loan_direction_labels: Sequence[FiveArticlesMappingLabel],
    settings: Settings,
    client: httpx.Client | None = None,
) -> TechnologyFinanceStageBResult:
    """Generate a grounded Stage B decision using one scenario profile only."""
    if not profile.is_executable_profile:
        raise TechnologyFinanceStageBError(f"场景 {profile.id} 不具备 Stage B 配置")
    enterprise_snapshot = tuple(enterprise_labels)
    loan_snapshot = tuple(loan_direction_labels)
    stage_a_snapshot = _serialize_stage_a_result(stage_a_result)
    _validate_deterministic_labels(
        enterprise_snapshot,
        loan_snapshot,
        stage_a_snapshot,
        profile,
    )
    business_sources = _build_business_sources(input_payload, stage_a_snapshot, profile)
    same_code = _has_same_neic_code_match(
        stage_a_snapshot, enterprise_snapshot, loan_snapshot
    )
    request_payload = _build_stage_b_request_payload(
        input_payload,
        stage_a_snapshot,
        enterprise_snapshot,
        loan_snapshot,
        settings.deepseek_model,
        profile,
        same_code=same_code,
    )

    if not settings.deepseek_api_key:
        raise TechnologyFinanceStageBError(
            f"DEEPSEEK_API_KEY is required for {profile.name} Stage B"
        )

    owns_client = client is None
    http_client = client or httpx.Client(
        base_url=settings.deepseek_base_url.rstrip("/"),
        timeout=httpx.Timeout(
            settings.deepseek_timeout_seconds,
            connect=settings.http_connect_timeout_seconds,
        ),
    )
    try:
        for attempt in range(3):
            try:
                response = http_client.post(
                    "/chat/completions",
                    headers={"Authorization": f"Bearer {settings.deepseek_api_key}"},
                    json=request_payload,
                )
                break
            except (httpx.TimeoutException, httpx.NetworkError):
                if attempt == 2:
                    raise
                time.sleep(0.5 * (2**attempt))
        response.raise_for_status()
        return _validate_stage_b_model_response(
            response.json(),
            stage_a_snapshot,
            enterprise_snapshot,
            loan_snapshot,
            business_sources,
            profile,
            same_code=same_code,
        )
    except TechnologyFinanceStageBError:
        raise
    except (httpx.HTTPError, json.JSONDecodeError, TypeError, ValueError, KeyError) as exc:
        raise TechnologyFinanceStageBError(
            f"DeepSeek {profile.name} Stage B failed: {exc}"
        ) from exc
    finally:
        if owns_client:
            http_client.close()
