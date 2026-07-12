import pytest

from app.services.national_economy_decision_policy import (
    EvidenceFact,
    EvidenceLayer,
    EvidenceLevel,
    LoanDirectionDecision,
    LoanDirectionRoute,
    LoanPurposeSpecificity,
    NoUsableEvidenceError,
    build_main_business_revenue_layer,
    decide_loan_direction,
    decide_primary_business,
    find_dominant_main_business,
    parse_main_business_revenue_shares,
    supplement_layer_with_objection,
)


@pytest.mark.parametrize("loan_purpose", ["", "  ", "经营周转", "流动资金"])
def test_generic_loan_purpose_falls_back_to_enterprise_conclusion(
    loan_purpose: str,
) -> None:
    decision = decide_loan_direction(
        loan_purpose=loan_purpose,
        matches_main_business=False,
        within_business_scope=False,
    )

    assert decision.route is LoanDirectionRoute.USE_ENTERPRISE_CONCLUSION
    assert decision.specificity is LoanPurposeSpecificity.GENERIC
    assert decision.matches_enterprise is True


def test_specific_loan_purpose_matching_main_business_stays_consistent() -> None:
    decision = decide_loan_direction(
        loan_purpose="采购水稻种子用于种植",
        matches_main_business=True,
        within_business_scope=True,
    )

    assert decision.route is LoanDirectionRoute.USE_ENTERPRISE_CONCLUSION
    assert decision.specificity is LoanPurposeSpecificity.SPECIFIC
    assert decision.matches_enterprise is True


def test_specific_minor_business_within_scope_is_classified_separately() -> None:
    decision = decide_loan_direction(
        loan_purpose="采购汽车及零部件",
        matches_main_business=False,
        within_business_scope=True,
    )

    assert decision.route is LoanDirectionRoute.CLASSIFY_ACTUAL_DIRECTION
    assert decision.specificity is LoanPurposeSpecificity.SPECIFIC
    assert decision.matches_enterprise is False


def test_specific_loan_purpose_beyond_scope_needs_manual_review() -> None:
    decision = decide_loan_direction(
        loan_purpose="采购经营范围外的医疗器械",
        matches_main_business=False,
        within_business_scope=False,
    )

    assert decision.route is LoanDirectionRoute.NEEDS_MANUAL_REVIEW
    assert decision.specificity is LoanPurposeSpecificity.SPECIFIC
    assert decision.matches_enterprise is None


def test_generic_decision_cannot_be_inconsistent() -> None:
    with pytest.raises(
        ValueError,
        match="generic loan purpose must use the enterprise conclusion",
    ):
        LoanDirectionDecision(
            route=LoanDirectionRoute.CLASSIFY_ACTUAL_DIRECTION,
            specificity=LoanPurposeSpecificity.GENERIC,
            matches_enterprise=False,
        )


def _layer(
    level: EvidenceLevel,
    business: str = "",
    *,
    label: str = "原字段",
    raw_text: str | None = None,
    unavailable_reason: str | None = None,
) -> EvidenceLayer:
    facts = ()
    if raw_text is not None or business:
        facts = (
            EvidenceFact(
                field_label=label,
                raw_text=business if raw_text is None else raw_text,
                indicated_business=business,
            ),
        )
    return EvidenceLayer(
        level=level,
        facts=facts,
        unavailable_reason=unavailable_reason,
    )


def test_highest_revenue_business_has_priority_over_lower_levels() -> None:
    decision = decide_primary_business(
        (
            _layer(EvidenceLevel.BUSINESS_SCOPE, "农产品批发"),
            _layer(EvidenceLevel.MAIN_BUSINESS_REVENUE, "稻谷种植"),
            _layer(EvidenceLevel.TRADE_AND_INDUSTRY_CHAIN, "粮食收购"),
            _layer(EvidenceLevel.LOAN_PURPOSE, "农业生产"),
        )
    )

    assert decision.adopted_layer.level is EvidenceLevel.MAIN_BUSINESS_REVENUE
    assert decision.adopted_business == "稻谷种植"
    assert {conflict.conflicting_level for conflict in decision.conflicts} == {
        EvidenceLevel.TRADE_AND_INDUSTRY_CHAIN,
        EvidenceLevel.LOAN_PURPOSE,
        EvidenceLevel.BUSINESS_SCOPE,
    }


