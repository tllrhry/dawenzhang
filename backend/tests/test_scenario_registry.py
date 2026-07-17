from pathlib import Path

import pytest
from docx import Document

from app.core.config import Settings
from app.services.national_economy_case_ingestion import FIELD_LABELS
from app.services.scenario_registry import (
    DIGITAL_FINANCE_ADDITIONAL_FIELDS,
    DIGITAL_FINANCE_REGISTRATION,
    DIGITAL_FINANCE_SCENARIO,
    AGRICULTURE_RELATED_ADDITIONAL_FIELDS,
    AGRICULTURE_RELATED_FIELD_SCHEMA,
    AGRICULTURE_RELATED_REGISTRATION,
    AGRICULTURE_RELATED_SCENARIO,
    AGRICULTURE_RELATED_STAGE_A_FIELD_KEYS,
    GREEN_FINANCE_ADDITIONAL_FIELDS,
    GREEN_FINANCE_REGISTRATION,
    GREEN_FINANCE_SCENARIO,
    INCLUSIVE_FINANCE_ADDITIONAL_FIELDS,
    INCLUSIVE_FINANCE_REGISTRATION,
    INCLUSIVE_FINANCE_SCENARIO,
    INCLUSIVE_FINANCE_STAGE_A_FIELD_KEYS,
    PENSION_FINANCE_ADDITIONAL_FIELDS,
    PENSION_FINANCE_REGISTRATION,
    PENSION_FINANCE_SCENARIO,
    SCENARIO_REGISTRY,
    TECHNOLOGY_FINANCE_ADDITIONAL_FIELDS,
    TECHNOLOGY_FINANCE_FIELD_SCHEMA,
    TECHNOLOGY_FINANCE_REGISTRATION,
    TECHNOLOGY_FINANCE_SCENARIO,
)


NEW_SCENARIO_CONTRACTS = (
    (
        GREEN_FINANCE_SCENARIO,
        GREEN_FINANCE_REGISTRATION,
        GREEN_FINANCE_ADDITIONAL_FIELDS,
        18,
        {
            "green_project_name": "对应绿色项目名称",
            "project_content": "项目建设 / 运营内容",
            "energy_saving_pollution_control": "节能减排 / 污染治理内容",
            "green_certifications": "环保与绿色资质认证",
            "carbon_environmental_benefits": "碳排放与环境效益",
        },
        (
            "loan_purpose",
            "green_project_name",
            "project_content",
            "energy_saving_pollution_control",
            "carbon_environmental_benefits",
            "green_certifications",
            "trade_goods_services",
        ),
    ),
    (
        DIGITAL_FINANCE_SCENARIO,
        DIGITAL_FINANCE_REGISTRATION,
        DIGITAL_FINANCE_ADDITIONAL_FIELDS,
        19,
        {
            "entity_type": "主体类型",
            "annual_revenue": "上年度营业收入",
            "project_name": "对应项目名称",
            "project_content": "项目建设 / 运营内容",
            "digital_core_competitiveness": "数字核心竞争力",
            "rd_ip_info": "研发与知识产权情况",
        },
        (
            "loan_purpose",
            "project_name",
            "project_content",
            "industry_position_competitiveness",
            "digital_core_competitiveness",
            "rd_ip_info",
            "trade_goods_services",
        ),
    ),
    (
        PENSION_FINANCE_SCENARIO,
        PENSION_FINANCE_REGISTRATION,
        PENSION_FINANCE_ADDITIONAL_FIELDS,
        19,
        {
            "entity_type": "主体类型",
            "annual_revenue": "上年度营业收入",
            "project_name": "对应项目名称",
            "project_content": "项目建设 / 运营内容",
            "pension_loan_direction_share": "该笔贷款实际投向养老产业占总贷款额度比",
            "certifications": "企业核心资质与认证",
        },
        (
            "loan_purpose",
            "project_name",
            "project_content",
            "pension_loan_direction_share",
            "main_business_revenue_share",
            "certifications",
            "trade_goods_services",
        ),
    ),
)


EXPECTED_ADDITIONAL_FIELDS = {
    "entity_type": "主体类型",
    "annual_revenue": "上年度营业收入",
    "project_name": "对应项目名称",
    "project_content": "项目建设 / 运营内容",
    "employee_count": "从业人员数量",
    "certifications": "企业核心资质与认证",
    "rd_ip_info": "研发与知识产权情况",
}


