from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Literal, Mapping

from app.core.config import Settings, get_settings
from app.services.national_economy_case_ingestion import FIELD_LABELS


TECHNOLOGY_FINANCE_SCENARIO = "technology_finance"
GREEN_FINANCE_SCENARIO = "green_finance"
DIGITAL_FINANCE_SCENARIO = "digital_finance"
PENSION_FINANCE_SCENARIO = "pension_finance"


@dataclass(frozen=True)
class ScenarioField:
    key: str
    label: str
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class ScenarioRegistration:
    id: str
    name: str
    status: Literal["available", "coming_soon"]
    description: str
    parent_id: str | None
    workflow: str | None
    template_path_setting: str | None
    field_schema: tuple[ScenarioField, ...]
    stage_a_field_keys: tuple[str, ...]
    stage_b_evidence_field_keys: tuple[str, ...]

    def template_path(self, settings: Settings | None = None) -> Path:
        if self.template_path_setting is None:
            raise ValueError(f"场景 {self.id} 暂未配置模板")
        return getattr(settings or get_settings(), self.template_path_setting)


_TECHNOLOGY_FINANCE_STAGE_A_ALIASES = {
    "counterparty_name": ("本次交易对手名称",),
    "trade_goods_services": ("核心交易品类 / 服务内容",),
}

_MULTI_SCENARIO_STAGE_A_ALIASES = {
    "enterprise_name": ("企业全称",),
    "counterparty_name": ("本次交易对手名称",),
    "trade_goods_services": ("核心交易品类 / 服务内容",),
}


def _stage_a_fields() -> tuple[ScenarioField, ...]:
    return tuple(
        ScenarioField(
            key=key,
            label=label,
            aliases=_MULTI_SCENARIO_STAGE_A_ALIASES.get(key, ()),
        )
        for key, label in FIELD_LABELS.items()
    )


def _prioritize_evidence_fields(
    schema: tuple[ScenarioField, ...],
    *preferred_keys: str,
) -> tuple[str, ...]:
    """Return the complete evidence whitelist in deterministic priority order."""
    remaining_keys = tuple(
        field.key for field in schema if field.key not in preferred_keys
    )
    return (*preferred_keys, *remaining_keys)

TECHNOLOGY_FINANCE_ADDITIONAL_FIELDS = (
    ScenarioField("entity_type", "主体类型"),
    ScenarioField("annual_revenue", "上年度营业收入"),
    ScenarioField("project_name", "对应项目名称"),
    ScenarioField("project_content", "项目建设 / 运营内容"),
    ScenarioField("employee_count", "从业人员数量"),
    ScenarioField("certifications", "企业核心资质与认证"),
    ScenarioField("rd_ip_info", "研发与知识产权情况"),
)

TECHNOLOGY_FINANCE_FIELD_SCHEMA = (
    *(
        ScenarioField(
            key=key,
            label=label,
            aliases=_TECHNOLOGY_FINANCE_STAGE_A_ALIASES.get(key, ()),
        )
        for key, label in FIELD_LABELS.items()
    ),
    *TECHNOLOGY_FINANCE_ADDITIONAL_FIELDS,
)

TECHNOLOGY_FINANCE_REGISTRATION = ScenarioRegistration(
    id=TECHNOLOGY_FINANCE_SCENARIO,
    name="科技金融",
    status="available",
    description="复用国民经济分类并生成科技金融判定",
    parent_id="five_major_articles",
    workflow="technology_finance_two_stage",
    template_path_setting="technology_finance_template_path",
    field_schema=TECHNOLOGY_FINANCE_FIELD_SCHEMA,
    stage_a_field_keys=tuple(FIELD_LABELS),
    stage_b_evidence_field_keys=tuple(
        field.key for field in TECHNOLOGY_FINANCE_FIELD_SCHEMA
    ),
)

GREEN_FINANCE_ADDITIONAL_FIELDS = (
    ScenarioField("entity_type", "主体类型"),
    ScenarioField("annual_revenue", "上年度营业收入"),
    ScenarioField("green_project_name", "对应绿色项目名称"),
    ScenarioField("project_content", "项目建设 / 运营内容"),
    ScenarioField("energy_saving_pollution_control", "节能减排 / 污染治理内容"),
    ScenarioField("green_certifications", "环保与绿色资质认证"),
    ScenarioField("carbon_environmental_benefits", "碳排放与环境效益"),
)

DIGITAL_FINANCE_ADDITIONAL_FIELDS = (
    ScenarioField("entity_type", "主体类型"),
    ScenarioField("annual_revenue", "上年度营业收入"),
    ScenarioField("project_name", "对应项目名称"),
    ScenarioField("project_content", "项目建设 / 运营内容"),
    ScenarioField("rd_ip_info", "研发与知识产权情况"),
)