@pytest.mark.parametrize(
    ("layers", "expected_level", "expected_skipped"),
    [
        (
            (
                _layer(
                    EvidenceLevel.MAIN_BUSINESS_REVENUE,
                    unavailable_reason="未填写主营业务及营收占比",
                ),
                _layer(EvidenceLevel.TRADE_AND_INDUSTRY_CHAIN, "粮食收购"),
                _layer(EvidenceLevel.LOAN_PURPOSE, "农业生产"),
                _layer(EvidenceLevel.BUSINESS_SCOPE, "农产品批发"),
            ),
            EvidenceLevel.TRADE_AND_INDUSTRY_CHAIN,
            (EvidenceLevel.MAIN_BUSINESS_REVENUE,),
        ),
        (
            (
                _layer(
                    EvidenceLevel.MAIN_BUSINESS_REVENUE,
                    unavailable_reason="无法分辨最高营收业务",
                ),
                _layer(
                    EvidenceLevel.TRADE_AND_INDUSTRY_CHAIN,
                    unavailable_reason="合同未明确交易品类与产业链",
                ),
                _layer(EvidenceLevel.LOAN_PURPOSE, "农业生产"),
                _layer(EvidenceLevel.BUSINESS_SCOPE, "农产品批发"),
            ),
            EvidenceLevel.LOAN_PURPOSE,
            (
                EvidenceLevel.MAIN_BUSINESS_REVENUE,
                EvidenceLevel.TRADE_AND_INDUSTRY_CHAIN,
            ),
        ),
        (
            (
                _layer(
                    EvidenceLevel.MAIN_BUSINESS_REVENUE,
                    unavailable_reason="缺失",
                ),
                _layer(
                    EvidenceLevel.TRADE_AND_INDUSTRY_CHAIN,
                    unavailable_reason="缺失",
                ),
                _layer(
                    EvidenceLevel.LOAN_PURPOSE,
                    unavailable_reason="未直接指向经营领域",
                ),
                _layer(EvidenceLevel.BUSINESS_SCOPE, "农产品批发"),
            ),
            EvidenceLevel.BUSINESS_SCOPE,
            (
                EvidenceLevel.MAIN_BUSINESS_REVENUE,
                EvidenceLevel.TRADE_AND_INDUSTRY_CHAIN,
                EvidenceLevel.LOAN_PURPOSE,
            ),
        ),
    ],
)
def test_evidence_falls_back_one_level_at_a_time(
    layers: tuple[EvidenceLayer, ...],
    expected_level: EvidenceLevel,
    expected_skipped: tuple[EvidenceLevel, ...],
) -> None:
    decision = decide_primary_business(layers)

    assert decision.adopted_layer.level is expected_level
    assert tuple(layer.level for layer in decision.skipped_layers) == expected_skipped


def test_lower_level_conflict_does_not_reverse_adopted_conclusion() -> None:
    decision = decide_primary_business(
        (
            _layer(EvidenceLevel.MAIN_BUSINESS_REVENUE, "软件开发"),
            _layer(EvidenceLevel.TRADE_AND_INDUSTRY_CHAIN, "设备销售"),
        )
    )

    assert decision.adopted_business == "软件开发"
    assert decision.conflicts[0].conflicting_business == "设备销售"


