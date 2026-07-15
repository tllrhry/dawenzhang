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
INCLUSIVE_FINANCE_SCENARIO = "inclusive_finance"
AGRICULTURE_RELATED_SCENARIO = "agriculture_related"


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
    uses_five_articles_mapping: bool
    export_sheet_name: str | None
    field_schema: tuple[ScenarioField, ...]
    stage_a_field_keys: tuple[str, ...]
    stage_b_evidence_field_keys: tuple[str, ...]
    mapping_tier_depth: int = 4
    mapping_path_setting: str | None = None
    mapping_has_condition_criteria: bool = False

    def template_path(self, settings: Settings | None = None) -> Path:
        if self.template_path_setting is None:
            raise ValueError(f"场景 {self.id} 暂未配置模板")
        return getattr(settings or get_settings(), self.template_path_setting)

    def mapping_path(self, settings: Settings | None = None) -> Path:
        if not self.uses_five_articles_mapping:
            raise ValueError(f"场景 {self.id} 暂未配置映射")
        resolved_settings = settings or get_settings()
        if self.mapping_path_setting is not None:
            return getattr(resolved_settings, self.mapping_path_setting)
        return resolved_settings.five_articles_mapping_source_path

    @property
    def is_executable_profile(self) -> bool:
        """Whether the registration has all metadata required by a workflow."""
        return all(
            (
                self.workflow,
                self.template_path_setting,
                self.export_sheet_name,
                self.field_schema,
            )
        )


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
    uses_five_articles_mapping=True,
    export_sheet_name="科技金融判定",
    field_schema=TECHNOLOGY_FINANCE_FIELD_SCHEMA,
    stage_a_field_keys=tuple(FIELD_LABELS),
    stage_b_evidence_field_keys=tuple(
        field.key for field in TECHNOLOGY_FINANCE_FIELD_SCHEMA
    ),
    mapping_tier_depth=4,
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

INCLUSIVE_FINANCE_STAGE_A_FIELD_KEYS = tuple(
    key for key in FIELD_LABELS if key != "main_business"
)

INCLUSIVE_FINANCE_ADDITIONAL_FIELDS = (
    ScenarioField("registered_address", "企业注册地址"),
    ScenarioField("actual_business_address", "实际经营地址"),
    ScenarioField("entity_type", "主体类型"),
    ScenarioField(
        "farmer_long_term_town_resident",
        "是否指长期（一年以上）居住在乡镇（不包括城关镇）行政管理区域内的住户",
    ),
    ScenarioField(
        "farmer_town_village_resident",
        "是否长期居住在城关镇所辖行政村范围内的住户",
    ),
    ScenarioField(
        "farmer_nonlocal_resident_over_one_year",
        "是否户口不在本地而在本地居住一年以上的住户",
    ),
    ScenarioField(
        "farmer_state_farm_employee_or_rural_individual_business",
        "是否国有农场的职工或农村个体工商户。",
    ),
    ScenarioField("enterprise_scale_type", "企业规模类型"),
    ScenarioField("total_assets", "总资产"),
    ScenarioField("annual_revenue", "上年度营业收入"),
    ScenarioField("employee_count", "从业人员数量"),
    ScenarioField("credit_amount", "本次授信额度"),
    ScenarioField("credit_variety", "授信品种"),
    ScenarioField("project_name", "对应项目名称"),
    ScenarioField("project_content", "项目建设 / 运营内容"),
    ScenarioField("credit_term", "授信期限"),
    ScenarioField("transaction_amount", "交易金额"),
    ScenarioField("certifications", "企业核心资质与认证"),
    ScenarioField("rd_ip_info", "研发与知识产权情况"),
)

INCLUSIVE_FINANCE_FIELD_SCHEMA = (
    *(
        field
        for field in _stage_a_fields()
        if field.key in INCLUSIVE_FINANCE_STAGE_A_FIELD_KEYS
    ),
    *INCLUSIVE_FINANCE_ADDITIONAL_FIELDS,
)

