from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.core.config import Settings
from app.services.national_economy_case_ingestion import (
    FIELD_LABELS,
    NationalEconomyTemplateError,
    create_case_from_template,
    parse_template,
    read_template_bytes,
)


FIXTURES = Path(__file__).parent / "fixtures" / "national_economy"


def _fixture_bytes(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


def test_valid_template_creates_pending_case_with_thirteen_fields() -> None:
    session = MagicMock()

    case = create_case_from_template(
        session,
        _fixture_bytes("valid.docx"),
        "../企业A.docx",
    )

    assert case.scenario == "national_economy_classification"
    assert case.status == "pending_classification"
    assert case.original_filename == "企业A.docx"
    assert list(case.input_payload) == list(FIELD_LABELS)
    assert case.input_payload["enterprise_name"] == "南京示例科技有限公司"
    assert case.input_payload["credit_approval_opinion"] == "同意授信"
    session.add.assert_called_once_with(case)
    session.commit.assert_called_once_with()
    session.refresh.assert_called_once_with(case)


def test_unfilled_fields_are_saved_as_empty_strings() -> None:
    payload = parse_template(_fixture_bytes("empty_fields.docx"))

    assert len(payload) == 13
    assert payload["enterprise_name"] == "南京示例科技有限公司"
    assert payload["loan_purpose"] == ""
    assert payload["credit_approval_opinion"] == ""


@pytest.mark.parametrize(
    ("fixture_name", "issue_name", "problem_label"),
    [
        ("missing_label.docx", "missing", "授信审批意见"),
        ("duplicate_label.docx", "duplicate", "企业名称"),
        ("unrecognized_label.docx", "unrecognized", "企业全称"),
    ],
)
def test_invalid_labels_report_issues_without_creating_case(
    fixture_name: str,
    issue_name: str,
    problem_label: str,
) -> None:
    session = MagicMock()

    with pytest.raises(NationalEconomyTemplateError) as error:
        create_case_from_template(session, _fixture_bytes(fixture_name), fixture_name)

    assert problem_label in getattr(error.value.issues, issue_name)
    session.add.assert_not_called()
    session.commit.assert_not_called()
    session.refresh.assert_not_called()


def test_template_download_returns_original_docx_bytes(tmp_path: Path) -> None:
    template_path = tmp_path / "template.docx"
    original_bytes = _fixture_bytes("valid.docx")
    template_path.write_bytes(original_bytes)
    settings = Settings(
        _env_file=None,
        national_economy_template_path=template_path,
    )

    assert read_template_bytes(settings) == original_bytes