def test_objection_supplements_an_existing_level_instead_of_becoming_a_fifth() -> None:
    trade_layer = _layer(
        EvidenceLevel.TRADE_AND_INDUSTRY_CHAIN,
        unavailable_reason="原合同事实不完整",
    )
    supplemented = supplement_layer_with_objection(
        trade_layer,
        field_label="异议补充：贸易合同核心交易品类 / 服务内容",
        raw_text="实际交易标的是水稻种子",
        indicated_business="稻谷种植",
    )
    decision = decide_primary_business(
        (
            _layer(
                EvidenceLevel.MAIN_BUSINESS_REVENUE,
                unavailable_reason="无法分辨最高营收业务",
            ),
            supplemented,
            _layer(EvidenceLevel.LOAN_PURPOSE, "农资采购"),
        )
    )

    assert supplemented.level is EvidenceLevel.TRADE_AND_INDUSTRY_CHAIN
    assert supplemented.facts[-1].source == "objection"
    assert decision.adopted_layer is supplemented


def test_no_usable_evidence_requires_manual_handling() -> None:
    with pytest.raises(NoUsableEvidenceError, match="no usable evidence"):
        decide_primary_business(
            (
                _layer(EvidenceLevel.MAIN_BUSINESS_REVENUE, unavailable_reason="缺失"),
                _layer(EvidenceLevel.BUSINESS_SCOPE, raw_text="", business=""),
            )
        )


def test_revenue_share_parser_accepts_multiple_separators_and_full_width_percent() -> None:
    items = parse_main_business_revenue_shares(
        "养老服务70%；机构养老服务10%、社区养老服务 20％,其他业务5%"
    )

    assert [(item.business_label, item.percentage) for item in items] == [
        ("养老服务", 70),
        ("机构养老服务", 10),
        ("社区养老服务", 20),
        ("其他业务", 5),
    ]


@pytest.mark.parametrize(
    ("raw_text", "expected_business", "expected_percentage"),
    [
        ("养老服务70%；机构养老服务30%", "养老服务", 70),
        ("养老服务50%；机构养老服务30%", "养老服务", 50),
        ("养老服务 50％ / 机构养老服务 49%", "养老服务", 50),
    ],
)
def test_revenue_share_at_or_above_fifty_locks_dominant_main_business(
    raw_text: str,
    expected_business: str,
    expected_percentage: int,
) -> None:
    dominant = find_dominant_main_business(raw_text)

    assert dominant is not None
    assert dominant.business_label == expected_business
    assert dominant.percentage == expected_percentage


@pytest.mark.parametrize(
    "raw_text",
    [
        "计算机及外部设备45%/软件30%/网络工程5%",
        "计算机49%；软件30%",
        "养老服务50%；机构养老服务50%",
        "养老服务70；机构养老服务30",
        "70%",
        "",
        "未填写",
    ],
)
def test_revenue_share_without_unique_labeled_fifty_percent_item_does_not_lock(
    raw_text: str,
) -> None:
    assert find_dominant_main_business(raw_text) is None


def test_missing_percent_item_is_ignored_while_valid_item_is_still_parsed() -> None:
    items = parse_main_business_revenue_shares("养老服务70；机构养老服务30%")

    assert [(item.business_label, item.percentage) for item in items] == [
        ("机构养老服务", 30)
    ]
    assert find_dominant_main_business("养老服务70；机构养老服务30%") is None


def test_dominant_main_business_is_injected_into_revenue_evidence_layer() -> None:
    raw_text = "养老服务70%；机构养老服务10%；社区养老服务20%"

    layer = build_main_business_revenue_layer(raw_text)

    assert layer.level is EvidenceLevel.MAIN_BUSINESS_REVENUE
    assert layer.is_available is True
    assert layer.usable_facts[0].field_label == "主营业务及营收占比（主导主营）"
    assert layer.usable_facts[0].raw_text == raw_text
    assert layer.usable_facts[0].indicated_business == "养老服务"


@pytest.mark.parametrize(
    "raw_text",
    ["计算机及外部设备45%/软件30%/网络工程5%", "养老服务70", ""],
)
def test_revenue_evidence_layer_safely_falls_back_without_dominant_business(
    raw_text: str,
) -> None:
    layer = build_main_business_revenue_layer(raw_text)

    assert layer.level is EvidenceLevel.MAIN_BUSINESS_REVENUE
    assert layer.is_available is False
    assert layer.facts == ()
    assert layer.unavailable_reason is not None