def test_technology_finance_registration_and_field_keys_are_stable() -> None:
    registration = SCENARIO_REGISTRY[TECHNOLOGY_FINANCE_SCENARIO]
    field_labels = {field.key: field.label for field in registration.field_schema}

    assert registration is TECHNOLOGY_FINANCE_REGISTRATION
    assert registration.id == "technology_finance"
    assert registration.name == "科技金融"
    assert registration.status == "available"
    assert registration.parent_id == "five_major_articles"
    assert len(field_labels) == len(FIELD_LABELS) + len(EXPECTED_ADDITIONAL_FIELDS)
    assert len(field_labels) == len(registration.field_schema)
    assert all(field.key and field.label for field in registration.field_schema)


def test_technology_finance_schema_reuses_the_complete_stage_a_subset() -> None:
    field_labels = {field.key: field.label for field in TECHNOLOGY_FINANCE_FIELD_SCHEMA}

    assert TECHNOLOGY_FINANCE_REGISTRATION.stage_a_field_keys == tuple(FIELD_LABELS)
    assert {
        key: field_labels[key]
        for key in TECHNOLOGY_FINANCE_REGISTRATION.stage_a_field_keys
    } == FIELD_LABELS


def test_technology_finance_schema_contains_all_additional_fields() -> None:
    additional_fields = {
        field.key: field.label for field in TECHNOLOGY_FINANCE_ADDITIONAL_FIELDS
    }

    assert additional_fields == EXPECTED_ADDITIONAL_FIELDS


def test_new_finance_scenario_schema_contracts_are_stable() -> None:
    for (
        scenario_id,
        registration,
        additional_fields,
        expected_count,
        expected_additional_fields,
        expected_evidence_prefix,
    ) in NEW_SCENARIO_CONTRACTS:
        schema_labels = {field.key: field.label for field in registration.field_schema}
        actual_additional_fields = {
            field.key: field.label for field in additional_fields
        }

        assert SCENARIO_REGISTRY[scenario_id] is registration
        assert registration.status == "available"
        assert registration.parent_id == "five_major_articles"
        assert len(registration.field_schema) == expected_count
        assert len(schema_labels) == expected_count
        assert all(field.key and field.label for field in registration.field_schema)
        assert actual_additional_fields == expected_additional_fields
        assert registration.stage_a_field_keys == tuple(FIELD_LABELS)
        assert {
            key: schema_labels[key] for key in registration.stage_a_field_keys
        } == FIELD_LABELS
        assert registration.stage_b_evidence_field_keys[: len(expected_evidence_prefix)] == (
            expected_evidence_prefix
        )
        assert set(registration.stage_b_evidence_field_keys) == set(schema_labels)
        assert len(registration.stage_b_evidence_field_keys) == expected_count


def test_new_finance_schemas_normalize_locked_stage_a_aliases() -> None:
    expected_aliases = {
        "enterprise_name": ("企业全称",),
        "counterparty_name": ("本次交易对手名称",),
        "trade_goods_services": ("核心交易品类 / 服务内容",),
    }

    for _, registration, *_ in NEW_SCENARIO_CONTRACTS:
        fields = {field.key: field for field in registration.field_schema}
        assert {
            key: fields[key].aliases for key in expected_aliases
        } == expected_aliases


def test_new_finance_schemas_do_not_persist_template_hint_column() -> None:
    for _, registration, *_ in NEW_SCENARIO_CONTRACTS:
        assert "填写提示" not in {
            field.label for field in registration.field_schema
        }
        assert all(not hasattr(field, "hint") for field in registration.field_schema)


def test_technology_finance_template_path_comes_from_settings(
    monkeypatch,
    tmp_path: Path,
) -> None:
    configured_path = tmp_path / "technology-finance.docx"
    monkeypatch.setenv("TECHNOLOGY_FINANCE_TEMPLATE_PATH", str(configured_path))
    settings = Settings(_env_file=None)

    assert settings.technology_finance_template_path == configured_path
    assert TECHNOLOGY_FINANCE_REGISTRATION.template_path(settings) == configured_path


def test_technology_finance_template_path_defaults_to_existing_asset() -> None:
    settings = Settings(_env_file=None)

    assert settings.technology_finance_template_path == Path(
        "模板文件/五篇大文章/科技金融模版 .docx"
    )


