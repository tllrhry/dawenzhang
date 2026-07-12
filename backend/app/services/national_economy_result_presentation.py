def format_industry_display_code(
    major_code: str | None,
    four_digit: str | None,
) -> str | None:
    if not major_code or not four_digit:
        return four_digit
    return f"{major_code}-{major_code[:1]}{four_digit}"