AGRICULTURE_RELATED_STAGE_A_FIELD_KEYS = (
    "enterprise_name",
    "unified_social_credit_code",
    "main_business",
    "business_scope",
    "main_business_revenue_share",
    "loan_purpose",
    "counterparty_name",
    "counterparty_business_industry",
    "trade_goods_services",
    "credit_approval_opinion",
)

_AGRICULTURE_RELATED_STAGE_A_TEMPLATE_LABELS = {
    "counterparty_name": "本次交易对手名称",
    "trade_goods_services": "核心交易品类 / 服务内容",
}

AGRICULTURE_RELATED_ADDITIONAL_FIELDS = (
    ScenarioField("registered_address", "企业注册地址"),
    ScenarioField("actual_business_address", "实际经营地址"),
    ScenarioField("farmer_long_term_town_resident", "是否为乡镇（不含城关镇）长期住户"),
    ScenarioField("farmer_town_village_resident", "是否为城关镇所辖行政村住户"),
    ScenarioField("farmer_nonlocal_resident_over_one_year", "是否为户籍不在本地的常住住户"),
    ScenarioField(
        "farmer_state_farm_employee_or_rural_individual_business",
        "是否为国有农场职工或农村个体工商户",
    ),
    ScenarioField("entity_type", "主体类型"),
    ScenarioField("annual_revenue", "上年度营业收入"),
    ScenarioField("project_name", "对应项目名称"),
    ScenarioField("project_content", "项目建设 / 运营内容"),
)

_AGRICULTURE_RELATED_FIELDS_BY_KEY = {
    field.key: field for field in AGRICULTURE_RELATED_ADDITIONAL_FIELDS
}
_AGRICULTURE_RELATED_FIELDS_BY_KEY.update(
    {
        key: ScenarioField(
            key=key,
            label=_AGRICULTURE_RELATED_STAGE_A_TEMPLATE_LABELS.get(
                key, FIELD_LABELS[key]
            ),
            aliases=tuple(
                dict.fromkeys(
                    (
                        *_MULTI_SCENARIO_STAGE_A_ALIASES.get(key, ()),
                        FIELD_LABELS[key],
                    )
                )
            ),
        )
        for key in AGRICULTURE_RELATED_STAGE_A_FIELD_KEYS
    }
)
AGRICULTURE_RELATED_FIELD_SCHEMA = tuple(
    _AGRICULTURE_RELATED_FIELDS_BY_KEY[key]
    for key in (
        "enterprise_name",
        "unified_social_credit_code",
        "registered_address",
        "actual_business_address",
        "farmer_long_term_town_resident",
        "farmer_town_village_resident",
        "farmer_nonlocal_resident_over_one_year",
        "farmer_state_farm_employee_or_rural_individual_business",
        "entity_type",
        "main_business",
        "annual_revenue",
        "business_scope",
        "main_business_revenue_share",
        "loan_purpose",
        "project_name",
        "project_content",
        "counterparty_name",
        "counterparty_business_industry",
        "trade_goods_services",
        "credit_approval_opinion",
    )
)

AGRICULTURE_RELATED_REGISTRATION = ScenarioRegistration(
    id=AGRICULTURE_RELATED_SCENARIO,
    name="涉农业务",
    status="available",
    description="复用国民经济分类并执行全口径涉农贷款判定",
    parent_id=None,
    workflow="agriculture_related_single_stage",
    template_path_setting="agriculture_related_template_path",
    uses_five_articles_mapping=False,
    export_sheet_name="涉农判定",
    field_schema=AGRICULTURE_RELATED_FIELD_SCHEMA,
    stage_a_field_keys=AGRICULTURE_RELATED_STAGE_A_FIELD_KEYS,
    stage_b_evidence_field_keys=_prioritize_evidence_fields(
        AGRICULTURE_RELATED_FIELD_SCHEMA,
        "registered_address",
        "actual_business_address",
        "farmer_long_term_town_resident",
        "farmer_town_village_resident",
        "farmer_nonlocal_resident_over_one_year",
        "farmer_state_farm_employee_or_rural_individual_business",
        "loan_purpose",
        "project_content",
        "trade_goods_services",
    ),
)

