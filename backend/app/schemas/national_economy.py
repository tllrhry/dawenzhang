from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ScenarioItem(BaseModel):
    id: str
    name: str
    status: str
    description: str
    parent_id: str | None = None


class ScenarioListResponse(BaseModel):
    items: list[ScenarioItem]


class CaseInputField(BaseModel):
    field: str
    label: str
    value: object


class ClassificationResultResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    version: int
    status: str
    industry_code: str | None
    industry_name: str | None
    confidence: int | None
    rationale: str | None
    ai_summary: str | None
    candidate_snapshot: list[dict[str, object]]
    objection: dict[str, object] | None
    created_at: datetime


class CaseResponse(BaseModel):
    id: int
    scenario: str
    status: str
    original_filename: str | None
    input_fields: list[CaseInputField]
    current_result: ClassificationResultResponse | None
    created_at: datetime
    updated_at: datetime


class CaseCreatedResponse(BaseModel):
    id: int
    scenario: str
    status: str
    original_filename: str | None


class TemplateIssueDetail(BaseModel):
    message: str
    missing: list[str]
    duplicate: list[str]
    unrecognized: list[str]


class ObjectionRequest(BaseModel):
    objection_text: str = Field(min_length=1)


class ResultHistoryResponse(BaseModel):
    items: list[ClassificationResultResponse]
