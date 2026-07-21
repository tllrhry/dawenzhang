import json
from dataclasses import replace

import httpx
import pytest

from app.core.config import Settings
from app.services.national_economy_classification import (
    NationalEconomyClassificationError,
    classify_national_economy,
)
from app.services.national_economy_decision_policy import (
    EvidenceFact,
    EvidenceLayer,
    EvidenceLevel,
    build_main_business_revenue_layer,
)
from app.services.national_economy_retrieval import (
    CandidateEvidenceTrace,
    EvidenceSnapshot,
    RecallHit,
)


def _settings() -> Settings:
    return Settings(
        database_url="postgresql+psycopg://user:pass@localhost/test",
        deepseek_api_key="test-key",
    )


def _candidate(code: str, name: str, text: str) -> EvidenceSnapshot:
    hit = RecallHit(
        industry_code=code,
        industry_name=name,
        text=text,
        chunk_type="definition",
        source_row=2,
        distance=0.2,
    )
    return EvidenceSnapshot(
        industry_code=code,
        industry_name=name,
        vector_score=0.8,
        rerank_score=0.9,
        hits=(hit,),
        evidence_traces=(
            CandidateEvidenceTrace(
                EvidenceLevel.MAIN_BUSINESS_REVENUE,
                (EvidenceFact("主营业务及营收占比", "水稻 90%", "水稻 90%"),),
                (hit,),
            ),
        ),
        major_category_code="A01",
        major_category_name="农、林、牧、渔业",
    )


def _candidate_with_complete_catalog(code: str, name: str) -> EvidenceSnapshot:
    hits = tuple(
        RecallHit(
            industry_code=code,
            industry_name=name,
            text=text,
            chunk_type=chunk_type,
            source_row=source_row,
            distance=0.2,
        )
        for chunk_type, text, source_row in (
            ("definition", "面向经营单位销售粮食的活动。", 2),
            ("include", "包括谷物批发。", 3),
            ("exclude", "不包括面向最终消费者的粮油零售。", 4),
        )
    )
    return EvidenceSnapshot(
        industry_code=code,
        industry_name=name,
        vector_score=0.8,
        rerank_score=0.9,
        hits=hits,
        evidence_traces=(
            CandidateEvidenceTrace(
                EvidenceLevel.MAIN_BUSINESS_REVENUE,
                (EvidenceFact("主营业务及营收占比", "粮食批发 60%", "粮食批发 60%"),),
                (hits[1],),
            ),
        ),
        major_category_code="F51",
        major_category_name="批发和零售业",
    )


def _evidence(business: str = "水稻种植") -> tuple[EvidenceLayer, ...]:
    return (
        EvidenceLayer(
            EvidenceLevel.MAIN_BUSINESS_REVENUE,
            (EvidenceFact("主营业务", business, business),),
        ),
        EvidenceLayer(
            EvidenceLevel.TRADE_AND_INDUSTRY_CHAIN,
            unavailable_reason="未提供贸易合同或产业链信息",
        ),
        EvidenceLayer(
            EvidenceLevel.LOAN_PURPOSE,
            (EvidenceFact("贷款用途详细描述", "采购汽车零部件", "采购汽车零部件"),),
        ),
        EvidenceLayer(
            EvidenceLevel.BUSINESS_SCOPE,
            (
                EvidenceFact(
                    "营业执照经营范围（全文）",
                    "谷物种植；销售汽车零部件",
                    "谷物种植；销售汽车零部件",
                ),
            ),
        ),
    )


def _dominant_evidence(business: str = "养老服务") -> tuple[EvidenceLayer, ...]:
    return (
        build_main_business_revenue_layer(
            f"{business}70%；计算机销售20%；网络工程10%"
        ),
        *_evidence(business)[1:],
    )


