import pytest

from app.services.inclusive_finance_determination import (
    determine_inclusive_finance,
    extract_approved_credit_amounts_wan,
    parse_credit_amount_wan,
    parse_count,
    resolve_credit_amount,
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
        "credit_approval_opinion": "",
        "registered_address": "",
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


def test_farmer_recognition_field_fills_missing_entity_type() -> None:
    result = determine_inclusive_finance(
        _payload(
            entity_type="",
            farmer_town_village_resident="是",
            credit_amount="500万元",
        ),
        _stage_a(),
    )

    assert result["borrower_type"] == "farmer"
    assert result["inclusive_category"] == "农户经营性贷款"


def test_farmer_registration_address_is_used_as_supporting_evidence() -> None:
    result = determine_inclusive_finance(
        _payload(
            entity_type="农户",
            credit_amount="500万元",
            registered_address="江苏省某乡某村",
        ),
        _stage_a(),
    )

    assert result["status"] == "completed"
    assert "可作为农户身份的地址佐证" in result["basis"]
    assert result["determination"]["farmer_registration_address_support"]
    assert {ref["field_key"] for ref in result["evidence_refs"] if ref["type"] == "field"} >= {
        "registered_address"
    }


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
    ("overrides", "expected_reason"),
    (
        (
            {
                "entity_type": "农户",
                "credit_amount": "600万元",
                "credit_variety": "",
                "loan_purpose": "一般用途",
            },
            "超过500万元上限",
        ),
        (
            {
                "entity_type": "个体工商户",
                "credit_amount": "",
                "credit_variety": "个人消费贷款",
                "loan_purpose": "购买家电",
            },
            "不属于经营性贷款",
        ),
        (
            {
                "entity_type": "企业",
                "annual_revenue": "20000万元",
                "employee_count": "1",
                "credit_amount": "",
                "credit_variety": "",
                "loan_purpose": "一般用途",
            },
            "不属于小微企业",
        ),
    ),
)
def test_definite_exclusion_takes_priority_over_unresolved_fields(
    overrides: dict[str, object], expected_reason: str
) -> None:
    result = determine_inclusive_finance(_payload(**overrides), _stage_a())

    assert result["status"] == "not_applicable"
    assert result["qualifies"] is False
    assert expected_reason in result["basis"]


@pytest.mark.parametrize(
    ("payload", "expected_source"),
    (
        ({"credit_variety": "流贷", "loan_purpose": "购买种子"}, "credit_variety"),
        (
            {
                "credit_variety": "一般贷款",
                "loan_purpose": "购买种子",
                "credit_approval_opinion": "本笔为流动资金贷款，用于生产农资",
            },
            "credit_approval_opinion",
        ),
    ),
)
def test_operating_loan_uses_all_structured_loan_evidence(
    payload: dict[str, object], expected_source: str
) -> None:
    result = determine_inclusive_finance(
        _payload(entity_type="农户", credit_amount="100万元", **payload), _stage_a()
    )

    assert result["status"] == "completed"
    assert result["inclusive_category"] == "农户经营性贷款"
    assert result["determination"]["operating_determination_source"] == expected_source


def test_conflicting_operating_evidence_needs_review() -> None:
    result = determine_inclusive_finance(
        _payload(
            entity_type="农户",
            credit_amount="500万元",
            credit_variety="个人消费贷款",
            loan_purpose="采购原材料用于生产",
        ),
        _stage_a(),
    )

    assert result["status"] == "needs_review"
    assert result["is_operating_loan"] is None


def test_medium_software_enterprise_is_not_inclusive_after_operating_loan_is_confirmed() -> None:
    result = determine_inclusive_finance(
        _payload(
            entity_type="企业",
            annual_revenue="5000万",
            employee_count="2025",
            total_assets="10000万",
            credit_amount="900万",
            credit_variety="流贷",
        ),
        _stage_a("6510", "I65"),
    )

    assert result["computed_size"] == "中型"
    assert result["status"] == "not_applicable"
    assert "不属于小微企业" in result["basis"]


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    (("1亿", 10000.0), ("1,000万元", 1000.0), ("1000万", 1000.0), ("500", 500.0)),
)
def test_credit_amount_parser_uses_wan_and_accepts_billion_and_thousands_separators(
    raw_value: str, expected: float
) -> None:
    assert parse_credit_amount_wan(raw_value) == expected


@pytest.mark.parametrize(
    ("opinion", "expected"),
    (
        ("经审查，同意授信额度人民币1,000万元。", (1000.0,)),
        ("申请授信1200万元，批复同意800万元。", (800.0,)),
        ("申请金额1000万元；核定授信额度500万元。", (500.0,)),
        ("授信额度0.1亿元，用于生产经营。", (1000.0,)),
        ("申请授信额度1000万元，期限12个月。", ()),
        ("批复额度金额待定，期限12个月。", ()),
    ),
)
def test_extract_approved_credit_amounts_ignores_application_amounts_and_invalid_text(
    opinion: str, expected: tuple[float, ...]
) -> None:
    assert extract_approved_credit_amounts_wan(opinion) == expected


