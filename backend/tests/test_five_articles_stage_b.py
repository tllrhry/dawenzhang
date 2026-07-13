import json
from types import SimpleNamespace

import httpx
import pytest

from app.core.config import Settings
from app.services.scenario_registry import GREEN_FINANCE_REGISTRATION
from app.services.technology_finance_mapping_query import FiveArticlesMappingLabel
from app.services.technology_finance_stage_b import (
    TechnologyFinanceStageBError,
    classify_five_articles_stage_b,
)


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        deepseek_api_key="test-deepseek-key",
        deepseek_base_url="https://deepseek.example/v1",
        deepseek_model="deepseek-test",
    )


def _stage_a() -> SimpleNamespace:
    return SimpleNamespace(
        id=41,
        industry_code="2710",
        industry_major_code="C27",
        industry_name="化学药品原料药制造",
        rationale="企业主营绿色原料药制造。",
        loan_industry_code="2710",
        loan_industry_major_code="C27",
        loan_industry_name="化学药品原料药制造",
        loan_matching_basis="贷款用于建设分布式光伏发电项目。",
    )


def _label(scenario_id: str = "green_finance") -> FiveArticlesMappingLabel:
    return FiveArticlesMappingLabel(
        mapping_version_id=7,
        scenario_id=scenario_id,
        neic_code="2710",
        code_level=4,
        neic_name="化学药品原料药制造",
        subject="绿色产业",
        tier1="绿色产业",
        tier2="清洁能源",
        tier3=None,
        tier4=None,
        source_row=11,
    )


def test_green_profile_uses_its_whitelist_and_server_owned_mapping_evidence() -> None:
    label = _label()
    captured: dict[str, object] = {}
    output = {
        "label_basis": {
            "matching_basis": "贷款用于分布式光伏发电项目，符合绿色金融类别。",
            "business_evidence_refs": [
                {
                    "type": "business",
                    "field_key": "green_project_name",
                    "field_label": "对应绿色项目名称",
                    "excerpt": "分布式光伏发电项目",
                }
            ],
        }
    }

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(output)}}]},
        )

    with httpx.Client(
        transport=httpx.MockTransport(handler), base_url=_settings().deepseek_base_url
    ) as client:
        result = classify_five_articles_stage_b(
            GREEN_FINANCE_REGISTRATION,
            {
                "loan_purpose": "建设分布式光伏发电项目",
                "green_project_name": "分布式光伏发电项目",
                "rd_ip_info": "其他场景字段不得作为绿色证据",
            },
            _stage_a(),
            (label,),
            (label,),
            _settings(),
            client=client,
        )

    prompt_input = json.loads(captured["messages"][1]["content"])
    prompt_fields = {field["field_key"] for field in prompt_input["template_fields"]}
    assert "绿色金融 Stage B" in captured["messages"][0]["content"]
    assert {"loan_purpose", "green_project_name"} <= prompt_fields
    assert "rd_ip_info" not in prompt_fields
    assert result.labels[0]["evidence_refs"] == [
        {
            "type": "mapping",
            "mapping_version_id": 7,
            "source_row": 11,
            "NEIC_Code": "2710",
            "NEIC_Name": "化学药品原料药制造",
            "taxonomy_path": ["绿色产业", "清洁能源"],
        },
        output["label_basis"]["business_evidence_refs"][0],
    ]


def test_profile_rejects_cross_scenario_candidates_before_model_call() -> None:
    foreign_label = _label("technology_finance")

    with pytest.raises(TechnologyFinanceStageBError, match="green_finance"):
        classify_five_articles_stage_b(
            GREEN_FINANCE_REGISTRATION,
            {},
            _stage_a(),
            (foreign_label,),
            (foreign_label,),
            _settings(),
        )
