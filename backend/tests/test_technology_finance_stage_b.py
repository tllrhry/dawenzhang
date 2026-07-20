import json
from dataclasses import replace
from types import SimpleNamespace

import httpx
import pytest

from app.core.config import Settings
from app.services.scenario_registry import (
    GREEN_FINANCE_REGISTRATION,
    PENSION_FINANCE_REGISTRATION,
)
from app.services.technology_finance_mapping_query import (
    FiveArticlesMappingLabel,
)
from app.services.technology_finance_stage_b import (
    TechnologyFinanceStageBError,
    classify_five_articles_stage_b,
    classify_technology_finance_stage_b,
)


def _settings() -> Settings:
    return Settings(
        _env_file=None,
        deepseek_api_key="test-deepseek-key",
        deepseek_base_url="https://deepseek.example/v1",
        deepseek_model="deepseek-test",
        deepseek_timeout_seconds=17,
        http_connect_timeout_seconds=3,
    )


def _stage_a(
    *,
    enterprise_code: str = "2710",
    enterprise_name: str = "化学药品原料药制造",
    loan_code: str = "6311",
    loan_name: str = "基础软件开发",
    loan_basis: str = "贷款用于采购服务器并建设基础软件研发平台。",
) -> SimpleNamespace:
    return SimpleNamespace(
        id=41,
        industry_code=enterprise_code,
        industry_major_code=f"C{enterprise_code[:2]}",
        industry_name=enterprise_name,
        rationale="企业主营创新药原料研发和制造。",
        loan_industry_code=loan_code,
        loan_industry_major_code=f"I{loan_code[:2]}",
        loan_industry_name=loan_name,
        loan_matching_basis=loan_basis,
    )


def _input_payload() -> dict[str, str]:
    return {
        "enterprise_name": "南京示例科技有限公司",
        "business_scope": "化学药品原料药制造；基础软件开发。",
        "main_business": "创新药原料研发和制造",
        "loan_purpose": "采购服务器并建设现有药物研发平台",
        "trade_goods_services": "研发服务器和软件服务",
        "credit_approval_opinion": "贷款仅限企业研发平台升级",
        "rd_ip_info": "拥有药物研发相关发明专利",
    }


def _label(
    *,
    code: str,
    name: str,
    source_row: int,
    subject: str = "高技术产业",
    taxonomy_path: tuple[str, ...] = ("高技术产业", "研发与技术服务"),
) -> FiveArticlesMappingLabel:
    tiers = (*taxonomy_path, None, None, None, None)[:4]
    return FiveArticlesMappingLabel(
        mapping_version_id=7,
        scenario_id="technology_finance",
        neic_code=code,
        code_level=len(code),
        neic_name=name,
        subject=subject,
        tier1=tiers[0],
        tier2=tiers[1],
        tier3=tiers[2],
        tier4=tiers[3],
        source_row=source_row,
    )


def _fixed_label(label: FiveArticlesMappingLabel) -> dict[str, object]:
    return {
        "mapping_version_id": label.mapping_version_id,
        "source_row": label.source_row,
        "NEIC_Code": label.neic_code,
        "NEIC_Name": label.neic_name,
        "subject": label.subject,
        "taxonomy_path": list(label.taxonomy_path),
    }


def _serialized_label(label: FiveArticlesMappingLabel) -> dict[str, object]:
    return {**_fixed_label(label), "match_method": label.match_method}


def _mapping_ref(label: FiveArticlesMappingLabel) -> dict[str, object]:
    fixed = _fixed_label(label)
    fixed.pop("subject")
    return {"type": "mapping", **fixed}


def _business_ref(
    field_key: str = "loan_purpose",
    field_label: str = "贷款用途详细描述",
    excerpt: str = "采购服务器并建设现有药物研发平台",
) -> dict[str, object]:
    return {
        "type": "business",
        "field_key": field_key,
        "field_label": field_label,
        "excerpt": excerpt,
    }


def _label_ref(
    label: FiveArticlesMappingLabel, side: str
) -> dict[str, object]:
    fixed = _fixed_label(label)
    fixed.pop("subject")
    return {"type": "label", "side": side, **fixed}


