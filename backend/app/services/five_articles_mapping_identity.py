from typing import TypeAlias


MappingCandidateIdentity: TypeAlias = tuple[
    str,
    str,
    str,
    str,
    str | None,
    str | None,
    str | None,
    str | None,
]


def build_mapping_candidate_identity(
    *,
    neic_code: str,
    neic_name: str,
    subject: str,
    tier1: str,
    tier2: str | None,
    tier3: str | None,
    tier4: str | None,
    condition_criteria: str | None,
) -> MappingCandidateIdentity:
    """Identify one normalized mapping candidate across sync and query boundaries."""
    return (
        neic_code,
        neic_name,
        subject,
        tier1,
        tier2,
        tier3,
        tier4,
        condition_criteria,
    )
