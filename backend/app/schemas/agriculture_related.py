from datetime import datetime

from pydantic import BaseModel, ConfigDict

from app.schemas.national_economy import ClassificationResultResponse


class AgricultureRelatedResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    version: int
    status: str
    stage_a_result_id: int
    is_agriculture_related: bool | None
    matched_categories: list[dict[str, object]]
    basis: str | None
    evidence_refs: list[dict[str, object]]
    model_output: dict[str, object] | None
    error_detail: str | None
    created_at: datetime


class AgricultureRelatedWorkflowResponse(BaseModel):
    stage_a: ClassificationResultResponse
    stage_b: AgricultureRelatedResultResponse | None


class AgricultureRelatedHistoryResponse(BaseModel):
    items: list[AgricultureRelatedResultResponse]