def _label_output(label: FiveArticlesMappingLabel) -> dict[str, object]:
    return {
        **_fixed_label(label),
        "matching_basis": "贷款资金用于现有研发平台升级，命中该科技金融类别。",
        "evidence_refs": [_mapping_ref(label), _business_ref()],
    }


def _label_basis_output() -> dict[str, object]:
    return {
        "matching_basis": "贷款资金用于现有研发平台升级，命中该科技金融类别。",
        "business_evidence_refs": [_business_ref()],
    }


def _model_output(
    enterprise_labels: tuple[FiveArticlesMappingLabel, ...],
    loan_labels: tuple[FiveArticlesMappingLabel, ...],
    status: str,
) -> dict[str, object]:
    refs: list[dict[str, object]] = []
    if enterprise_labels:
        refs.append(_label_ref(enterprise_labels[0], "enterprise"))
    refs.extend(
        (
            _label_ref(loan_labels[0], "loan_direction"),
            _business_ref(),
            _business_ref(
                "stage_a.loan_matching_basis",
                "Stage A 贷款投向匹配依据",
                "采购服务器并建设基础软件研发平台",
            ),
        )
    )
    return {
        "labels": [_label_output(label) for label in reversed(loan_labels)],
        "consistency": {
            "status": status,
            "basis": {
                "consistent": "企业和投向科技金融标签有交集，资金用于现有研发活动。",
                "inconsistent": "企业和投向科技金融标签无交集，资金流向独立业务。",
                "needs_review": "企业侧未命中科技金融标签，现有证据不足以可靠比较。",
            }[status],
            "evidence_refs": refs,
        },
    }


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
        transport=httpx.MockTransport(handler),
        base_url=_settings().deepseek_base_url,
    )


def _run(
    output: dict[str, object],
    enterprise_labels: tuple[FiveArticlesMappingLabel, ...],
    loan_labels: tuple[FiveArticlesMappingLabel, ...],
    *,
    stage_a: SimpleNamespace | None = None,
    input_payload: dict[str, str] | None = None,
):
    with _client(output) as client:
        return classify_technology_finance_stage_b(
            input_payload or _input_payload(),
            stage_a or _stage_a(),
            enterprise_labels,
            loan_labels,
            _settings(),
            client=client,
        )


def _run_green(
    output: dict[str, object],
    enterprise_labels: tuple[FiveArticlesMappingLabel, ...],
    loan_labels: tuple[FiveArticlesMappingLabel, ...],
    *,
    stage_a: SimpleNamespace,
):
    with _client(output) as client:
        return classify_five_articles_stage_b(
            GREEN_FINANCE_REGISTRATION,
            _input_payload(),
            stage_a,
            enterprise_labels,
            loan_labels,
            _settings(),
            client=client,
        )


def test_technology_stage_b_rejects_non_technology_candidates() -> None:
    enterprise = replace(
        _label(code="2710", name="化学药品原料药制造", source_row=11),
        scenario_id="green_finance",
    )
    loan = replace(
        _label(code="6311", name="基础软件开发", source_row=22),
        scenario_id="green_finance",
    )

    with pytest.raises(TechnologyFinanceStageBError, match="technology_finance"):
        _run(_model_output((enterprise,), (loan,), "consistent"), (enterprise,), (loan,))


def test_deterministic_labels_reject_mixed_scenarios() -> None:
    enterprise = replace(
        _label(code="2710", name="化学药品原料药制造", source_row=11),
        scenario_id="green_finance",
    )
    loan = replace(
        _label(code="6311", name="基础软件开发", source_row=22),
        scenario_id="digital_finance",
    )

    with pytest.raises(
        TechnologyFinanceStageBError,
        match="one non-empty scenario_id",
    ):
        _run(
            _model_output((enterprise,), (loan,), "consistent"),
            (enterprise,),
            (loan,),
        )


