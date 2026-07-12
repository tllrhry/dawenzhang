from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator

from app.services.national_economy_result_presentation import (
    format_industry_display_code,
)


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
    industry_major_code: str | None = Field(default=None, exclude=True)
    industry_name: str | None
    matching_basis: str | None = Field(validation_alias="rationale")
    loan_industry_code: str | None
    loan_industry_major_code: str | None = Field(default=None, exclude=True)
    loan_industry_name: str | None
    loan_matching_basis: str | None
    loan_matches_enterprise: bool | None
    candidate_snapshot: list[dict[str, object]]
    objection: dict[str, object] | None
    created_at: datetime

    @model_validator(mode="after")
    def populate_legacy_loan_direction(self) -> "ClassificationResultResponse":
        if self.loan_industry_code is None and self.loan_matching_basis is None:
            self.loan_matches_enterprise = True
            if self.industry_code is not None:
                self.loan_industry_code = self.industry_code
                self.loan_industry_major_code = self.industry_major_code
                self.loan_industry_name = self.industry_name
            self.loan_matching_basis = "贷款投向未单独评估，与企业主营一致"
        elif self.loan_industry_code is None:
            self.loan_industry_name = None
            self.loan_matches_enterprise = False
        else:
            self.loan_matches_enterprise = self.loan_matches_enterprise is True
        return self

    @computed_field(return_type=str | None)
    @property
    def industry_display_code(self) -> str | None:
        return format_industry_display_code(
            self.industry_major_code,
            self.industry_code,
        )

    @computed_field(return_type=str | None)
    @property
    def loan_industry_display_code(self) -> str | None:
        return format_industry_display_code(
            self.loan_industry_major_code,
            self.loan_industry_code,
        )


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
