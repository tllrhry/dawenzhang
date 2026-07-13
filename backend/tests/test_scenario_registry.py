from pathlib import Path

import pytest

from app.core.config import Settings
from app.services.national_economy_case_ingestion import FIELD_LABELS
from app.services.scenario_registry import (
    DIGITAL_FINANCE_ADDITIONAL_FIELDS,
    DIGITAL_FINANCE_REGISTRATION,
    DIGITAL_FINANCE_SCENARIO,
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
        20,
        {
            "entity_type": "主体类型",
            "annual_revenue": "上年度营业收入",
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
        18,
        {
            "entity_type": "主体类型",
            "annual_revenue": "上年度营业收入",
            "project_name": "对应项目名称",
            "project_content": "项目建设 / 运营内容",
            "rd_ip_info": "研发与知识产权情况",
        },
        (
            "loan_purpose",
            "project_name",
            "project_content",
            "rd_ip_info",
            "trade_goods_services",
        ),
    ),
    (
        PENSION_FINANCE_SCENARIO,
        PENSION_FINANCE_REGISTRATION,
        PENSION_FINANCE_ADDITIONAL_FIELDS,
        18,
        {
            "entity_type": "主体类型",
            "annual_revenue": "上年度营业收入",
            "project_name": "对应项目名称",
            "project_content": "项目建设 / 运营内容",
            "certifications": "企业核心资质与认证",
        },
        (
            "loan_purpose",
            "project_name",
            "project_content",
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
        assert registration.status == "coming_soon"
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
    ("registration", "template_name", "mapping_name", "export_sheet_name"),
    (
        (
            GREEN_FINANCE_REGISTRATION,
            "green-template.docx",
            "green-mapping.xlsx",
            "绿色金融判定",
        ),
        (
            DIGITAL_FINANCE_REGISTRATION,
            "digital-template.docx",
            "digital-mapping.xlsx",
            "数字金融判定",
        ),
        (
            PENSION_FINANCE_REGISTRATION,
            "pension-template.docx",
            "pension-mapping.xlsx",
            "养老金融判定",
        ),
    ),
)
def test_new_finance_profiles_resolve_independent_execution_metadata(
    monkeypatch,
    tmp_path: Path,
    registration,
    template_name: str,
    mapping_name: str,
    export_sheet_name: str,
) -> None:
    template_path = tmp_path / template_name
    mapping_path = tmp_path / mapping_name
    monkeypatch.setenv(registration.template_path_setting.upper(), str(template_path))
    monkeypatch.setenv(registration.mapping_path_setting.upper(), str(mapping_path))
    settings = Settings(_env_file=None)

    assert registration.status == "coming_soon"
    assert registration.workflow == "technology_finance_two_stage"
    assert registration.is_executable_profile is True
    assert registration.template_path(settings) == template_path
    assert registration.mapping_path(settings) == mapping_path
    assert registration.export_sheet_name == export_sheet_name
    assert registration.field_schema
    assert registration.name in export_sheet_name


def test_inclusive_and_unknown_scenarios_are_not_executable_profiles() -> None:
    inclusive = SCENARIO_REGISTRY["agriculture_related"]

    assert inclusive.status == "coming_soon"
    assert inclusive.workflow is None
    assert inclusive.template_path_setting is None
    assert inclusive.mapping_path_setting is None
    assert inclusive.export_sheet_name is None
    assert inclusive.is_executable_profile is False
    assert SCENARIO_REGISTRY.get("not_registered") is None

    with pytest.raises(ValueError, match="暂未配置模板"):
        inclusive.template_path(Settings(_env_file=None))
    with pytest.raises(ValueError, match="暂未配置映射"):
        inclusive.mapping_path(Settings(_env_file=None))


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
    assert registration.mapping_path_setting is None
    assert registration.export_sheet_name == "普惠金融判定"
    assert registration.is_executable_profile is True
    assert registration.stage_a_field_keys == INCLUSIVE_FINANCE_STAGE_A_FIELD_KEYS
    assert registration.stage_a_field_keys == tuple(
        key for key in FIELD_LABELS if key != "main_business"
    )
    assert "main_business" not in fields
    assert len(fields) == 31
    assert len(fields) == len(registration.field_schema)
    assert additional_fields == {
        "registered_address": "企业注册地址",
        "actual_business_address": "实际经营地址",
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
        "project_name": "对应项目名称",
        "project_content": "项目建设 / 运营内容",
        "credit_term": "授信期限",
        "transaction_amount": "交易金额",
        "certifications": "企业核心资质与认证",
        "rd_ip_info": "研发与知识产权情况",
    }
    with pytest.raises(ValueError, match="暂未配置映射"):
        registration.mapping_path(Settings(_env_file=None))