def test_prompt_contains_only_whitelisted_inputs_and_immutable_labels() -> None:
    enterprise = _label(code="2710", name="化学药品原料药制造", source_row=11)
    loan = _label(code="6311", name="基础软件开发", source_row=22)
    output = _model_output((enterprise,), (loan,), "consistent")
    captured: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": json.dumps(output, ensure_ascii=False)}}
                ]
            },
        )

    payload = {**_input_payload(), "unexpected_secret": "不得发送"}
    settings = _settings()
    with httpx.Client(
        transport=httpx.MockTransport(handler), base_url=settings.deepseek_base_url
    ) as client:
        classify_technology_finance_stage_b(
            payload,
            _stage_a(),
            (enterprise,),
            (loan,),
            settings,
            client=client,
        )

    user_input = json.loads(captured["messages"][1]["content"])
    system_prompt = captured["messages"][0]["content"]
    assert {field["field_key"] for field in user_input["template_fields"]} == set(
        _input_payload()
    )
    assert "unexpected_secret" not in json.dumps(user_input, ensure_ascii=False)
    assert user_input["stage_a_result"]["stage_a_result_id"] == 41
    assert user_input["enterprise_labels"] == [_serialized_label(enterprise)]
    assert user_input["loan_direction_labels"] == [_serialized_label(loan)]
    assert {
        source["field_key"] for source in user_input["business_evidence_sources"]
    } == {
        *_input_payload(),
        "stage_a.enterprise_matching_basis",
        "stage_a.loan_matching_basis",
    }
    assert user_input["max_excerpt_length"] == 160
    assert "不得新增、删除、改写或替换标签" in system_prompt
    assert "证据不足时必须输出 needs_review" in system_prompt
    assert "consistency 不得输出 label 引用或复制标签固定字段" in system_prompt
    assert "status、basis，不得返回任何 evidence_refs" in system_prompt


def test_model_cannot_change_or_reorder_into_a_different_label_set() -> None:
    enterprise = _label(code="2710", name="化学药品原料药制造", source_row=11)
    loan = _label(code="6311", name="基础软件开发", source_row=22)
    output = _model_output((enterprise,), (loan,), "consistent")
    output["labels"][0]["source_row"] = 999

    with pytest.raises(TechnologyFinanceStageBError, match="altered or invented"):
        _run(output, (enterprise,), (loan,))


@pytest.mark.parametrize(
    "mutation",
    [
        "fake_field",
        "fake_excerpt",
    ],
)
def test_fake_business_field_or_excerpt_is_rejected(mutation: str) -> None:
    enterprise = _label(code="2710", name="化学药品原料药制造", source_row=11)
    loan = _label(code="6311", name="基础软件开发", source_row=22)
    output = _model_output((enterprise,), (loan,), "consistent")
    business_ref = output["labels"][0]["evidence_refs"][1]
    if mutation == "fake_field":
        business_ref["field_key"] = "invented_field"
    else:
        business_ref["excerpt"] = "原始输入中不存在的虚假摘录"

    with pytest.raises(TechnologyFinanceStageBError, match="absent|not present"):
        _run(output, (enterprise,), (loan,))


def test_missing_business_evidence_is_rejected() -> None:
    enterprise = _label(code="2710", name="化学药品原料药制造", source_row=11)
    loan = _label(code="6311", name="基础软件开发", source_row=22)
    output = _model_output((enterprise,), (loan,), "consistent")
    output["labels"][0]["evidence_refs"] = [
        output["labels"][0]["evidence_refs"][0]
    ]

    with pytest.raises(TechnologyFinanceStageBError, match="at least one business"):
        _run(output, (enterprise,), (loan,))


@pytest.mark.parametrize(
    ("status", "enterprise", "loan"),
    [
        (
            "consistent",
            _label(code="2710", name="化学药品原料药制造", source_row=11),
            _label(code="6311", name="基础软件开发", source_row=22),
        ),
        (
            "inconsistent",
            _label(
                code="2710",
                name="化学药品原料药制造",
                source_row=11,
                subject="高技术制造业",
                taxonomy_path=("高技术制造业", "医药制造"),
            ),
            _label(
                code="6311",
                name="基础软件开发",
                source_row=22,
                subject="数字产品服务",
                taxonomy_path=("数字产品服务", "软件服务"),
            ),
        ),
    ],
)
def test_different_codes_accept_grounded_consistent_and_inconsistent_states(
    status: str,
    enterprise: FiveArticlesMappingLabel,
    loan: FiveArticlesMappingLabel,
) -> None:
    result = _run(_model_output((enterprise,), (loan,), status), (enterprise,), (loan,))

    assert result.consistency_status == status
    assert result.consistency_basis
    assert result.labels[0]["source_row"] == loan.source_row
    assert result.labels[0]["matching_basis"]
    assert len(result.consistency_evidence_refs) == 4