def _dual_success(
    *,
    enterprise_code: str = "0111",
    enterprise_name: str = "稻谷种植",
    loan_code: str = "0111",
    loan_name: str = "稻谷种植",
    specificity: str = "generic",
    route: str | None = None,
) -> dict[str, object]:
    selected_route = route or (
        "use_enterprise_conclusion"
        if (loan_code, loan_name) == (enterprise_code, enterprise_name)
        else "classify_actual_direction"
    )
    if selected_route == "use_enterprise_conclusion":
        loan_direction = {
            "route": selected_route,
            "matching_basis": "实际投向服务于企业主导主营，由服务端继承企业结论。",
            "specificity": specificity,
        }
    else:
        loan_direction = {
            "route": selected_route,
            "no_match": False,
            "industry_code": loan_code,
            "industry_name": loan_name,
            "matching_basis": (
                f"实际投向属于另一经营活动，对应四级代码 {loan_code}。"
            ),
            "specificity": specificity,
        }
    return {
        "enterprise": {
            "no_match": False,
            "industry_code": enterprise_code,
            "industry_name": enterprise_name,
            "matching_basis": "主营水稻种植，匹配四级代码 0111。",
        },
        "loan_direction": loan_direction,
    }


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


def test_generic_dual_conclusion_falls_back_to_enterprise() -> None:
    candidates = (
        _candidate("0111", "稻谷种植", "稻谷种植的定义"),
        _candidate("0112", "小麦种植", "小麦种植的定义"),
    )

    with _client(_dual_success()) as client:
        result = classify_national_economy(
            _evidence(),
            candidates,
            _settings(),
            objection={"补充说明": "收入主要来自水稻"},
            client=client,
        )

    assert result.status == "completed"
    assert (result.industry_code, result.industry_name) == ("0111", "稻谷种植")
    assert (result.loan_industry_code, result.loan_industry_name) == (
        "0111",
        "稻谷种植",
    )
    assert result.loan_specificity == "generic"
    assert result.loan_matches_enterprise is True
    assert result.confidence is None
    assert result.summary is None
    assert result.objection == {"补充说明": "收入主要来自水稻"}
    assert result.candidate_snapshot[0]["major_category_code"] == "A01"


def test_specific_loan_direction_can_select_loan_candidate_and_recomputes_false() -> None:
    enterprise_candidates = (_candidate("3742", "航天器及运载火箭制造", "航天制造"),)
    loan_candidates = (_candidate("5263", "汽车零配件零售", "汽车零配件零售"),)
    output = _dual_success(
        enterprise_code="3742",
        enterprise_name="航天器及运载火箭制造",
        loan_code="5263",
        loan_name="汽车零配件零售",
        specificity="specific",
    )

    with _client(output) as client:
        result = classify_national_economy(
            _dominant_evidence("航天器制造"),
            enterprise_candidates,
            _settings(),
            client=client,
            loan_direction_candidates=loan_candidates,
        )

    assert result.status == "completed"
    assert result.loan_industry_code == "5263"
    assert result.loan_specificity == "specific"
    assert result.loan_matches_enterprise is False
    assert "5263" in result.loan_matching_basis


def test_specific_main_business_route_inherits_enterprise_without_loan_candidate() -> None:
    candidates = (_candidate("0111", "稻谷种植", "稻谷种植"),)
    output = _dual_success(specificity="specific")

    with _client(output) as client:
        result = classify_national_economy(
            _evidence(),
            candidates,
            _settings(),
            client=client,
        )

    assert result.loan_industry_code == result.industry_code
    assert result.loan_matches_enterprise is True