PENSION_FINANCE_ADDITIONAL_FIELDS = (
    ScenarioField("entity_type", "主体类型"),
    ScenarioField("annual_revenue", "上年度营业收入"),
    ScenarioField("project_name", "对应项目名称"),
    ScenarioField("project_content", "项目建设 / 运营内容"),
    ScenarioField("certifications", "企业核心资质与认证"),
)

GREEN_FINANCE_FIELD_SCHEMA = (*_stage_a_fields(), *GREEN_FINANCE_ADDITIONAL_FIELDS)
DIGITAL_FINANCE_FIELD_SCHEMA = (*_stage_a_fields(), *DIGITAL_FINANCE_ADDITIONAL_FIELDS)
PENSION_FINANCE_FIELD_SCHEMA = (*_stage_a_fields(), *PENSION_FINANCE_ADDITIONAL_FIELDS)

GREEN_FINANCE_REGISTRATION = ScenarioRegistration(
    id=GREEN_FINANCE_SCENARIO,
    name="绿色金融",
    status="coming_soon",
    description="暂未开放",
    parent_id="five_major_articles",
    workflow=None,
    template_path_setting=None,
    field_schema=GREEN_FINANCE_FIELD_SCHEMA,
    stage_a_field_keys=tuple(FIELD_LABELS),
    stage_b_evidence_field_keys=_prioritize_evidence_fields(
        GREEN_FINANCE_FIELD_SCHEMA,
        "loan_purpose",
        "green_project_name",
        "project_content",
        "energy_saving_pollution_control",
        "carbon_environmental_benefits",
        "green_certifications",
        "trade_goods_services",
    ),
)

DIGITAL_FINANCE_REGISTRATION = ScenarioRegistration(
    id=DIGITAL_FINANCE_SCENARIO,
    name="数字金融",
    status="coming_soon",
    description="暂未开放",
    parent_id="five_major_articles",
    workflow=None,
    template_path_setting=None,
    field_schema=DIGITAL_FINANCE_FIELD_SCHEMA,
    stage_a_field_keys=tuple(FIELD_LABELS),
    stage_b_evidence_field_keys=_prioritize_evidence_fields(
        DIGITAL_FINANCE_FIELD_SCHEMA,
        "loan_purpose",
        "project_name",
        "project_content",
        "rd_ip_info",
        "trade_goods_services",
    ),
)

PENSION_FINANCE_REGISTRATION = ScenarioRegistration(
    id=PENSION_FINANCE_SCENARIO,
    name="养老金融",
    status="coming_soon",
    description="暂未开放",
    parent_id="five_major_articles",
    workflow=None,
    template_path_setting=None,
    field_schema=PENSION_FINANCE_FIELD_SCHEMA,
    stage_a_field_keys=tuple(FIELD_LABELS),
    stage_b_evidence_field_keys=_prioritize_evidence_fields(
        PENSION_FINANCE_FIELD_SCHEMA,
        "loan_purpose",
        "project_name",
        "project_content",
        "certifications",
        "trade_goods_services",
    ),
)

MULTI_SCENARIO_FINANCE_REGISTRATIONS = (
    GREEN_FINANCE_REGISTRATION,
    DIGITAL_FINANCE_REGISTRATION,
    PENSION_FINANCE_REGISTRATION,
)

COMING_SOON_SCENARIO_NAMES = MappingProxyType(
    {
        "agriculture_related": ("涉农业务", None),
        "inclusive_finance": ("普惠金融", "five_major_articles"),
    }
)

COMING_SOON_REGISTRATIONS = tuple(
    ScenarioRegistration(
        id=scenario_id,
        name=name,
        status="coming_soon",
        description="暂未开放",
        parent_id=parent_id,
        workflow=None,
        template_path_setting=None,
        field_schema=(),
        stage_a_field_keys=(),
        stage_b_evidence_field_keys=(),
    )
    for scenario_id, (name, parent_id) in COMING_SOON_SCENARIO_NAMES.items()
)

SCENARIO_REGISTRY: Mapping[str, ScenarioRegistration] = MappingProxyType(
    {
        TECHNOLOGY_FINANCE_SCENARIO: TECHNOLOGY_FINANCE_REGISTRATION,
        **{
            registration.id: registration
            for registration in MULTI_SCENARIO_FINANCE_REGISTRATIONS
        },
        **{registration.id: registration for registration in COMING_SOON_REGISTRATIONS},
    }
)