def test_missing_enterprise_mapping_requires_and_accepts_needs_review() -> None:
    loan = _label(code="6311", name="基础软件开发", source_row=22)
    output = _model_output((), (loan,), "needs_review")

    result = _run(output, (), (loan,))

    assert result.consistency_status == "needs_review"
    assert "证据不足" in result.consistency_basis


def test_non_pension_enterprise_with_unknown_share_is_not_applicable() -> None:
    loan = replace(
        _label(code="8514", name="老年人、残疾人养护服务", source_row=1520),
        scenario_id=PENSION_FINANCE_REGISTRATION.id,
    )
    output = _model_output((), (loan,), "inconsistent")

    with _client(output) as client:
        result = classify_five_articles_stage_b(
            PENSION_FINANCE_REGISTRATION,
            _input_payload(),
            _stage_a(
                enterprise_code="7020",
                enterprise_name="物业管理",
                loan_code="8514",
                loan_name="老年人、残疾人养护服务",
            ),
            (),
            (loan,),
            _settings(),
            client=client,
        )

    assert result.consistency_status == "inconsistent"
    assert result.result_status == "not_applicable"
    assert result.labels == ()
    assert "不属于养老金融" in result.consistency_basis
    assert len(result.consistency_evidence_refs) == 3


def test_legacy_consistency_refs_are_ignored_and_rebuilt_by_server() -> None:
    loan = _label(code="6311", name="基础软件开发", source_row=22)
    output = _model_output((), (loan,), "needs_review")
    output["consistency"]["evidence_refs"] = [
        {"type": "business", "field_key": "invented_field"}
    ]

    result = _run(output, (), (loan,))

    assert [ref["field_key"] for ref in result.consistency_evidence_refs[1:]] == [
        "loan_purpose",
        "stage_a.loan_matching_basis",
    ]


def test_insufficient_evidence_cannot_be_forced_to_consistent() -> None:
    enterprise = _label(code="2710", name="化学药品原料药制造", source_row=11)
    loan = _label(code="6311", name="基础软件开发", source_row=22)
    output = _model_output((enterprise,), (loan,), "consistent")
    payload = _input_payload()
    payload.pop("loan_purpose")
    trade_ref = _business_ref(
        "trade_goods_services",
        "贸易合同核心交易品类 / 服务内容",
        "研发服务器和软件服务",
    )
    output["labels"][0]["evidence_refs"][1] = trade_ref
    output["consistency"]["evidence_refs"][2] = trade_ref

    with pytest.raises(TechnologyFinanceStageBError, match="insufficient.*needs_review"):
        _run(output, (enterprise,), (loan,), input_payload=payload)


def test_same_four_digit_code_is_deterministically_consistent() -> None:
    label = _label(code="2710", name="化学药品原料药制造", source_row=11)
    output = {"labels": [_label_output(label)]}
    stage_a = _stage_a(
        enterprise_code="2710",
        enterprise_name="化学药品原料药制造",
        loan_code="2710",
        loan_name="化学药品原料药制造",
    )

    result = _run(output, (label,), (label,), stage_a=stage_a)

    assert result.consistency_status == "consistent"
    assert "均为2710" in result.consistency_basis
    assert [ref["field_key"] for ref in result.consistency_evidence_refs] == [
        "stage_a.industry_code",
        "stage_a.loan_industry_code",
    ]
    assert "consistency" not in result.model_output


def test_http_failure_is_reported_without_real_cloud_call() -> None:
    label = _label(code="2710", name="化学药品原料药制造", source_row=11)
    stage_a = _stage_a(
        enterprise_code="2710",
        enterprise_name="化学药品原料药制造",
        loan_code="2710",
        loan_name="化学药品原料药制造",
    )

    with _client({}, status_code=503) as client:
        with pytest.raises(TechnologyFinanceStageBError, match="503"):
            classify_technology_finance_stage_b(
                _input_payload(),
                stage_a,
                (label,),
                (label,),
                _settings(),
                client=client,
            )