@pytest.mark.parametrize(
    ("enterprise", "loan_only_candidate"),
    [
        (("4790", "其他房屋建筑业"), ("5090", "其他未列明建筑业")),
        (("5132", "服装批发"), ("5131", "纺织品、针织品及原料批发")),
        (("0141", "蔬菜种植"), ("0511", "种子种苗培育活动")),
        (("6513", "应用软件开发"), ("6560", "信息技术咨询服务")),
    ],
)
def test_specific_main_business_route_is_stable_when_retrieval_pools_disagree(
    enterprise: tuple[str, str],
    loan_only_candidate: tuple[str, str],
) -> None:
    output = _dual_success(
        enterprise_code=enterprise[0],
        enterprise_name=enterprise[1],
        loan_code=enterprise[0],
        loan_name=enterprise[1],
        specificity="specific",
        route="use_enterprise_conclusion",
    )

    with _client(output) as client:
        result = classify_national_economy(
            _dominant_evidence(enterprise[1]),
            (_candidate(*enterprise, enterprise[1]),),
            _settings(),
            client=client,
            loan_direction_candidates=(
                _candidate(
                    *loan_only_candidate,
                    loan_only_candidate[1],
                ),
            ),
        )

    assert (result.loan_industry_code, result.loan_industry_name) == enterprise
    assert result.loan_matches_enterprise is True


def test_specific_loan_direction_cannot_borrow_enterprise_only_candidate() -> None:
    enterprise_candidates = (
        _candidate("1951", "纺织面料鞋制造", "纺织面料鞋制造"),
    )
    loan_candidates = (
        _candidate("1819", "其他机织服装制造", "其他机织服装制造"),
    )
    output = _dual_success(
        enterprise_code="1951",
        enterprise_name="纺织面料鞋制造",
        loan_code="1951",
        loan_name="纺织面料鞋制造",
        specificity="specific",
        route="classify_actual_direction",
    )

    with _client(output) as client:
        with pytest.raises(
            NationalEconomyClassificationError,
            match="loan_direction.*same candidate",
        ):
            classify_national_economy(
                _dominant_evidence("鞋制造"),
                enterprise_candidates,
                _settings(),
                client=client,
                loan_direction_candidates=loan_candidates,
            )


@pytest.mark.parametrize(
    ("enterprise", "loan"),
    [
        (("6513", "应用软件开发"), ("6210", "正餐服务")),
        (("4710", "住宅房屋建筑"), ("5165", "建材批发")),
        (("2927", "日用塑料制品制造"), ("5199", "其他未列明批发业")),
    ],
)
def test_specific_loan_candidate_pool_isolated_across_industries(
    enterprise: tuple[str, str],
    loan: tuple[str, str],
) -> None:
    output = _dual_success(
        enterprise_code=enterprise[0],
        enterprise_name=enterprise[1],
        loan_code=enterprise[0],
        loan_name=enterprise[1],
        specificity="specific",
        route="classify_actual_direction",
    )

    with _client(output) as client:
        with pytest.raises(
            NationalEconomyClassificationError,
            match="loan_direction.*same candidate",
        ):
            classify_national_economy(
                _dominant_evidence(enterprise[1]),
                (_candidate(*enterprise, enterprise[1]),),
                _settings(),
                client=client,
                loan_direction_candidates=(_candidate(*loan, loan[1]),),
            )


def test_matched_candidate_major_codes_are_captured_from_the_correct_pools() -> None:
    enterprise_candidate = replace(
        _candidate("3742", "航天器及运载火箭制造", "航天制造"),
        major_category_code="C37",
    )
    loan_candidate = replace(
        _candidate("5263", "汽车零配件零售", "汽车零配件零售"),
        major_category_code="F52",
    )
    output = _dual_success(
        enterprise_code="3742",
        enterprise_name="航天器及运载火箭制造",
        loan_code="5263",
        loan_name="汽车零配件零售",
        specificity="specific",
    )

    with _client(output) as client:
        result = classify_national_economy(
            _evidence(),
            (enterprise_candidate,),
            _settings(),
            client=client,
            loan_direction_candidates=(loan_candidate,),
        )

    assert result.industry_major_code == "C37"
    assert result.loan_industry_major_code == "F52"


