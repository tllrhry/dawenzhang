import pytest

from app.services.national_economy_result_presentation import (
    format_industry_display_code,
)


@pytest.mark.parametrize(
    ("major_code", "industry_code", "middle_code", "expected"),
    [
        ("Q85", "8514", "Q851", "Q85-Q851-Q8514"),
        ("F51", "5176", "F517", "F51-F517-F5176"),
        ("A01", "011", "A011", "A01-A011"),
        ("A01", "01", None, "A01"),
        ("Q85", "8514", None, "Q85-Q8514"),
        (None, "5176", None, "5176"),
        ("Q85", None, None, None),
        ("Q85", "", None, ""),
        (None, None, None, None),
    ],
)
def test_format_industry_display_code(
    major_code: str | None,
    industry_code: str | None,
    middle_code: str | None,
    expected: str | None,
) -> None:
    assert format_industry_display_code(major_code, industry_code, middle_code) == expected