def test_transient_network_failures_are_retried_before_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    label = _label(code="2710", name="化学药品原料药制造", source_row=11)
    stage_a = _stage_a(
        enterprise_code="2710",
        enterprise_name="化学药品原料药制造",
        loan_code="2710",
        loan_name="化学药品原料药制造",
    )
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise httpx.ConnectTimeout("temporary TLS timeout", request=request)
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": json.dumps(
                                {"label_basis": {
                                    "matching_basis": "贷款用于现有研发平台升级。",
                                    "business_evidence_refs": [_business_ref()],
                                }},
                                ensure_ascii=False,
                            )
                        }
                    }
                ]
            },
        )

    monkeypatch.setattr(
        "app.services.technology_finance_stage_b.time.sleep", lambda _seconds: None
    )
    settings = _settings()
    with httpx.Client(
        transport=httpx.MockTransport(handler), base_url=settings.deepseek_base_url
    ) as client:
        result = classify_technology_finance_stage_b(
            _input_payload(), stage_a, (label,), (label,), settings, client=client
        )

    assert attempts == 3
    assert result.consistency_status == "consistent"


def test_http_status_failure_is_not_retried() -> None:
    label = _label(code="2710", name="化学药品原料药制造", source_row=11)
    stage_a = _stage_a(
        enterprise_code="2710",
        enterprise_name="化学药品原料药制造",
        loan_code="2710",
        loan_name="化学药品原料药制造",
    )
    attempts = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        return httpx.Response(503, json={"error": "unavailable"})

    settings = _settings()
    with httpx.Client(
        transport=httpx.MockTransport(handler), base_url=settings.deepseek_base_url
    ) as client:
        with pytest.raises(TechnologyFinanceStageBError, match="503"):
            classify_technology_finance_stage_b(
                _input_payload(), stage_a, (label,), (label,), settings, client=client
            )

    assert attempts == 1


def test_output_label_order_is_normalized_to_deterministic_input_order() -> None:
    enterprise = _label(code="2710", name="化学药品原料药制造", source_row=11)
    first = _label(code="6311", name="基础软件开发", source_row=22)
    second = _label(
        code="63",
        name="软件和信息技术服务业",
        source_row=23,
        subject="科技服务业",
        taxonomy_path=("科技服务业",),
    )
    output = _model_output((enterprise,), (first, second), "consistent")

    result = _run(output, (enterprise,), (first, second))

    assert [label["source_row"] for label in result.labels] == [22, 23]


def test_label_output_allows_only_an_exact_echo_of_server_match_method() -> None:
    enterprise = _label(code="2710", name="化学药品原料药制造", source_row=11)
    loan = _label(code="6311", name="基础软件开发", source_row=22)
    output = _model_output((enterprise,), (loan,), "consistent")
    output["labels"][0]["match_method"] = "neic_code"

    result = _run(output, (enterprise,), (loan,))

    assert result.labels[0]["match_method"] == "neic_code"
    output["labels"][0]["match_method"] = "condition_fallback"
    with pytest.raises(TechnologyFinanceStageBError, match="match_method differs"):
        _run(output, (enterprise,), (loan,))


def test_mapping_evidence_allows_and_discards_an_exact_match_method_echo() -> None:
    enterprise = _label(code="2710", name="化学药品原料药制造", source_row=11)
    loan = _label(code="6311", name="基础软件开发", source_row=22)
    output = _model_output((enterprise,), (loan,), "consistent")
    output["labels"][0]["evidence_refs"][0]["match_method"] = "neic_code"

    result = _run(output, (enterprise,), (loan,))

    assert result.labels[0]["evidence_refs"][0] == _mapping_ref(loan)
    output["labels"][0]["evidence_refs"][0]["match_method"] = "condition_fallback"
    with pytest.raises(TechnologyFinanceStageBError, match="match_method differs"):
        _run(output, (enterprise,), (loan,))


def test_label_evidence_uses_server_mapping_when_model_returns_only_business_evidence() -> None:
    enterprise = _label(code="2710", name="化学药品原料药制造", source_row=11)
    loan = _label(code="6311", name="基础软件开发", source_row=22)
    output = _model_output((enterprise,), (loan,), "consistent")
    output["labels"][0]["evidence_refs"] = [_business_ref()]

    result = _run(output, (enterprise,), (loan,))

    assert result.labels[0]["evidence_refs"] == [_mapping_ref(loan), _business_ref()]


