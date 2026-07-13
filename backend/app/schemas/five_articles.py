from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.schemas.national_economy import ClassificationResultResponse


class FiveArticlesResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    version: int
    status: str
    stage_a_result_id: int
    mapping_version_id: int | None
    labels: list[dict[str, object]]
    loan_neic_code: str | None
    loan_neic_name: str | None
    enterprise_neic_code: str | None
    enterprise_neic_name: str | None
    consistency_status: str | None
    consistency_basis: str | None
    consistency_evidence_refs: list[dict[str, object]]
    error_detail: str | None
    created_at: datetime


class TechnologyFinanceWorkflowResponse(BaseModel):
    stage_a: ClassificationResultResponse
    stage_b: FiveArticlesResultResponse | None


class FiveArticlesHistoryResponse(BaseModel):
    items: list[FiveArticlesResultResponse]
