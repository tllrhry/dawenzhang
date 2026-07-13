from pathlib import Path

from app.core.config import Settings
from app.services.national_economy_case_ingestion import FIELD_LABELS
from app.services.scenario_registry import (
    SCENARIO_REGISTRY,
    TECHNOLOGY_FINANCE_ADDITIONAL_FIELDS,
    TECHNOLOGY_FINANCE_FIELD_SCHEMA,
    TECHNOLOGY_FINANCE_REGISTRATION,
    TECHNOLOGY_FINANCE_SCENARIO,
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