def test_generic_loan_direction_inherits_enterprise_major_code() -> None:
    enterprise_candidate = replace(
        _candidate("0111", "稻谷种植", "稻谷种植"),
        major_category_code="A01",
    )

    with _client(_dual_success()) as client:
        result = classify_national_economy(
            _evidence(),
            (enterprise_candidate,),
            _settings(),
            client=client,
        )

    assert result.industry_major_code == "A01"
    assert result.loan_industry_major_code == result.industry_major_code


def test_no_match_branches_leave_major_codes_empty() -> None:
    output = {
        "enterprise": {"no_match": True, "reason": "企业候选均不匹配。"},
        "loan_direction": {
            "route": "classify_actual_direction",
            "no_match": True,
            "reason": "贷款用途候选均不匹配。",
            "specificity": "specific",
        },
    }

    with _client(output) as client:
        result = classify_national_economy(
            _evidence(),
            (_candidate("0111", "稻谷种植", "农业定义"),),
            _settings(),
            client=client,
        )

    assert result.industry_major_code is None
    assert result.loan_industry_major_code is None


def test_request_contains_two_candidate_pools_and_loan_decision_tree() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": json.dumps(_dual_success())}}
                ]
            },
        )

    settings = _settings()
    with httpx.Client(
        transport=httpx.MockTransport(handler), base_url=settings.deepseek_base_url
    ) as client:
        classify_national_economy(
            _evidence(),
            (_candidate("0111", "稻谷种植", "目录命中片段"),),
            settings,
            objection={"reason": "经营内容已变化"},
            client=client,
            loan_direction_candidates=(
                _candidate("5263", "汽车零配件零售", "投向目录片段"),
            ),
        )

    user_content = json.loads(captured["messages"][1]["content"])
    system_prompt = captured["messages"][0]["content"]
    assert captured["temperature"] == 0
    assert captured["response_format"] == {"type": "json_object"}
    assert [layer["priority"] for layer in user_content["ordered_evidence"]] == [
        1,
        2,
        3,
        4,
    ]
    assert user_content["enterprise_candidates"][0]["industry_code"] == "0111"
    assert user_content["loan_direction_candidates"][0]["industry_code"] == "5263"
    candidate_payload = json.dumps(
        {
            "enterprise_candidates": user_content["enterprise_candidates"],
            "loan_direction_candidates": user_content["loan_direction_candidates"],
        },
        ensure_ascii=False,
    )
    assert '"chunk_type": "定义"' in candidate_payload
    assert not any(
        f'"chunk_type": "{label}"' in candidate_payload
        for label in ("definition", "include", "exclude")
    )
    assert user_content["dominant_main_business"] is None
    assert user_content["objection"] == {"reason": "经营内容已变化"}
    assert "笼统" in system_prompt
    assert "无论是否已登记在营业执照经营范围内" in system_prompt
    assert "不得作为否定真实贷款投向或拒绝选择候选的门槛" in system_prompt
    assert "不得仅以不属于主营或不在营业执照经营范围内为由返回无匹配" in system_prompt
    assert "仍须按实际资金用途完成分类" in system_prompt
    assert "真实投向既不在主营也不在经营范围" not in system_prompt
    assert "真实投向" in system_prompt
    assert "贷款用途详细描述是主信号" in system_prompt
    assert "贸易合同核心交易品类用于揭示并校正资金真实流向" in system_prompt
    assert "授信审批意见是资金用途的刚性约束" in system_prompt
    assert (
        "贷款用途详细描述高于贸易合同核心交易品类，贸易合同核心交易品类高于"
        "授信审批意见"
    ) in system_prompt
    assert "贸易合同与授信审批意见冲突时必须以贸易合同" in system_prompt
    assert "不得采用逐级降级只取最高可用层的布尔机制" in system_prompt
    assert "必须综合三类证据得出真实投向" in system_prompt
    assert "生产设备等直接进入主导主营产品/服务生产、销售或交付的投入品" in system_prompt
    assert "不得改判为投入品所属行业" in system_prompt
    assert "真实投向为资金收款方所提供产品或服务对应的行业" in system_prompt
    assert "明确声明不用于主营业务投入时，不得返回 route=use_enterprise_conclusion" in system_prompt
    assert "项目终端用途也不得改变借款人实际开展的经营活动" in system_prompt
    assert "route=use_enterprise_conclusion" in system_prompt
    assert "route=classify_actual_direction" in system_prompt
    assert "低于50%的其他业务线" in system_prompt
    assert "不得称为主营" in system_prompt
    assert "只能从 loan_direction_candidates 的同一记录选择" in system_prompt
    assert "行业代码/名称由服务端继承企业结论" in system_prompt
    assert (
        "贷款投向 matching_basis 必须明确指明真实投向依据贷款用途、贸易合同核心"
        "交易品类、授信审批意见中的哪一类或哪几类证据判定"
    ) in system_prompt
    assert "matching_basis 与 reason 的内容必须全中文" in system_prompt
    assert "不得出现任何英文词元" in system_prompt
    assert "英文单词、字母缩写或英文片段类型标签" in system_prompt
    assert "直接用业务语言陈述结论与支撑事实" in system_prompt
    assert "不得写采用了哪个优先级、字段或证据层" in system_prompt
    assert "说明采用层级" not in system_prompt
    assert "字段标签" not in system_prompt
    assert "企业结论必须落在该主导主营对应的四级行业" in system_prompt
    assert "必须采用最高可用层；低层冲突不得推翻高层" in system_prompt
    assert "所选行业必须有业务证据命中其包括中的至少一条" in system_prompt
    assert "语义匹配不要求业务原文与目录逐字重复" in system_prompt
    assert "不得仅因业务名称比目录更细而拒绝最匹配候选" in system_prompt
    assert "根对象只能包含 enterprise 和 loan_direction" in system_prompt
    assert "不得返回置信度、AI 总结或 matched" in system_prompt
    assert "一致性由服务端复算" in system_prompt


