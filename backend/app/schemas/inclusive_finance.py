from datetime import datetime
from pydantic import BaseModel, ConfigDict, field_validator
from app.schemas.national_economy import ClassificationResultResponse
from app.services.inclusive_finance_determination import BORROWER_TYPE_LABELS

class InclusiveFinanceResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int; version: int; status: str; stage_a_result_id: int
    borrower_type: str | None; computed_size: str | None; filled_size: str | None; size_consistent: bool | None
    is_operating_loan: bool | None; credit_amount_wan: float | None; qualifies: bool | None; inclusive_category: str | None; basis: str | None
    evidence_refs: list[dict[str, object]]; anomalies: list[dict[str, object]]; determination: dict[str, object] | None; error_detail: str | None; created_at: datetime

    @field_validator("borrower_type", mode="before")
    @classmethod
    def localize_borrower_type(cls, value: object) -> object:
        return BORROWER_TYPE_LABELS.get(value, value) if isinstance(value, str) else value

class InclusiveFinanceWorkflowResponse(BaseModel):
    stage_a: ClassificationResultResponse
    stage_b: InclusiveFinanceResultResponse | None

class InclusiveFinanceHistoryResponse(BaseModel):
    items: list[InclusiveFinanceResultResponse]
