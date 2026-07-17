from dataclasses import dataclass
from typing import Literal, Protocol


TechnologyFinanceConsistencyStatus = Literal[
    "consistent", "inconsistent", "needs_review"
]
FiveArticlesResultStatus = Literal["completed", "not_applicable", "needs_review"]


class StageAResult(Protocol):
    id: int
    industry_code: str | None
    industry_major_code: str | None
    industry_name: str | None
    rationale: str | None
    loan_industry_code: str | None
    loan_industry_major_code: str | None
    loan_industry_name: str | None
    loan_matching_basis: str | None


class TechnologyFinanceStageBError(RuntimeError):
    """Raised when Stage B cannot produce a grounded constrained decision."""


@dataclass(frozen=True)
class TechnologyFinanceStageBResult:
    labels: tuple[dict[str, object], ...]
    consistency_status: TechnologyFinanceConsistencyStatus
    consistency_basis: str
    consistency_evidence_refs: tuple[dict[str, object], ...]
    model_output: dict[str, object]
    result_status: FiveArticlesResultStatus = "completed"
