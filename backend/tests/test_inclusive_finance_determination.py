import pytest

from app.services.inclusive_finance_determination import (
    determine_inclusive_finance,
    parse_credit_amount_wan,
)


def _payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "entity_type": "企业",
        "enterprise_scale_type": "小型",
        "total_assets": "300万元",
        "annual_revenue": "300万元",
        "employee_count": "20",
        "credit_amount": "1000万元",
        "credit_variety": "流动资金贷款",
        "loan_purpose": "采购原材料用于生产经营",
        "farmer_long_term_town_resident": "否",
        "farmer_town_village_resident": "否",
        "farmer_nonlocal_resident_over_one_year": "否",
        "farmer_state_farm_employee_or_rural_individual_business": "否",
    }
    payload.update(overrides)
    return payload


def _stage_a(code: str = "0111", major: str = "A01") -> dict[str, str]:
    return {"industry_code": code, "industry_major_code": major}


@pytest.mark.parametrize(
    ("entity_type", "credit_amount", "expected_type", "expected_category"),
    (
        ("农户", "500万元", "farmer", "农户经营性贷款"),
        ("个体工商户", "1000万元", "individual_business", "个体工商户经营性贷款"),
        ("小微企业主", "1000万元", "small_micro_owner", "小微企业主经营性贷款"),
        ("企业", "1000万元", "enterprise", "小微企业贷款"),
    ),
)
def test_four_borrower_types_qualify_at_their_credit_boundaries(
    entity_type: str, credit_amount: str, expected_type: str, expected_category: str
) -> None:
    result = determine_inclusive_finance(
        _payload(entity_type=entity_type, credit_amount=credit_amount), _stage_a()
    )

    assert result["status"] == "completed"
    assert result["borrower_type"] == expected_type
    assert result["inclusive_category"] == expected_category
    assert result["qualifies"] is True


def test_farmer_recognition_field_overrides_entity_type() -> None:
    result = determine_inclusive_finance(
        _payload(farmer_town_village_resident="是", credit_amount="500万元"), _stage_a()
    )

    assert result["borrower_type"] == "farmer"
    assert result["inclusive_category"] == "农户经营性贷款"


def test_non_operating_loan_is_not_applicable() -> None:
    result = determine_inclusive_finance(
        _payload(entity_type="个体工商户", credit_variety="个人消费贷款", loan_purpose="购买家电"),
        _stage_a(),
    )

    assert result["status"] == "not_applicable"
    assert result["is_operating_loan"] is False
    assert "不属于经营性贷款" in result["basis"]


def test_unknown_operating_nature_needs_review() -> None:
    result = determine_inclusive_finance(
        _payload(entity_type="个体工商户", credit_variety="", loan_purpose="一般用途"),
        _stage_a(),
    )

    assert result["status"] == "needs_review"
    assert "经营性贷款判定" in result["basis"]


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    (("1亿", 10000.0), ("1,000万元", 1000.0), ("1000万", 1000.0), ("500", 500.0)),
)
def test_credit_amount_parser_uses_wan_and_accepts_billion_and_thousands_separators(
    raw_value: str, expected: float
) -> None:
    assert parse_credit_amount_wan(raw_value) == expected


def test_unparseable_credit_amount_needs_review() -> None:
    result = determine_inclusive_finance(_payload(credit_amount="金额待定"), _stage_a())

    assert result["status"] == "needs_review"
    assert "本次授信额度" in result["basis"]


def test_computed_size_wins_and_records_a_size_mismatch() -> None:
    result = determine_inclusive_finance(
        _payload(enterprise_scale_type="中型", annual_revenue="300万元", employee_count="20"),
        _stage_a(),
    )

    assert result["status"] == "completed"
    assert result["computed_size"] == "小型"
    assert result["determination"]["size_consistent"] is False
    assert result["anomalies"][0]["type"] == "size_mismatch"


def test_enterprise_with_missing_sizing_input_needs_review() -> None:
    result = determine_inclusive_finance(_payload(total_assets=""), _stage_a("4810", "E48"))

    assert result["status"] == "needs_review"
    assert "总资产" in result["basis"]


@pytest.mark.parametrize(
    ("payload", "stage_a", "reason"),
    (
        (
            {"entity_type": "农户", "credit_amount": "501万元"},
            _stage_a(),
            "超过500万元上限",
        ),
        (
            {"entity_type": "个体工商户", "credit_amount": "1001万元"},
            _stage_a(),
            "超过1000万元上限",
        ),
        (
            {"annual_revenue": "20000万元", "employee_count": "1"},
            _stage_a(),
            "计算企业规模为大型",
        ),
    ),
)
def test_not_applicable_has_a_specific_reason(
    payload: dict[str, object], stage_a: dict[str, str], reason: str
) -> None:
    result = determine_inclusive_finance(_payload(**payload), stage_a)

    assert result["status"] == "not_applicable"
    assert reason in result["basis"]