def test_request_hard_locks_enterprise_to_dominant_main_business() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(_dual_success())}}]},
        )

    settings = _settings()
    with httpx.Client(
        transport=httpx.MockTransport(handler), base_url=settings.deepseek_base_url
    ) as client:
        classify_national_economy(
            _dominant_evidence(),
            (_candidate("0111", "稻谷种植", "目录命中片段"),),
            settings,
            client=client,
        )

    user_content = json.loads(captured["messages"][1]["content"])
    system_prompt = captured["messages"][0]["content"]
    assert user_content["dominant_main_business"] == "养老服务"
    assert user_content["ordered_evidence"][0]["facts"][0]["raw_text"].startswith(
        "养老服务70%"
    )
    assert "企业结论必须落在该主导主营对应的四级行业" in system_prompt
    assert "绝对不得因核心产品/服务中的其他条目或更低占比业务线改判" in system_prompt
    assert "该锁定只约束企业结论" in system_prompt
    assert "为空时" in system_prompt and "既有行为不变" in system_prompt


def test_request_carries_complete_catalog_and_definition_grounded_constraints() -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": json.dumps(_dual_success())}}]},
        )

    settings = _settings()
    candidate = _candidate_with_complete_catalog("0111", "稻谷种植")
    with httpx.Client(
        transport=httpx.MockTransport(handler), base_url=settings.deepseek_base_url
    ) as client:
        classify_national_economy(
            _dominant_evidence(),
            (candidate,),
            settings,
            client=client,
            loan_direction_candidates=(candidate,),
        )

    user_content = json.loads(captured["messages"][1]["content"])
    system_prompt = captured["messages"][0]["content"]
    expected_fragments = [
        {
            "chunk_type": "定义",
            "text": "面向经营单位销售粮食的活动。",
            "source_row": 2,
        },
        {"chunk_type": "包括", "text": "包括谷物批发。", "source_row": 3},
        {
            "chunk_type": "不包括",
            "text": "不包括面向最终消费者的粮油零售。",
            "source_row": 4,
        },
    ]
    assert user_content["enterprise_candidates"][0]["complete_catalog_fragments"] == (
        expected_fragments
    )
    assert user_content["loan_direction_candidates"][0]["complete_catalog_fragments"] == (
        expected_fragments
    )
    assert "所选行业必须有业务证据命中其包括中的至少一条" in system_prompt
    assert "目录中的概括项、其他项或未列明项" in system_prompt
    assert "业务证据不得命中其不包括" in system_prompt
    assert "业务证据与候选定义相斥" in system_prompt
    assert "不得仅因候选重排靠前而选中" in system_prompt
    assert "matching_basis 必须明确指出业务证据命中了所选行业包括中的哪一条" in system_prompt
    assert "门类级结构性判别原则数量有限" in system_prompt
    assert "不得逐项业务枚举关键词" in system_prompt
    assert "批发与零售按客户对象区分" in system_prompt
    assert "面向经营单位、经销商或集团等客户的销售属于批发" in system_prompt
    assert "面向最终消费者的销售属于零售" in system_prompt
    assert "或将资金支付给其他行业购买员工培训等独立" in system_prompt
    assert "借款人自身使用资金开展另一项" in system_prompt
    assert "不得仅因交易标的为著作权转让就把软件技术购买归入知识产权服务" in system_prompt
    assert "已有少量收入或使用相似原材料而回落企业结论" in system_prompt
    assert "matching_basis 与 reason 的内容必须全中文" in system_prompt
    assert "直接用业务语言陈述结论与支撑事实" in system_prompt
    assert "不得写采用了哪个优先级、字段或证据层" in system_prompt
    assert "企业结论必须落在该主导主营对应的四级行业" in system_prompt
    assert "贷款投向必须按以下决策树判定" in system_prompt


