from io import BytesIO
from unittest.mock import MagicMock

import pytest
from docx import Document

from app.services.five_articles_case_ingestion import (
    create_five_articles_case_from_template,
    parse_five_articles_template,
)
from app.services.national_economy_case_ingestion import (
    NationalEconomyTemplateError,
)
from app.services.scenario_registry import (
    DIGITAL_FINANCE_REGISTRATION,
    GREEN_FINANCE_REGISTRATION,
    MULTI_SCENARIO_FINANCE_REGISTRATIONS,
    PENSION_FINANCE_REGISTRATION,
    ScenarioRegistration,
)


def _three_column_template(
    profile: ScenarioRegistration,
    *,
    issue: str | None = None,
) -> bytes:
    rows = [
        [field.label, f"测试值-{field.key}"]
        for field in profile.field_schema
    ]
    if issue == "missing":
        rows.pop()
    elif issue == "duplicate":
        rows.append(rows[0].copy())
    elif issue == "unrecognized":
        rows[0][0] = "无法识别的字段"

    document = Document()
    document.add_heading(f"{profile.name}企业信息采集表", level=1)
    document.add_paragraph("请在第二列填写，第三列为填写提示。")
    table = document.add_table(rows=1, cols=3)
    for cell, value in zip(
        table.rows[0].cells,
        ("字段名称", "填写内容", "填写提示"),
        strict=True,
    ):
        cell.text = value
    for label, value in rows:
        cells = table.add_row().cells
        cells[0].text = label
        cells[1].text = value
        cells[2].text = "不得进入案例字段"

    output = BytesIO()
    document.save(output)
    return output.getvalue()


@pytest.mark.parametrize("profile", MULTI_SCENARIO_FINANCE_REGISTRATIONS)
def test_formal_three_column_template_creates_profile_owned_case(
    profile: ScenarioRegistration,
) -> None:
    session = MagicMock()

    case = create_five_articles_case_from_template(
        session,
        profile.template_path().read_bytes(),
        f"../{profile.name}案例.docx",
        profile,
    )

    assert case.scenario == profile.id
    assert case.original_filename == f"{profile.name}案例.docx"
    assert case.status == "pending_classification"
    assert list(case.input_payload) == [field.key for field in profile.field_schema]
    assert len(case.input_payload) == len(profile.field_schema)
    assert "不得进入案例字段" not in case.input_payload.values()
    session.add.assert_called_once_with(case)
    session.commit.assert_called_once_with()
    session.refresh.assert_called_once_with(case)


@pytest.mark.parametrize(
    ("profile", "issue", "issue_name"),
    [
        (GREEN_FINANCE_REGISTRATION, "missing", "missing"),
        (DIGITAL_FINANCE_REGISTRATION, "duplicate", "duplicate"),
        (PENSION_FINANCE_REGISTRATION, "unrecognized", "unrecognized"),
    ],
)
def test_invalid_profile_template_reports_issue_without_creating_case(
    profile: ScenarioRegistration,
    issue: str,
    issue_name: str,
) -> None:
    session = MagicMock()

    with pytest.raises(NationalEconomyTemplateError) as error:
        create_five_articles_case_from_template(
            session,
            _three_column_template(profile, issue=issue),
            f"{profile.id}-{issue}.docx",
            profile,
        )

    assert getattr(error.value.issues, issue_name)
    session.add.assert_not_called()
    session.commit.assert_not_called()
    session.refresh.assert_not_called()


@pytest.mark.parametrize("profile", MULTI_SCENARIO_FINANCE_REGISTRATIONS)
def test_three_column_parser_ignores_hint_column(
    profile: ScenarioRegistration,
) -> None:
    payload = parse_five_articles_template(
        _three_column_template(profile),
        profile,
    )

    assert payload == {
        field.key: f"测试值-{field.key}"
        for field in profile.field_schema
    }
