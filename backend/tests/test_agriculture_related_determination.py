from types import SimpleNamespace

import pytest

from app.services.agriculture_related_determination import (
    determine_agriculture_industry_loan_category,
    determine_farmer_loan_category,
)


FARMER_FIELDS = (
    "farmer_long_term_town_resident",
    "farmer_town_village_resident",
    "farmer_nonlocal_resident_over_one_year",
    "farmer_state_farm_employee_or_rural_individual_business",
)


def test_farmer_category_matches_single_identity_field() -> None:
    payload = {key: "否" for key in FARMER_FIELDS}
    payload[FARMER_FIELDS[1]] = "是"

    result = determine_farmer_loan_category(payload)

    assert result["category"] == 1
    assert result["category_name"] == "农户贷款"
    assert result["result"] == "matched"
    assert result["method"] == "rule"
    assert result["evidence_refs"] == [
        {"type": "field", "field_key": FARMER_FIELDS[1], "raw_value": "是"}
    ]


def test_farmer_category_keeps_all_matching_fields() -> None:
    payload = {key: "是" for key in FARMER_FIELDS}

    result = determine_farmer_loan_category(payload)

    assert result["result"] == "matched"
    assert [ref["field_key"] for ref in result["evidence_refs"]] == list(FARMER_FIELDS)


@pytest.mark.parametrize("value", [None, "", "否", "no"])
def test_farmer_category_does_not_review_non_affirmative_values(value: object) -> None:
    result = determine_farmer_loan_category({key: value for key in FARMER_FIELDS})

    assert result["result"] == "not_matched"
    assert "复核" not in result["basis"]
    assert result["evidence_refs"] == []


def _stage_a(**overrides: object) -> SimpleNamespace:
    values = {
        "industry_category_name": "制造业",
        "industry_code": "3742",
        "industry_major_code": "C37",
        "industry_middle_code": "C374",
        "industry_middle_name": "医药制造",
        "industry_name": "生物药品制造",
        "loan_industry_category_name": None,
        "loan_industry_code": None,
        "loan_industry_major_code": None,
        "loan_industry_middle_code": None,
        "loan_industry_middle_name": None,
        "loan_industry_name": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_category_three_enterprise_match_does_not_require_loan_match() -> None:
    result = determine_agriculture_industry_loan_category(
        _stage_a(
            industry_category_name="农、林、牧、渔业",
            industry_code="0111",
            industry_major_code="A01",
            industry_middle_code="A011",
            industry_middle_name="谷物种植",
            industry_name="稻谷种植",
            loan_industry_category_name=None,
            loan_industry_code=None,
        )
    )

    assert result["result"] == "matched"
    assert "企业结论门类" in result["basis"]
    assert result["evidence_refs"][0]["field_key"] == "industry_category_name"


def test_category_three_keeps_both_sources_when_both_match() -> None:
    result = determine_agriculture_industry_loan_category(
        _stage_a(
            industry_category_name="农、林、牧、渔业",
            industry_code="01",
            industry_major_code="A01",
            industry_name="农业",
            loan_industry_category_name="农、林、牧、渔业",
            loan_industry_code="011",
            loan_industry_major_code="A01",
            loan_industry_middle_code="A011",
            loan_industry_middle_name="谷物种植",
            loan_industry_name="谷物种植",
        )
    )

    assert result["result"] == "matched"
    assert [ref["field_key"] for ref in result["evidence_refs"]] == [
        "industry_category_name",
        "loan_industry_category_name",
    ]
    assert "A01" in result["basis"]
    assert "A01-A011" in result["basis"]


@pytest.mark.parametrize(
    ("code", "middle_code", "expected"),
    [("0111", "A011", "A01-A011-A0111"), ("011", "A011", "A01-A011"), ("01", None, "A01")],
)
def test_category_three_uses_actual_code_granularity(
    code: str, middle_code: str | None, expected: str
) -> None:
    result = determine_agriculture_industry_loan_category(
        _stage_a(
            loan_industry_category_name="农、林、牧、渔业",
            loan_industry_code=code,
            loan_industry_major_code="A01",
            loan_industry_middle_code=middle_code,
            loan_industry_middle_name="谷物种植" if middle_code else None,
            loan_industry_name="稻谷种植" if len(code) == 4 else None,
        )
    )

    assert expected in result["basis"]


def test_category_three_not_matched_when_both_sources_are_non_agriculture() -> None:
    result = determine_agriculture_industry_loan_category(_stage_a())

    assert result["result"] == "not_matched"
    assert result["evidence_refs"] == []