def test_same_code_multiple_labels_prompt_requires_labels_not_label_basis() -> None:
    first = _label(code="2710", name="化学药品原料药制造", source_row=11)
    second = _label(
        code="2710",
        name="化学药品原料药制造",
        source_row=12,
        subject="知识产权(专利)密集型产业",
        taxonomy_path=("信息通信技术制造业",),
    )
    captured: dict[str, object] = {}
    output = {"label_bases": [_label_basis_output(), _label_basis_output()]}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(output, ensure_ascii=False)}}]},
        )

    stage_a = _stage_a(
        enterprise_code="2710",
        enterprise_name="化学药品原料药制造",
        loan_code="2710",
        loan_name="化学药品原料药制造",
    )
    settings = _settings()
    with httpx.Client(
        transport=httpx.MockTransport(handler), base_url=settings.deepseek_base_url
    ) as client:
        result = classify_technology_finance_stage_b(
            _input_payload(), stage_a, (first, second), (first, second), settings, client=client
        )

    system_prompt = captured["messages"][0]["content"]  # type: ignore[index]
    assert "根对象只能返回 label_bases，不得返回 consistency。" in system_prompt
    assert "根对象只能返回 label_basis，不得返回 consistency。" not in system_prompt
    assert "不得把数组直接作为最外层值" in system_prompt
    assert '最外层形态必须是 {"label_bases":[...]}' in system_prompt
    assert [label["source_row"] for label in result.labels] == [11, 12]


def test_multiple_label_bases_are_attached_to_server_owned_labels_in_order() -> None:
    first = _label(code="2710", name="化学药品原料药制造", source_row=11)
    second = _label(
        code="2710",
        name="化学药品原料药制造",
        source_row=12,
        subject="知识产权(专利)密集型产业",
        taxonomy_path=("信息通信技术制造业",),
    )
    output = {
        "label_bases": [
            _label_basis_output(),
            {
                "matching_basis": "企业知识产权活动与该产业候选相匹配。",
                "business_evidence_refs": [
                    _business_ref(
                        "rd_ip_info",
                        "研发与知识产权情况",
                        "拥有药物研发相关发明专利",
                    )
                ],
            },
        ]
    }

    result = _run(
        output,
        (first, second),
        (first, second),
        stage_a=_stage_a(
            enterprise_code="2710",
            enterprise_name="化学药品原料药制造",
            loan_code="2710",
            loan_name="化学药品原料药制造",
        ),
    )

    assert [label["source_row"] for label in result.labels] == [11, 12]
    assert result.labels[1]["matching_basis"] == "企业知识产权活动与该产业候选相匹配。"
    assert result.labels[1]["evidence_refs"][0] == _mapping_ref(second)


def test_compact_legacy_labels_are_attached_to_server_owned_labels_in_order() -> None:
    first = _label(code="2710", name="化学药品原料药制造", source_row=11)
    second = _label(
        code="2710",
        name="化学药品原料药制造",
        source_row=12,
        subject="知识产权(专利)密集型产业",
        taxonomy_path=("信息通信技术制造业",),
    )
    output = {
        "labels": [
            {
                "matching_basis": "首个候选与企业主营及贷款用途相匹配。",
                "evidence_refs": [_business_ref()],
            },
            {
                "matching_basis": "第二个候选与企业知识产权活动相匹配。",
                "evidence_refs": [
                    _business_ref(
                        "rd_ip_info",
                        "研发与知识产权情况",
                        "拥有药物研发相关发明专利",
                    )
                ],
            },
        ]
    }

    result = _run(
        output,
        (first, second),
        (first, second),
        stage_a=_stage_a(
            enterprise_code="2710",
            enterprise_name="化学药品原料药制造",
            loan_code="2710",
            loan_name="化学药品原料药制造",
        ),
    )

    assert [label["source_row"] for label in result.labels] == [11, 12]
    assert result.labels[0]["mapping_version_id"] == first.mapping_version_id
    assert result.labels[1]["NEIC_Name"] == second.neic_name