def test_specific_loan_direction_no_match_returns_needs_review() -> None:
    output = _dual_success()
    output["loan_direction"] = {
        "route": "classify_actual_direction",
        "no_match": True,
        "reason": "实际投向购买芯片，超出经营范围，需人工确认。",
        "specificity": "specific",
    }

    with _client(output) as client:
        result = classify_national_economy(
            _evidence(),
            (_candidate("0111", "稻谷种植", "农业定义"),),
            _settings(),
            client=client,
        )

    assert result.status == "needs_review"
    assert result.industry_code == "0111"
    assert result.loan_industry_code is None
    assert result.loan_industry_name is None
    assert result.loan_matching_basis == output["loan_direction"]["reason"]
    assert result.loan_specificity == "specific"
    assert result.loan_matches_enterprise is None


def test_enterprise_no_match_returns_needs_review_without_forced_conclusion() -> None:
    output = {
        "enterprise": {
            "no_match": True,
            "reason": "企业候选均不覆盖软件开发活动。",
        },
        "loan_direction": {
            "route": "classify_actual_direction",
            "no_match": True,
            "reason": "具体贷款用途也不在经营范围内。",
            "specificity": "specific",
        },
    }

    with _client(output) as client:
        result = classify_national_economy(
            _evidence("软件开发"),
            (_candidate("0111", "稻谷种植", "农业定义"),),
            _settings(),
            client=client,
        )

    assert result.status == "needs_review"
    assert result.industry_code is None
    assert result.industry_name is None
    assert result.matching_basis == output["enterprise"]["reason"]
    assert result.loan_matching_basis == output["loan_direction"]["reason"]
    assert result.loan_matches_enterprise is None


