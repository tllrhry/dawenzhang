def format_industry_display_code(
    major_code: str | None,
    industry_code: str | None,
    middle_code: str | None = None,
) -> str | None:
    if not industry_code:
        return industry_code
    if len(industry_code) == 2:
        return major_code or industry_code
    if len(industry_code) == 3:
        return f"{major_code}-{middle_code or industry_code}" if major_code else (middle_code or industry_code)
    if major_code and middle_code:
        return f"{major_code}-{middle_code}-{major_code[:1]}{industry_code}"
    if major_code:
        return f"{major_code}-{major_code[:1]}{industry_code}"
    return industry_code