GREEN_FINANCE_REGISTRATION = ScenarioRegistration(
    id=GREEN_FINANCE_SCENARIO,
    name="绿色金融",
    status="available",
    description="复用国民经济分类并生成绿色金融判定",
    parent_id="five_major_articles",
    workflow="technology_finance_two_stage",
    template_path_setting="green_finance_template_path",
    uses_five_articles_mapping=True,
    export_sheet_name="绿色金融判定",
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
    mapping_tier_depth=2,
    mapping_path_setting="green_finance_mapping_source_path",
    mapping_has_condition_criteria=True,
)

DIGITAL_FINANCE_REGISTRATION = ScenarioRegistration(
    id=DIGITAL_FINANCE_SCENARIO,
    name="数字金融",
    status="available",
    description="复用国民经济分类并生成数字金融判定",
    parent_id="five_major_articles",
    workflow="technology_finance_two_stage",
    template_path_setting="digital_finance_template_path",
    uses_five_articles_mapping=True,
    export_sheet_name="数字金融判定",
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
    mapping_tier_depth=3,
)

PENSION_FINANCE_REGISTRATION = ScenarioRegistration(
    id=PENSION_FINANCE_SCENARIO,
    name="养老金融",
    status="available",
    description="复用国民经济分类并生成养老金融判定",
    parent_id="five_major_articles",
    workflow="technology_finance_two_stage",
    template_path_setting="pension_finance_template_path",
    uses_five_articles_mapping=True,
    export_sheet_name="养老金融判定",
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
    mapping_tier_depth=3,
)

INCLUSIVE_FINANCE_REGISTRATION = ScenarioRegistration(
    id=INCLUSIVE_FINANCE_SCENARIO,
    name="普惠金融",
    status="available",
    description="复用国民经济分类并执行普惠金融确定性判定",
    parent_id="five_major_articles",
    workflow="inclusive_finance_single_stage",
    template_path_setting="inclusive_finance_template_path",
    uses_five_articles_mapping=False,
    export_sheet_name="普惠金融判定",
    field_schema=INCLUSIVE_FINANCE_FIELD_SCHEMA,
    stage_a_field_keys=INCLUSIVE_FINANCE_STAGE_A_FIELD_KEYS,
    stage_b_evidence_field_keys=_prioritize_evidence_fields(
        INCLUSIVE_FINANCE_FIELD_SCHEMA,
        "entity_type",
        "enterprise_scale_type",
        "total_assets",
        "annual_revenue",
        "employee_count",
        "credit_amount",
        "credit_variety",
        "loan_purpose",
        "project_name",
        "project_content",
        "farmer_long_term_town_resident",
        "farmer_town_village_resident",
        "farmer_nonlocal_resident_over_one_year",
        "farmer_state_farm_employee_or_rural_individual_business",
    ),
)

MULTI_SCENARIO_FINANCE_REGISTRATIONS = (
    GREEN_FINANCE_REGISTRATION,
    DIGITAL_FINANCE_REGISTRATION,
    PENSION_FINANCE_REGISTRATION,
    INCLUSIVE_FINANCE_REGISTRATION,
)

COMING_SOON_SCENARIO_NAMES = MappingProxyType({})

COMING_SOON_REGISTRATIONS = tuple(
    ScenarioRegistration(
        id=scenario_id,
        name=name,
        status="coming_soon",
        description="暂未开放",
        parent_id=parent_id,
        workflow=None,
        template_path_setting=None,
        uses_five_articles_mapping=False,
        export_sheet_name=None,
        field_schema=(),
        stage_a_field_keys=(),
        stage_b_evidence_field_keys=(),
    )
    for scenario_id, (name, parent_id) in COMING_SOON_SCENARIO_NAMES.items()
)

SCENARIO_REGISTRY: Mapping[str, ScenarioRegistration] = MappingProxyType(
    {
        TECHNOLOGY_FINANCE_SCENARIO: TECHNOLOGY_FINANCE_REGISTRATION,
        AGRICULTURE_RELATED_SCENARIO: AGRICULTURE_RELATED_REGISTRATION,
        **{
            registration.id: registration
            for registration in MULTI_SCENARIO_FINANCE_REGISTRATIONS
        },
        **{registration.id: registration for registration in COMING_SOON_REGISTRATIONS},
    }
)