@pytest.mark.parametrize(
    ("side", "code", "name", "message"),
    [
        ("enterprise", "9999", "未知行业", "enterprise.*same candidate"),
        ("loan_direction", "9999", "未知行业", "loan_direction.*same candidate"),
        ("loan_direction", "5263", "汽车零部件制造", "loan_direction.*same candidate"),
    ],
)
def test_each_success_side_requires_an_exact_candidate_pair(
    side: str, code: str, name: str, message: str
) -> None:
    output = _dual_success(
        loan_code="5263",
        loan_name="汽车零配件零售",
        specificity="specific",
        route="classify_actual_direction",
    )
    output[side]["industry_code"] = code
    output[side]["industry_name"] = name

    with _client(output) as client:
        with pytest.raises(NationalEconomyClassificationError, match=message):
            classify_national_economy(
                _evidence(),
                (_candidate("0111", "稻谷种植", "定义"),),
                _settings(),
                client=client,
                loan_direction_candidates=(
                    _candidate("5263", "汽车零配件零售", "定义"),
                ),
            )


def test_enterprise_cannot_select_from_loan_direction_candidate_pool() -> None:
    output = _dual_success(
        enterprise_code="5263",
        enterprise_name="汽车零配件零售",
        loan_code="5263",
        loan_name="汽车零配件零售",
        specificity="specific",
    )

    with _client(output) as client:
        with pytest.raises(
            NationalEconomyClassificationError, match="enterprise.*same candidate"
        ):
            classify_national_economy(
                _evidence(),
                (_candidate("0111", "稻谷种植", "定义"),),
                _settings(),
                client=client,
                loan_direction_candidates=(
                    _candidate("5263", "汽车零配件零售", "定义"),
                ),
            )


def test_generic_loan_direction_cannot_use_independent_route() -> None:
    output = _dual_success(
        loan_code="5263",
        loan_name="汽车零配件零售",
        specificity="generic",
    )

    with _client(output) as client:
        with pytest.raises(
            NationalEconomyClassificationError,
            match="classify_actual_direction requires specificity=specific",
        ):
            classify_national_economy(
                _evidence(),
                (_candidate("0111", "稻谷种植", "定义"),),
                _settings(),
                client=client,
                loan_direction_candidates=(
                    _candidate("5263", "汽车零配件零售", "定义"),
                ),
            )


def test_inherited_route_rejects_model_supplied_industry_fields() -> None:
    output = _dual_success(specificity="specific")
    output["loan_direction"].update(
        {
            "no_match": False,
            "industry_code": "0111",
            "industry_name": "稻谷种植",
        }
    )

    with _client(output) as client:
        with pytest.raises(
            NationalEconomyClassificationError,
            match="loan_direction inherited.*unexpected",
        ):
            classify_national_economy(
                _evidence(),
                (_candidate("0111", "稻谷种植", "定义"),),
                _settings(),
                client=client,
            )


@pytest.mark.parametrize(
    "route", ["", "inherit", "needs_manual_review", None, True]
)
def test_loan_route_is_constrained(route: object) -> None:
    output = _dual_success()
    output["loan_direction"]["route"] = route

    with _client(output) as client:
        with pytest.raises(
            NationalEconomyClassificationError,
            match="route must be use_enterprise_conclusion or classify_actual_direction",
        ):
            classify_national_economy(
                _evidence(),
                (_candidate("0111", "稻谷种植", "定义"),),
                _settings(),
                client=client,
            )


@pytest.mark.parametrize("specificity", ["vague", "", None, True])
def test_loan_specificity_is_constrained(specificity: object) -> None:
    output = _dual_success()
    output["loan_direction"]["specificity"] = specificity

    with _client(output) as client:
        with pytest.raises(
            NationalEconomyClassificationError, match="specificity must be generic or specific"
        ):
            classify_national_economy(
                _evidence(),
                (_candidate("0111", "稻谷种植", "定义"),),
                _settings(),
                client=client,
            )


def test_model_reported_match_flag_is_rejected() -> None:
    output = _dual_success()
    output["loan_direction"]["matched"] = False

    with _client(output) as client:
        with pytest.raises(
            NationalEconomyClassificationError, match=r"unexpected=\['matched'\]"
        ):
            classify_national_economy(
                _evidence(),
                (_candidate("0111", "稻谷种植", "定义"),),
                _settings(),
                client=client,
            )


