import pytest

from app.services.inclusive_finance_sizing import (
    SIZING_CATEGORIES,
    classify_enterprise_size,
    map_industry_to_sizing_category,
)


def _metric_values(category: str, level: str) -> dict[str, float]:
    threshold = getattr(SIZING_CATEGORIES[category], level)
    return {
        "revenue_wan": float(threshold.revenue_wan or 0),
        "employee_count": float(threshold.employee_count or 0),
        "total_assets_wan": float(threshold.total_assets_wan or 0),
    }


@pytest.mark.parametrize("category", tuple(SIZING_CATEGORIES))
@pytest.mark.parametrize(
    ("level", "expected"),
    (("large", "大型"), ("medium", "中型"), ("small", "小型")),
)
def test_each_sizing_category_respects_large_medium_small_thresholds(
    category: str, level: str, expected: str
) -> None:
    assert classify_enterprise_size(category, **_metric_values(category, level)) == expected


@pytest.mark.parametrize("category", tuple(SIZING_CATEGORIES))
def test_each_sizing_category_classifies_below_small_threshold_as_micro(category: str) -> None:
    values = _metric_values(category, "small")
    required_metric = SIZING_CATEGORIES[category].required_metrics[0]
    values[required_metric] -= 1

    assert classify_enterprise_size(category, **values) == "微型"


@pytest.mark.parametrize("category", tuple(SIZING_CATEGORIES))
def test_each_sizing_category_requires_all_its_metrics(category: str) -> None:
    values = _metric_values(category, "small")
    values[SIZING_CATEGORIES[category].required_metrics[0]] = None

    assert classify_enterprise_size(category, **values) == "不可判定"


@pytest.mark.parametrize(
    ("industry_code", "industry_major_code", "expected"),
    (
        ("0111", "A01", "农林牧渔业"),
        ("3742", "C37", "工业"),
        ("4810", "E48", "建筑业"),
        ("5111", "F51", "批发业"),
        ("5263", "F52", "零售业"),
        ("5410", "G54", "交通运输业"),
        ("5910", "G59", "仓储业"),
        ("6010", "G60", "邮政业"),
        ("6110", "H61", "住宿业"),
        ("6210", "H62", "餐饮业"),
        ("6310", "I63", "信息传输业"),
        ("6510", "I65", "软件和信息技术服务业"),
        ("7110", "L71", "租赁和商务服务业"),
        ("6610", "J66", "其他未列明行业"),
    ),
)
def test_industry_major_ranges_map_to_the_required_sizing_category(
    industry_code: str, industry_major_code: str, expected: str
) -> None:
    assert map_industry_to_sizing_category(industry_code, industry_major_code) == expected


def test_real_estate_medium_prefixes_and_other_real_estate_are_split() -> None:
    assert map_industry_to_sizing_category("7010", "K70") == "房地产开发经营"
    assert map_industry_to_sizing_category("7020", "K70") == "物业管理"
    assert map_industry_to_sizing_category("7030", "K70") == "其他未列明行业"


def test_missing_industry_cannot_be_mapped() -> None:
    assert map_industry_to_sizing_category(None, None) is None
