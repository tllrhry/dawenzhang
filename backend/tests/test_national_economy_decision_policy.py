import pytest

from app.services.national_economy_decision_policy import (
    EvidenceFact,
    EvidenceLayer,
    EvidenceLevel,
    NoUsableEvidenceError,
    decide_primary_business,
    supplement_layer_with_objection,
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
