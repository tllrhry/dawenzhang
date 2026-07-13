from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType
from typing import Literal, Mapping

from app.core.config import Settings, get_settings
from app.services.national_economy_case_ingestion import FIELD_LABELS


TECHNOLOGY_FINANCE_SCENARIO = "technology_finance"


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

    def template_path(self, settings: Settings | None = None) -> Path:
        if self.template_path_setting is None:
            raise ValueError(f"场景 {self.id} 暂未配置模板")
        return getattr(settings or get_settings(), self.template_path_setting)


_TECHNOLOGY_FINANCE_STAGE_A_ALIASES = {
    "counterparty_name": ("本次交易对手名称",),
    "trade_goods_services": ("核心交易品类 / 服务内容",),
}

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
)

COMING_SOON_SCENARIO_NAMES = MappingProxyType(
    {
        "agriculture_related": ("涉农业务", None),
        "green_finance": ("绿色金融", "five_major_articles"),
        "inclusive_finance": ("普惠金融", "five_major_articles"),
        "pension_finance": ("养老金融", "five_major_articles"),
        "digital_finance": ("数字金融", "five_major_articles"),
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
    )
    for scenario_id, (name, parent_id) in COMING_SOON_SCENARIO_NAMES.items()
)

SCENARIO_REGISTRY: Mapping[str, ScenarioRegistration] = MappingProxyType(
    {
        TECHNOLOGY_FINANCE_SCENARIO: TECHNOLOGY_FINANCE_REGISTRATION,
        **{registration.id: registration for registration in COMING_SOON_REGISTRATIONS},
    }
)
