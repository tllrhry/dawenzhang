import json

import httpx
import pytest

from app.core.config import Settings
from app.services.national_economy_classification import (
    NationalEconomyClassificationError,
    classify_national_economy,
)
from app.services.national_economy_retrieval import EvidenceSnapshot, RecallHit


def _settings() -> Settings:
    return Settings(
        database_url="postgresql+psycopg://user:pass@localhost/test",
        deepseek_api_key="test-key",
    )


def _candidate(code: str, name: str, text: str) -> EvidenceSnapshot:
    return EvidenceSnapshot(
        industry_code=code,
        industry_name=name,
        vector_score=0.8,
        rerank_score=0.9,
        hits=(
            RecallHit(
                industry_code=code,
                industry_name=name,
                text=text,
                chunk_type="definition",
                source_row=2,
                distance=0.2,
            ),
        ),
    )


def _client(model_output: object, status_code: int = 200) -> httpx.Client:
    def handler(_request: httpx.Request) -> httpx.Response:
        if status_code != 200:
            return httpx.Response(status_code, json={"error": "unavailable"})
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(model_output)}}]},
        )

    return httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url=_settings().deepseek_base_url,
    )


def test_classification_accepts_exact_candidate_pair_and_required_fields() -> None:
    candidates = (
        _candidate("0111", "稻谷种植", "稻谷种植的定义"),
        _candidate("0112", "小麦种植", "小麦种植的定义"),
    )
    output = {
        "no_match": False,
        "industry_code": "0111",
        "industry_name": "稻谷种植",
        "confidence": 87.5,
        "matching_basis": "主营水稻种植，与候选定义一致。",
        "summary": "企业归入稻谷种植。",
    }

    with _client(output) as client:
        result = classify_national_economy(
            {"主营产品/服务": "水稻种植"},
            candidates,
            _settings(),
            objection={"补充说明": "收入主要来自水稻"},
            client=client,
        )

    assert result.status == "completed"
    assert result.industry_code == "0111"
    assert result.industry_name == "稻谷种植"
    assert result.confidence == 87.5
    assert result.matching_basis
    assert result.summary
    assert result.objection == {"补充说明": "收入主要来自水稻"}
    assert result.candidate_snapshot[0]["definition_and_hits"][0]["text"] == "稻谷种植的定义"


def test_request_only_sends_enterprise_objection_and_candidate_evidence() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {
                                    "no_match": True,
                                    "reason": "现有候选均未覆盖企业活动。",
                                }
                            )
                        }
                    }
                ]
            },
        )

    settings = _settings()
    with httpx.Client(
        transport=httpx.MockTransport(handler), base_url=settings.deepseek_base_url
    ) as client:
        classify_national_economy(
            {"企业名称": "测试企业"},
            (_candidate("0111", "稻谷种植", "目录命中片段"),),
            settings,
            objection={"reason": "经营内容已变化"},
            client=client,
        )

    user_content = json.loads(captured["messages"][1]["content"])
    assert captured["model"] == settings.deepseek_model
    assert captured["response_format"] == {"type": "json_object"}
    assert user_content["enterprise_input"] == {"企业名称": "测试企业"}
    assert user_content["objection"] == {"reason": "经营内容已变化"}
    assert user_content["candidates"][0]["industry_code"] == "0111"
    assert "目录命中片段" in str(user_content["candidates"])


def test_no_match_returns_needs_review_without_forced_conclusion() -> None:
    output = {"no_match": True, "reason": "候选均不覆盖软件开发活动。"}

    with _client(output) as client:
        result = classify_national_economy(
            {"主营产品/服务": "软件开发"},
            (_candidate("0111", "稻谷种植", "农业定义"),),
            _settings(),
            client=client,
        )

    assert result.status == "needs_review"
    assert result.industry_code is None
    assert result.industry_name is None
    assert result.confidence is None
    assert result.matching_basis == output["reason"]
    assert result.candidate_snapshot
    assert result.model_output == output


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"industry_code": "9999"}, "exactly match"),
        ({"industry_name": "小麦种植"}, "exactly match"),
        ({"confidence": -1}, "between 0 and 100"),
        ({"confidence": 101}, "between 0 and 100"),
        ({"confidence": "90"}, "must be a number"),
        ({"matching_basis": ""}, "matching_basis must be non-empty"),
        ({"summary": None}, "summary must be non-empty"),
    ],
)
def test_invalid_selected_result_fails_without_conclusion(overrides, message) -> None:
    output = {
        "no_match": False,
        "industry_code": "0111",
        "industry_name": "稻谷种植",
        "confidence": 90,
        "matching_basis": "匹配定义",
        "summary": "分类总结",
    }
    output.update(overrides)

    with _client(output) as client:
        with pytest.raises(NationalEconomyClassificationError, match=message):
            classify_national_economy(
                {"主营产品/服务": "水稻"},
                (
                    _candidate("0111", "稻谷种植", "定义"),
                    _candidate("0112", "小麦种植", "定义"),
                ),
                _settings(),
                client=client,
            )


@pytest.mark.parametrize(
    "response_content",
    [
        "not-json",
        json.dumps({"reason": "missing no_match"}),
        json.dumps({"no_match": True, "reason": ""}),
    ],
)
def test_malformed_model_output_fails(response_content: str) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, json={"choices": [{"message": {"content": response_content}}]}
        )

    with httpx.Client(
        transport=httpx.MockTransport(handler), base_url=_settings().deepseek_base_url
    ) as client:
        with pytest.raises(NationalEconomyClassificationError):
            classify_national_economy(
                {"主营产品/服务": "水稻"},
                (_candidate("0111", "稻谷种植", "定义"),),
                _settings(),
                client=client,
            )


def test_http_failure_is_reported_as_classification_failure() -> None:
    with _client({}, status_code=503) as client:
        with pytest.raises(NationalEconomyClassificationError, match="503"):
            classify_national_economy(
                {"主营产品/服务": "水稻"},
                (_candidate("0111", "稻谷种植", "定义"),),
                _settings(),
                client=client,
            )


def test_timeout_is_reported_as_classification_failure() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out")

    with httpx.Client(
        transport=httpx.MockTransport(handler), base_url=_settings().deepseek_base_url
    ) as client:
        with pytest.raises(NationalEconomyClassificationError, match="timed out"):
            classify_national_economy(
                {"主营产品/服务": "水稻"},
                (_candidate("0111", "稻谷种植", "定义"),),
                _settings(),
                client=client,
            )