def test_extract_approved_credit_amounts_preserves_distinct_multiple_values() -> None:
    opinion = "批复流动资金贷款300万元；核定固定资产贷款200万元。"

    assert extract_approved_credit_amounts_wan(opinion) == (300.0, 200.0)


@pytest.mark.parametrize(
    ("structured", "opinion", "amount", "source", "consistent"),
    (
        ("800万元", "同意授信额度800万元", 800.0, "structured_and_approval_consistent", True),
        ("800万元", "同意本笔经营性贷款", 800.0, "structured", None),
        ("", "批复同意授信额度500万元", 500.0, "approval_opinion", None),
    ),
)
def test_credit_amount_resolution_records_the_adopted_value_and_source(
    structured: str,
    opinion: str,
    amount: float,
    source: str,
    consistent: bool | None,
) -> None:
    resolution = resolve_credit_amount(structured, opinion)

    assert resolution["adopted_amount_wan"] == amount
    assert resolution["source"] == source
    assert resolution["consistent"] is consistent


def test_conflicting_credit_amount_sources_need_review_and_preserve_both_values() -> None:
    result = determine_inclusive_finance(
        _payload(
            credit_amount="1000万元",
            credit_approval_opinion="批复同意授信额度800万元，用于生产经营",
        ),
        _stage_a(),
    )

    assert result["status"] == "needs_review"
    assert result["credit_amount_wan"] is None
    assert result["determination"]["structured_credit_amount_wan"] == 1000.0
    assert result["determination"]["approval_credit_amounts_wan"] == [800.0]
    assert result["determination"]["credit_amount_conflict"] is True
    assert result["anomalies"][0]["type"] == "credit_amount_conflict"


def test_multiple_distinct_approved_amounts_need_review() -> None:
    result = determine_inclusive_finance(
        _payload(
            credit_amount="",
            credit_approval_opinion="批复流动资金贷款300万元；核定固定资产贷款200万元。",
        ),
        _stage_a(),
    )

    assert result["status"] == "needs_review"
    assert "多个不同批复额度" in result["basis"]
    assert result["anomalies"][0]["type"] == "multiple_approved_credit_amounts"


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    (("14 人，其中研发技术人员 4 人", 14.0), ("20名员工", 20.0)),
)
def test_employee_count_parser_accepts_a_total_followed_by_explanatory_text(
    raw_value: str, expected: float
) -> None:
    assert parse_count(raw_value) == expected


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
    assert any(item["type"] == "missing_sizing_metrics" for item in result["anomalies"])


def test_enterprise_with_missing_stage_a_industry_records_a_structured_anomaly() -> None:
    result = determine_inclusive_finance(_payload(), _stage_a("", ""))

    assert result["status"] == "needs_review"
    assert "Stage A 企业行业信息" in result["basis"]
    assert result["anomalies"][0]["type"] == "missing_sizing_metrics"
    assert result["anomalies"][0]["missing_metrics"] == ["Stage A 企业行业信息"]


def test_address_alone_does_not_change_a_non_farmer_borrower_type() -> None:
    result = determine_inclusive_finance(
        _payload(registered_address="江苏省某乡某村"), _stage_a()
    )

    assert result["borrower_type"] == "enterprise"
    assert result["determination"]["farmer_matched_conditions"] == []
    assert "可作为农户身份的地址佐证" in result["determination"][
        "farmer_registration_address_support"
    ]


@pytest.mark.parametrize("field", tuple(_payload())[-4:])
def test_each_farmer_identity_condition_fills_missing_entity_type(field: str) -> None:
    result = determine_inclusive_finance(
        _payload(**{field: "是", "entity_type": "", "credit_amount": "500万元"}),
        _stage_a(),
    )

    assert result["status"] == "completed"
    assert result["borrower_type"] == "farmer"
    assert len(result["determination"]["farmer_matched_conditions"]) == 1


@pytest.mark.parametrize(
    "entity_type",
    ("企业", "个体工商户", "小微企业主"),
)
def test_farmer_identity_conditions_override_non_farmer_entity_type(
    entity_type: str,
) -> None:
    result = determine_inclusive_finance(
        _payload(
            entity_type=entity_type,
            farmer_long_term_town_resident="是",
            farmer_town_village_resident="是",
            farmer_state_farm_employee_or_rural_individual_business="是",
            credit_amount="600万元",
        ),
        _stage_a(),
    )

    assert result["status"] == "not_applicable"
    assert result["borrower_type"] == "farmer"
    assert result["inclusive_category"] is None
    assert result["qualifies"] is False
    assert "超过500万元上限" in result["basis"]
    assert "农户条件命中" in result["determination"]["borrower_type_basis"]


def test_identical_input_produces_an_identical_deterministic_decision() -> None:
    payload = _payload(
        credit_amount="500万元",
        credit_approval_opinion="批复同意授信额度500万元，用于生产经营",
    )

    assert determine_inclusive_finance(payload, _stage_a()) == determine_inclusive_finance(
        payload, _stage_a()
    )


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