def test_same_code_multiple_labels_accepts_direct_root_array() -> None:
    first = _label(code="2710", name="化学药品原料药制造", source_row=11)
    second = _label(
        code="2710",
        name="化学药品原料药制造",
        source_row=12,
        subject="知识产权(专利)密集型产业",
        taxonomy_path=("信息通信技术制造业",),
    )
    output = [_label_output(first), _label_output(second)]

    result = _run(
        output,
        (first, second),
        (first, second),
        stage_a=_stage_a(
            enterprise_code="2710",
            enterprise_name="化学药品原料药制造",
            loan_code="2710",
            loan_name="化学药品原料药制造",
        ),
    )

    assert [label["source_row"] for label in result.labels] == [11, 12]
    assert result.consistency_status == "consistent"
    assert result.model_output == {"labels": output}


def test_different_code_rejects_direct_root_array_without_consistency() -> None:
    enterprise = _label(code="2710", name="化学药品原料药制造", source_row=11)
    loan = _label(code="6311", name="基础软件开发", source_row=22)

    with pytest.raises(TechnologyFinanceStageBError, match="must be a JSON object"):
        _run([_label_output(loan)], (enterprise,), (loan,))


def test_single_label_basis_is_attached_to_server_owned_label() -> None:
    label = _label(code="2710", name="化学药品原料药制造", source_row=11)
    stage_a = _stage_a(
        enterprise_code="2710",
        enterprise_name="化学药品原料药制造",
        loan_code="2710",
        loan_name="化学药品原料药制造",
    )
    output = {
        "label_basis": {
            "matching_basis": "贷款资金用于现有研发平台升级，命中该科技金融类别。",
            "business_evidence_refs": [_business_ref()],
        }
    }

    result = _run(output, (label,), (label,), stage_a=stage_a)

    assert result.labels == (
        {
            **_serialized_label(label),
            "matching_basis": "贷款资金用于现有研发平台升级，命中该科技金融类别。",
            "evidence_refs": [_mapping_ref(label), _business_ref()],
        },
    )
    assert set(result.model_output) == {"label_basis"}


@pytest.mark.parametrize(
    ("enterprise_subject", "enterprise_path", "expected_status"),
    [
        ("绿色产业", ("节能环保",), "inconsistent"),
        ("清洁能源", ("可再生能源",), "consistent"),
    ],
    ids=["different-fallback-labels", "same-fallback-labels"],
)
def test_same_stage_a_code_condition_fallback_uses_real_consistency_evaluation(
    enterprise_subject: str,
    enterprise_path: tuple[str, ...],
    expected_status: str,
) -> None:
    loan = replace(
        _label(code="2710", name="化学药品原料药制造", source_row=22,
               subject="清洁能源", taxonomy_path=("可再生能源",)),
        scenario_id="green_finance", match_method="condition_fallback",
    )
    enterprise = replace(
        _label(code="2710", name="化学药品原料药制造", source_row=11,
               subject=enterprise_subject, taxonomy_path=enterprise_path),
        scenario_id="green_finance", match_method="condition_fallback",
    )
    stage_a = _stage_a(
        enterprise_code="2710", enterprise_name="化学药品原料药制造",
        loan_code="2710", loan_name="化学药品原料药制造",
    )
    output = {
        "label_basis": {
            "matching_basis": "贷款资金用于现有绿色项目建设，命中清洁能源类别。",
            "business_evidence_refs": [_business_ref()],
        },
        "consistency": {
            "status": "consistent",
            "basis": "企业主营与贷款投向均服务于现有绿色项目。",
        },
    }

    result = _run_green(output, (enterprise,), (loan,), stage_a=stage_a)

    assert result.consistency_status == expected_status
    assert result.labels[0]["match_method"] == "condition_fallback"
    assert "企业四位码与贷款投向四位码均为" not in result.consistency_basis
    assert result.model_output == output
    assert [(ref["side"], ref["source_row"]) for ref in result.consistency_evidence_refs[:2]] == [
        ("enterprise", 11),
        ("loan_direction", 22),
    ]


def test_consistency_label_refs_are_assembled_from_server_owned_labels() -> None:
    enterprise = _label(code="2710", name="化学药品原料药制造", source_row=11)
    loan = _label(code="6311", name="基础软件开发", source_row=22)
    output = {
        "label_basis": {
            "matching_basis": "贷款资金用于现有研发平台升级，命中该科技金融类别。",
            "business_evidence_refs": [_business_ref()],
        },
        "consistency": {
            "status": "consistent",
            "basis": "企业和投向科技金融标签有交集，资金用于现有研发活动。",
        },
    }

    result = _run(output, (enterprise,), (loan,))

    assert result.consistency_evidence_refs == (
        _label_ref(enterprise, "enterprise"),
        _label_ref(loan, "loan_direction"),
        _business_ref(),
        _business_ref(
            "stage_a.loan_matching_basis",
            "Stage A 贷款投向匹配依据",
            "贷款用于采购服务器并建设基础软件研发平台。",
        ),
    )


