import pytest

from app.services.national_economy_result_presentation import (
    format_industry_display_code,
)


@pytest.mark.parametrize(
    ("major_code", "four_digit", "expected"),
    [
        ("Q85", "8514", "Q85-Q8514"),
        ("F51", "5176", "F51-F5176"),
        (None, "5176", "5176"),
        ("", "5176", "5176"),
        ("Q85", None, None),
        ("Q85", "", ""),
        (None, None, None),
    ],
)
def test_format_industry_display_code(
    major_code: str | None,
    four_digit: str | None,
    expected: str | None,
) -> None:
    assert format_industry_display_code(major_code, four_digit) == expected