def test_invalid_model_contract_is_repaired_with_bounded_follow_up() -> None:
    invalid_output = {
        "enterprise": {"no_match": True, "reason": "企业候选暂未匹配。"},
        "loan_direction": {
            "route": "use_enterprise_conclusion",
            "matching_basis": "贷款用途服务于企业主导主营。",
            "specificity": "specific",
        },
    }
    outputs = [invalid_output, _dual_success(specificity="specific")]
    requests: list[dict[str, object]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": json.dumps(outputs.pop(0))}}
                ]
            },
        )

    settings = _settings()
    with httpx.Client(
        transport=httpx.MockTransport(handler), base_url=settings.deepseek_base_url
    ) as client:
        result = classify_national_economy(
            _dominant_evidence("稻谷种植"),
            (_candidate("0111", "稻谷种植", "定义"),),
            settings,
            client=client,
        )

    assert result.status == "completed"
    assert result.loan_matches_enterprise is True
    assert len(requests) == 2
    assert [message["role"] for message in requests[1]["messages"]] == [
        "system",
        "user",
        "assistant",
        "user",
    ]
    assert "不得放宽候选约束" in requests[1]["messages"][-1]["content"]


def test_repeated_invalid_model_contract_still_fails_after_three_attempts() -> None:
    invalid_output = {
        "enterprise": {"no_match": True, "reason": "企业候选暂未匹配。"},
        "loan_direction": {
            "route": "use_enterprise_conclusion",
            "matching_basis": "贷款用途服务于企业主导主营。",
            "specificity": "specific",
        },
    }
    call_count = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": json.dumps(invalid_output)}}
                ]
            },
        )

    settings = _settings()
    with httpx.Client(
        transport=httpx.MockTransport(handler), base_url=settings.deepseek_base_url
    ) as client:
        with pytest.raises(
            NationalEconomyClassificationError,
            match="cannot inherit an unsuccessful enterprise conclusion",
        ):
            classify_national_economy(
                _dominant_evidence("稻谷种植"),
                (_candidate("0111", "稻谷种植", "定义"),),
                settings,
                client=client,
            )

    assert call_count == 3


@pytest.mark.parametrize(
    "response_content",
    [
        "not-json",
        json.dumps({"enterprise": {}, "loan_direction": {}}),
        json.dumps({"enterprise": {"no_match": True, "reason": ""}, "loan_direction": {}}),
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
                _evidence(),
                (_candidate("0111", "稻谷种植", "定义"),),
                _settings(),
                client=client,
            )


def test_http_failure_is_reported_as_classification_failure() -> None:
    with _client({}, status_code=503) as client:
        with pytest.raises(NationalEconomyClassificationError, match="503"):
            classify_national_economy(
                _evidence(),
                (_candidate("0111", "稻谷种植", "定义"),),
                _settings(),
                client=client,
            )


def test_transient_transport_failure_is_retried_without_changing_contract() -> None:
    call_count = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise httpx.ConnectTimeout("TLS handshake timed out")
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": json.dumps(_dual_success())}}
                ]
            },
        )

    with httpx.Client(
        transport=httpx.MockTransport(handler), base_url=_settings().deepseek_base_url
    ) as client:
        result = classify_national_economy(
            _evidence(),
            (_candidate("0111", "稻谷种植", "定义"),),
            _settings(),
            client=client,
        )

    assert call_count == 2
    assert result.status == "completed"


def test_timeout_is_reported_as_classification_failure() -> None:
    call_count = 0

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        raise httpx.ReadTimeout("timed out")

    with httpx.Client(
        transport=httpx.MockTransport(handler), base_url=_settings().deepseek_base_url
    ) as client:
        with pytest.raises(NationalEconomyClassificationError, match="timed out"):
            classify_national_economy(
                _evidence(),
                (_candidate("0111", "稻谷种植", "定义"),),
                _settings(),
                client=client,
            )

    assert call_count == 3