def test_no_taxonomy_intersection_overrides_model_consistent_status() -> None:
    enterprise = _label(
        code="2710",
        name="化学药品原料药制造",
        source_row=11,
        subject="高技术制造业",
        taxonomy_path=("高技术制造业", "医药制造"),
    )
    loan = _label(
        code="6311",
        name="基础软件开发",
        source_row=22,
        subject="数字产品服务",
        taxonomy_path=("数字产品服务", "软件服务"),
    )
    output = _model_output((enterprise,), (loan,), "consistent")

    result = _run(output, (enterprise,), (loan,))

    assert result.consistency_status == "inconsistent"
    assert "不存在主题或层级交集" in result.consistency_basis


def test_single_label_basis_discards_extra_invalid_business_refs() -> None:
    label = _label(code="2710", name="化学药品原料药制造", source_row=11)
    stage_a = _stage_a(
        enterprise_code="2710",
        enterprise_name="化学药品原料药制造",
        loan_code="2710",
        loan_name="化学药品原料药制造",
    )
    invalid_ref = _business_ref(field_key="invented_field")
    output = {
        "label_basis": {
            "matching_basis": "贷款资金用于现有研发平台升级，命中该科技金融类别。",
            "business_evidence_refs": [_business_ref(), invalid_ref],
        }
    }

    result = _run(output, (label,), (label,), stage_a=stage_a)

    assert result.labels[0]["evidence_refs"] == [
        _mapping_ref(label),
        _business_ref(),
    ]


def test_single_label_basis_rejects_when_all_business_refs_are_invalid() -> None:
    label = _label(code="2710", name="化学药品原料药制造", source_row=11)
    stage_a = _stage_a(
        enterprise_code="2710",
        enterprise_name="化学药品原料药制造",
        loan_code="2710",
        loan_name="化学药品原料药制造",
    )
    output = {
        "label_basis": {
            "matching_basis": "贷款资金用于现有研发平台升级，命中该科技金融类别。",
            "business_evidence_refs": [
                _business_ref(field_key="invented_field"),
                _business_ref(excerpt="原始输入中不存在的虚假摘录"),
            ],
        }
    }

    with pytest.raises(TechnologyFinanceStageBError, match="absent"):
        _run(output, (label,), (label,), stage_a=stage_a)


def test_legacy_extra_labels_cannot_expand_single_selected_result() -> None:
    enterprise = _label(code="2710", name="化学药品原料药制造", source_row=11)
    selected = _label(code="6311", name="基础软件开发", source_row=22)
    extra = _label(
        code="6311",
        name="基础软件开发",
        source_row=99,
        subject="模型额外输出",
        taxonomy_path=("不应进入正式结果",),
    )
    output = _model_output((enterprise,), (selected,), "consistent")
    output["labels"].append(_label_output(extra))

    result = _run(output, (enterprise,), (selected,))

    assert [label["source_row"] for label in result.labels] == [22]


def test_grounded_long_business_excerpt_is_truncated_by_server() -> None:
    label = _label(code="2710", name="化学药品原料药制造", source_row=11)
    stage_a = _stage_a(
        enterprise_code="2710",
        enterprise_name="化学药品原料药制造",
        loan_code="2710",
        loan_name="化学药品原料药制造",
    )
    long_excerpt = "采购服务器并建设现有药物研发平台" * 20
    output = {
        "label_basis": {
            "matching_basis": "贷款用于现有药物研发平台升级。",
            "business_evidence_refs": [
                _business_ref(excerpt=long_excerpt),
            ],
        }
    }

    result = _run(
        output,
        (label,),
        (label,),
        stage_a=stage_a,
        input_payload={**_input_payload(), "loan_purpose": long_excerpt},
    )

    saved_excerpt = result.labels[0]["evidence_refs"][1]["excerpt"]
    assert saved_excerpt == long_excerpt[:160]
    assert len(saved_excerpt) == 160
