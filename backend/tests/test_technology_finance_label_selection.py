import json
from types import SimpleNamespace

import httpx
import pytest

from app.core.config import Settings
from app.services.technology_finance_label_selection import (
    TechnologyFinanceLabelSelectionError,
    select_most_matching_technology_finance_label,
)
from app.services.technology_finance_mapping_query import TechnologyFinanceMappingLabel


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        deepseek_api_key="test-deepseek-key",
        deepseek_base_url="https://deepseek.example/v1",
        deepseek_model="deepseek-test",
        deepseek_timeout_seconds=17,
        http_connect_timeout_seconds=3,
    )


def _stage_a(*, loan_basis: str = "贷款用于国家重大新药创制专项项目建设。") -> SimpleNamespace:
    return SimpleNamespace(
        id=41,
        industry_code="2710",
        industry_major_code="C27",
        industry_name="化学药品原料药制造",
        rationale="企业主营化学药品原料药制造。",
        loan_industry_code="2710",
        loan_industry_major_code="C27",
        loan_industry_name="化学药品原料药制造",
        loan_matching_basis=loan_basis,
    )


def _input_payload() -> dict[str, str]:
    return {
        "enterprise_name": "南京示例科技有限公司",
        "main_business": "创新药原料研发和制造",
        "loan_purpose": "用于国家重大新药创制专项建设",
        "trade_goods_services": "原料药生产线建设",
    }


def _label(
    *,
    subject: str,
    tier1: str,
    source_row: int,
    code: str = "2710",
    name: str = "化学药品原料药制造",
) -> TechnologyFinanceMappingLabel:
    return TechnologyFinanceMappingLabel(
        mapping_version_id=7,
        scenario_id="technology_finance",
        neic_code=code,
        code_level=len(code),
        neic_name=name,
        subject=subject,
        tier1=tier1,
        tier2=None,
        tier3=None,
        tier4=None,
        source_row=source_row,
    )


def _candidates() -> tuple[TechnologyFinanceMappingLabel, ...]:
    return (
        _label(subject="高技术产业（制造业）", tier1="医药制造业", source_row=11),
        _label(subject="国家科技重大项目", tier1="重大新药创制", source_row=22),
    )


def _client(model_output: object, status_code: int = 200) -> httpx.Client:
    def handler(_request: httpx.Request) -> httpx.Response:
        if status_code != 200:
            return httpx.Response(status_code, json={"error": "unavailable"})
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": json.dumps(model_output, ensure_ascii=False)}}
                ]
            },
        )

    return httpx.Client(
        transport=httpx.MockTransport(handler), base_url=_settings().deepseek_base_url
    )


def test_single_candidate_returns_without_any_model_call() -> None:
    only = _label(subject="高技术产业（制造业）", tier1="医药制造业", source_row=11)

    def handler(_request: httpx.Request) -> httpx.Response:
        raise AssertionError("must not call DeepSeek for a single candidate")

    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        selected = select_most_matching_technology_finance_label(
            _input_payload(), _stage_a(), (only,), _settings(), client=client
        )
    assert selected is only


def test_selects_the_model_chosen_candidate() -> None:
    candidates = _candidates()
    output = {
        "selected_source_row": 22,
        "selection_basis": "贷款用途明确指向国家重大新药创制专项，优先该主题。",
    }
    with _client(output) as client:
        selected = select_most_matching_technology_finance_label(
            _input_payload(), _stage_a(), candidates, _settings(), client=client
        )
    assert selected is candidates[1]


def test_rejects_a_source_row_absent_from_candidates() -> None:
    candidates = _candidates()
    output = {"selected_source_row": 99, "selection_basis": "选择理由。"}
    with _client(output) as client, pytest.raises(TechnologyFinanceLabelSelectionError):
        select_most_matching_technology_finance_label(
            _input_payload(), _stage_a(), candidates, _settings(), client=client
        )


def test_rejects_empty_selection_basis() -> None:
    candidates = _candidates()
    output = {"selected_source_row": 11, "selection_basis": "   "}
    with _client(output) as client, pytest.raises(TechnologyFinanceLabelSelectionError):
        select_most_matching_technology_finance_label(
            _input_payload(), _stage_a(), candidates, _settings(), client=client
        )


def test_rejects_unexpected_root_fields() -> None:
    candidates = _candidates()
    output = {
        "selected_source_row": 11,
        "selection_basis": "选择理由。",
        "extra": "not allowed",
    }
    with _client(output) as client, pytest.raises(TechnologyFinanceLabelSelectionError):
        select_most_matching_technology_finance_label(
            _input_payload(), _stage_a(), candidates, _settings(), client=client
        )


def test_rejects_http_error() -> None:
    candidates = _candidates()
    with _client({}, status_code=500) as client, pytest.raises(
        TechnologyFinanceLabelSelectionError
    ):
        select_most_matching_technology_finance_label(
            _input_payload(), _stage_a(), candidates, _settings(), client=client
        )


def test_requires_api_key() -> None:
    candidates = _candidates()
    settings = Settings(_env_file=None, deepseek_api_key=None)
    with pytest.raises(TechnologyFinanceLabelSelectionError):
        select_most_matching_technology_finance_label(
            _input_payload(), _stage_a(), candidates, settings
        )


def test_raises_when_no_candidates_given() -> None:
    with pytest.raises(TechnologyFinanceLabelSelectionError):
        select_most_matching_technology_finance_label(
            _input_payload(), _stage_a(), (), _settings()
        )


def test_retries_transient_tls_timeout_before_selecting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    candidates = _candidates()
    attempts = 0
    delays: list[float] = []
    monkeypatch.setattr(
        "app.services.technology_finance_label_selection.time.sleep",
        delays.append,
    )

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise httpx.ConnectTimeout("temporary TLS handshake timeout")
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "selected_source_row": 22,
                                    "selection_basis": "第三次连接成功并选中重大新药创制主题。",
                                },
                                ensure_ascii=False,
                            )
                        }
                    }
                ]
            },
        )

    with httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url=_settings().deepseek_base_url,
    ) as client:
        selected = select_most_matching_technology_finance_label(
            _input_payload(), _stage_a(), candidates, _settings(), client=client
        )

    assert attempts == 3
    assert delays == [0.5, 1.0]
    assert selected is candidates[1]