@pytest.mark.parametrize(
    ("registration", "template_name", "export_sheet_name"),
    (
        (
            TECHNOLOGY_FINANCE_REGISTRATION,
            "technology-template.docx",
            "科技金融判定",
        ),
        (
            GREEN_FINANCE_REGISTRATION,
            "green-template.docx",
            "绿色金融判定",
        ),
        (
            DIGITAL_FINANCE_REGISTRATION,
            "digital-template.docx",
            "数字金融判定",
        ),
        (
            PENSION_FINANCE_REGISTRATION,
            "pension-template.docx",
            "养老金融判定",
        ),
    ),
)
def test_new_finance_profiles_resolve_independent_execution_metadata(
    monkeypatch,
    tmp_path: Path,
    registration,
    template_name: str,
    export_sheet_name: str,
) -> None:
    template_path = tmp_path / template_name
    shared_mapping_path = tmp_path / "five-articles-mapping.xlsx"
    green_mapping_path = tmp_path / "green-finance-mapping.xlsx"
    monkeypatch.setenv(registration.template_path_setting.upper(), str(template_path))
    monkeypatch.setenv("FIVE_ARTICLES_MAPPING_SOURCE_PATH", str(shared_mapping_path))
    monkeypatch.setenv("GREEN_FINANCE_MAPPING_SOURCE_PATH", str(green_mapping_path))
    settings = Settings(_env_file=None)

    assert registration.status == "available"
    assert registration.workflow == "technology_finance_two_stage"
    assert registration.is_executable_profile is True
    assert registration.template_path(settings) == template_path
    expected_mapping_path = (
        green_mapping_path
        if registration is GREEN_FINANCE_REGISTRATION
        else shared_mapping_path
    )
    assert registration.mapping_path(settings) == expected_mapping_path
    assert registration.export_sheet_name == export_sheet_name
    assert registration.field_schema
    assert registration.name in export_sheet_name


def test_five_articles_mapping_profiles_declare_source_and_column_shape() -> None:
    assert GREEN_FINANCE_REGISTRATION.mapping_path_setting == (
        "green_finance_mapping_source_path"
    )
    assert GREEN_FINANCE_REGISTRATION.mapping_tier_depth == 2
    assert GREEN_FINANCE_REGISTRATION.mapping_has_condition_criteria is True

    for registration, expected_tier_depth in (
        (TECHNOLOGY_FINANCE_REGISTRATION, 4),
        (DIGITAL_FINANCE_REGISTRATION, 3),
        (PENSION_FINANCE_REGISTRATION, 3),
    ):
        assert registration.mapping_path_setting is None
        assert registration.mapping_tier_depth == expected_tier_depth
        assert registration.mapping_has_condition_criteria is False


def test_agriculture_and_unknown_scenarios_resolve_correctly() -> None:
    agriculture = SCENARIO_REGISTRY[AGRICULTURE_RELATED_SCENARIO]

    assert agriculture is AGRICULTURE_RELATED_REGISTRATION
    assert agriculture.status == "available"
    assert agriculture.parent_id is None
    assert agriculture.workflow == "agriculture_related_single_stage"
    assert agriculture.template_path_setting == "agriculture_related_template_path"
    assert agriculture.uses_five_articles_mapping is False
    assert agriculture.export_sheet_name == "涉农判定"
    assert agriculture.is_executable_profile is True
    assert SCENARIO_REGISTRY.get("not_registered") is None

    with pytest.raises(ValueError, match="暂未配置映射"):
        agriculture.mapping_path(Settings(_env_file=None))


