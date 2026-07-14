from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from app.schemas.national_economy import ClassificationResultResponse
from app.services.agriculture_related_determination import FARMER_IDENTITY_FIELD_LABELS


def _localize_farmer_identity_basis(value: object) -> object:
    if not isinstance(value, str):
        return value
    for field_key, label in FARMER_IDENTITY_FIELD_LABELS.items():
        value = value.replace(field_key, label)
    return value


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

    @field_validator("basis", mode="before")
    @classmethod
    def localize_basis(cls, value: object) -> object:
        return _localize_farmer_identity_basis(value)

    @field_validator("matched_categories", mode="before")
    @classmethod
    def localize_category_basis(cls, value: object) -> object:
        if not isinstance(value, list):
            return value
        return [
            {
                **item,
                "basis": _localize_farmer_identity_basis(item.get("basis")),
            }
            if isinstance(item, dict) and "basis" in item
            else item
            for item in value
        ]


class AgricultureRelatedWorkflowResponse(BaseModel):
    stage_a: ClassificationResultResponse
    stage_b: AgricultureRelatedResultResponse | None


class AgricultureRelatedHistoryResponse(BaseModel):
    items: list[AgricultureRelatedResultResponse]
