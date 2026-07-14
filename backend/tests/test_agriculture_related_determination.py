from types import SimpleNamespace

import httpx
import pytest

from app.core.config import Settings
from app.services.agriculture_related_determination import (
    AgricultureRelatedAIError,
    determine_category_four,
    determine_category_two,
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


def _ai_settings() -> Settings:
    return Settings(_env_file=None, deepseek_api_key="test-key", deepseek_base_url="https://deepseek.example/v1")


def _ai_client(output: object, calls: list[httpx.Request] | None = None) -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        if calls is not None:
            calls.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": __import__("json").dumps(output, ensure_ascii=False)}}]})
    return httpx.Client(transport=httpx.MockTransport(handler), base_url=_ai_settings().deepseek_base_url)


@pytest.mark.parametrize("address", ["江苏省南京市某乡某村", "江苏省某镇工业园"])
def test_category_two_rural_rules_do_not_call_ai(address: str) -> None:
    result = determine_category_two({"registered_address": address}, _ai_settings())
    assert result["result"] == "matched"
    assert result["method"] == "rule"


@pytest.mark.parametrize("address", ["江苏省南京市鼓楼区", "江苏省某县城关镇"])
def test_category_two_urban_rules_do_not_call_ai(address: str) -> None:
    result = determine_category_two({"registered_address": address}, _ai_settings())
    assert result["result"] == "not_matched"
    assert result["method"] == "rule"


def test_category_two_prefers_registration_and_falls_back_to_business_address() -> None:
    result = determine_category_two({"registered_address": "南京市鼓楼区", "actual_business_address": "某乡某村"}, _ai_settings())
    assert result["result"] == "not_matched"
    fallback = determine_category_two({"registered_address": "", "actual_business_address": "某乡某村"}, _ai_settings())
    assert fallback["result"] == "matched"
    assert "实际经营地址" in fallback["basis"]


def test_category_two_both_addresses_empty_needs_review_without_ai() -> None:
    result = determine_category_two({}, _ai_settings())
    assert result["result"] == "needs_review"
    assert result["method"] == "rule"


def test_category_two_ai_and_request_contract() -> None:
    calls: list[httpx.Request] = []
    with _ai_client({"label": "农村地区", "basis": "地址为江苏省南京市玄武街道"}, calls) as client:
        result = determine_category_two({"registered_address": "江苏省南京市玄武街道"}, _ai_settings(), client)
    body = calls[0].read()
    assert result["result"] == "matched"
    assert result["method"] == "ai"
    assert b'"temperature":0' in body
    assert b'"response_format":{"type":"json_object"}' in body


def test_category_two_ai_can_return_needs_review() -> None:
    with _ai_client({"label": "无法判定", "basis": "地址为未知路"}) as client:
        result = determine_category_two({"registered_address": "未知路"}, _ai_settings(), client)
    assert result["result"] == "needs_review"


def test_category_two_ai_retries_network_errors_with_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    attempts = 0
    delays: list[float] = []
    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise httpx.ReadTimeout("temporary")
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"label":"城区","basis":"地址为未知路"}'}}]})
    monkeypatch.setattr("app.services.agriculture_related_determination.time.sleep", delays.append)
    with httpx.Client(transport=httpx.MockTransport(handler), base_url=_ai_settings().deepseek_base_url) as client:
        result = determine_category_two({"registered_address": "未知路"}, _ai_settings(), client)
    assert result["result"] == "not_matched"
    assert attempts == 3 and delays == [0.5, 1.0]


def test_category_two_rejects_ungrounded_ai_without_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0
    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"label":"城区","basis":"模型认为这是城区"}'}}]})
    monkeypatch.setattr("app.services.agriculture_related_determination.time.sleep", lambda _: pytest.fail("must not retry"))
    with httpx.Client(transport=httpx.MockTransport(handler), base_url=_ai_settings().deepseek_base_url) as client, pytest.raises(AgricultureRelatedAIError):
        determine_category_two({"registered_address": "未知路"}, _ai_settings(), client)
    assert calls == 1


@pytest.mark.parametrize("text", ["粮食深加工", "乡村道路建设", "冷链仓储", "乡村文旅项目"])
def test_category_four_rule_matches_four_subclasses(text: str) -> None:
    result = determine_category_four({"loan_purpose": text}, {"result": "not_matched"}, _ai_settings())
    assert result["result"] == "matched"
    assert result["method"] == "rule"


def test_category_four_does_not_call_ai_when_category_two_is_not_urban(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("AI must not be called")
    monkeypatch.setattr("app.services.agriculture_related_determination._call_agriculture_ai", fail)
    assert determine_category_four({"loan_purpose": "任意用途"}, {"result": "matched"}, _ai_settings())["result"] == "not_applicable"
    assert determine_category_four({"loan_purpose": "任意用途"}, {"result": "needs_review"}, _ai_settings())["result"] == "needs_review"


def test_category_four_ai_exclusion_and_grounded_basis() -> None:
    with _ai_client({"label": "均不属于", "basis": "贷款用途为办公设备采购"}) as client:
        result = determine_category_four({"loan_purpose": "办公设备采购"}, {"result": "not_matched"}, _ai_settings(), client)
    assert result["result"] == "not_matched"


def test_category_four_ai_can_match_or_request_review() -> None:
    with _ai_client({"label": "农村流通", "basis": "贷款用途为农资采购"}) as client:
        matched = determine_category_four({"loan_purpose": "农资采购"}, {"result": "not_matched"}, _ai_settings(), client)
    with _ai_client({"label": "无法判定", "basis": "贷款用途为办公设备采购"}) as client:
        review = determine_category_four({"loan_purpose": "办公设备采购"}, {"result": "not_matched"}, _ai_settings(), client)
    assert matched["result"] == "matched"
    assert review["result"] == "needs_review"