def test_agriculture_related_schema_matches_template_and_reuses_existing_keys() -> None:
    expected_stage_a = {
        "enterprise_name": "企业名称",
        "unified_social_credit_code": "统一社会信用代码",
        "main_business": "主营业务",
        "business_scope": "营业执照经营范围（全文）",
        "main_business_revenue_share": "主营业务及营收占比",
        "loan_purpose": "贷款用途详细描述",
        "counterparty_name": "本次交易对手名称",
        "counterparty_business_industry": "交易对手主营业务 / 所属行业",
        "trade_goods_services": "核心交易品类 / 服务内容",
        "credit_approval_opinion": "授信审批意见",
    }
    expected_additional = {
        field.key: field.label for field in AGRICULTURE_RELATED_ADDITIONAL_FIELDS
    }
    fields = {field.key: field.label for field in AGRICULTURE_RELATED_FIELD_SCHEMA}

    assert AGRICULTURE_RELATED_REGISTRATION.status == "available"
    assert AGRICULTURE_RELATED_REGISTRATION.parent_id is None
    assert AGRICULTURE_RELATED_REGISTRATION.workflow == "agriculture_related_single_stage"
    assert AGRICULTURE_RELATED_REGISTRATION.template_path_setting == (
        "agriculture_related_template_path"
    )
    assert AGRICULTURE_RELATED_REGISTRATION.template_path(Settings(_env_file=None)).is_file()
    assert len(AGRICULTURE_RELATED_FIELD_SCHEMA) == 20
    assert len(fields) == 20
    template = Document(
        AGRICULTURE_RELATED_REGISTRATION.template_path(Settings(_env_file=None))
    )
    assert tuple(field.label for field in AGRICULTURE_RELATED_FIELD_SCHEMA) == tuple(
        row.cells[0].text.strip() for row in template.tables[0].rows[1:]
    )
    assert AGRICULTURE_RELATED_STAGE_A_FIELD_KEYS == tuple(expected_stage_a)
    assert {key: fields[key] for key in expected_stage_a} == expected_stage_a
    assert expected_additional == {
        "registered_address": "企业注册地址",
        "actual_business_address": "实际经营地址",
        "farmer_long_term_town_resident": "是否为乡镇（不含城关镇）长期住户",
        "farmer_town_village_resident": "是否为城关镇所辖行政村住户",
        "farmer_nonlocal_resident_over_one_year": "是否为户籍不在本地的常住住户",
        "farmer_state_farm_employee_or_rural_individual_business": "是否为国有农场职工或农村个体工商户",
        "entity_type": "主体类型",
        "annual_revenue": "上年度营业收入",
        "project_name": "对应项目名称",
        "project_content": "项目建设 / 运营内容",
    }
    assert set(fields) == set(expected_stage_a) | set(expected_additional)
    assert not {
        "core_products_services",
        "industry_chain_position",
        "industry_position_competitiveness",
    } & set(fields)


def test_inclusive_finance_profile_is_mapping_free_and_has_real_stage_a_subset() -> None:
    registration = SCENARIO_REGISTRY[INCLUSIVE_FINANCE_SCENARIO]
    fields = {field.key: field.label for field in registration.field_schema}
    additional_fields = {
        field.key: field.label for field in INCLUSIVE_FINANCE_ADDITIONAL_FIELDS
    }

    assert registration is INCLUSIVE_FINANCE_REGISTRATION
    assert registration.status == "available"
    assert registration.parent_id == "five_major_articles"
    assert registration.workflow == "inclusive_finance_single_stage"
    assert registration.uses_five_articles_mapping is False
    assert registration.export_sheet_name == "普惠金融判定"
    assert registration.is_executable_profile is True
    assert registration.stage_a_field_keys == INCLUSIVE_FINANCE_STAGE_A_FIELD_KEYS
    assert registration.stage_a_field_keys == tuple(
        key
        for key in FIELD_LABELS
        if key not in {"main_business", "counterparty_name"}
    )
    assert "main_business" not in fields
    assert "counterparty_name" not in fields
    assert len(fields) == 23
    assert len(fields) == len(registration.field_schema)
    assert additional_fields == {
        "registered_address": "企业注册地址",
        "entity_type": "主体类型",
        "farmer_long_term_town_resident": "是否指长期（一年以上）居住在乡镇（不包括城关镇）行政管理区域内的住户",
        "farmer_town_village_resident": "是否长期居住在城关镇所辖行政村范围内的住户",
        "farmer_nonlocal_resident_over_one_year": "是否户口不在本地而在本地居住一年以上的住户",
        "farmer_state_farm_employee_or_rural_individual_business": "是否国有农场的职工或农村个体工商户。",
        "enterprise_scale_type": "企业规模类型",
        "total_assets": "总资产",
        "annual_revenue": "上年度营业收入",
        "employee_count": "从业人员数量",
        "credit_amount": "本次授信额度",
        "credit_variety": "授信品种",
    }
    with pytest.raises(ValueError, match="暂未配置映射"):
        registration.mapping_path(Settings(_env_file=None))
