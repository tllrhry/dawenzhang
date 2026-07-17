import pytest

from app.services.five_articles_policies import get_five_articles_policy
from app.services.five_articles_policies.digital import (
    DIGITAL_FINANCE_DECISION_POLICY_VERSION,
    DIGITAL_FINANCE_POLICY,
)
from app.services.five_articles_policies.green import (
    GREEN_FINANCE_DECISION_POLICY_VERSION,
    GREEN_FINANCE_POLICY,
)
from app.services.five_articles_policies.pension import PENSION_FINANCE_POLICY
from app.services.five_articles_policies.pension import (
    PENSION_FINANCE_DECISION_POLICY_VERSION,
)
from app.services.five_articles_policies.technology import (
    TECHNOLOGY_FINANCE_POLICY,
)
from app.services.scenario_registry import (
    DIGITAL_FINANCE_REGISTRATION,
    GREEN_FINANCE_REGISTRATION,
    PENSION_FINANCE_REGISTRATION,
    TECHNOLOGY_FINANCE_REGISTRATION,
)


@pytest.mark.parametrize(
    ("registration", "expected_policy"),
    [
        (TECHNOLOGY_FINANCE_REGISTRATION, TECHNOLOGY_FINANCE_POLICY),
        (GREEN_FINANCE_REGISTRATION, GREEN_FINANCE_POLICY),
        (DIGITAL_FINANCE_REGISTRATION, DIGITAL_FINANCE_POLICY),
        (PENSION_FINANCE_REGISTRATION, PENSION_FINANCE_POLICY),
    ],
)
def test_registered_profiles_resolve_independent_policies(
    registration: object,
    expected_policy: object,
) -> None:
    assert get_five_articles_policy(registration.id) is expected_policy


def test_policy_metadata_owns_scenario_behavior_flags() -> None:
    assert TECHNOLOGY_FINANCE_POLICY.narrows_loan_labels is False
    assert GREEN_FINANCE_POLICY.narrows_loan_labels is True
    assert DIGITAL_FINANCE_POLICY.narrows_loan_labels is True
    assert PENSION_FINANCE_POLICY.narrows_loan_labels is True
    assert (
        GREEN_FINANCE_POLICY.decision_policy_version
        == GREEN_FINANCE_DECISION_POLICY_VERSION
    )
    assert (
        DIGITAL_FINANCE_POLICY.decision_policy_version
        == DIGITAL_FINANCE_DECISION_POLICY_VERSION
    )
    assert (
        PENSION_FINANCE_POLICY.decision_policy_version
        == PENSION_FINANCE_DECISION_POLICY_VERSION
    )


def test_unknown_scenario_has_no_implicit_policy() -> None:
    with pytest.raises(LookupError, match="未注册五篇大文章策略"):
        get_five_articles_policy("unknown")
