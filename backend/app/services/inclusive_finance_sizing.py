"""工信部联企业〔2011〕300 号中小微企业划型纯规则。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Literal


EnterpriseSize = Literal["大型", "中型", "小型", "微型", "不可判定"]


@dataclass(frozen=True)
class SizingThreshold:
    revenue_wan: Decimal | None = None
    employee_count: Decimal | None = None
    total_assets_wan: Decimal | None = None

    def is_met_by(
        self,
        revenue_wan: Decimal | None,
        employee_count: Decimal | None,
        total_assets_wan: Decimal | None,
    ) -> bool:
        return all(
            actual is not None and actual >= expected
            for actual, expected in (
                (revenue_wan, self.revenue_wan),
                (employee_count, self.employee_count),
                (total_assets_wan, self.total_assets_wan),
            )
            if expected is not None
        )


@dataclass(frozen=True)
class SizingCategory:
    name: str
    large: SizingThreshold
    medium: SizingThreshold
    small: SizingThreshold

    @property
    def required_metrics(self) -> tuple[str, ...]:
        return tuple(
            metric
            for metric, value in (
                ("revenue_wan", self.small.revenue_wan),
                ("employee_count", self.small.employee_count),
                ("total_assets_wan", self.small.total_assets_wan),
            )
            if value is not None
        )


def _threshold(
    *,
    revenue_wan: int | None = None,
    employee_count: int | None = None,
    total_assets_wan: int | None = None,
) -> SizingThreshold:
    return SizingThreshold(
        revenue_wan=Decimal(revenue_wan) if revenue_wan is not None else None,
        employee_count=Decimal(employee_count) if employee_count is not None else None,
        total_assets_wan=(
            Decimal(total_assets_wan) if total_assets_wan is not None else None
        ),
    )


# 单位：营业收入/资产总额为万元，从业人员为人。阈值完整转录自 300 号。
SIZING_CATEGORIES: dict[str, SizingCategory] = {
    "农林牧渔业": SizingCategory("农林牧渔业", _threshold(revenue_wan=20000), _threshold(revenue_wan=500), _threshold(revenue_wan=50)),
    "工业": SizingCategory("工业", _threshold(employee_count=1000, revenue_wan=40000), _threshold(employee_count=300, revenue_wan=2000), _threshold(employee_count=20, revenue_wan=300)),
    "建筑业": SizingCategory("建筑业", _threshold(revenue_wan=80000, total_assets_wan=80000), _threshold(revenue_wan=6000, total_assets_wan=5000), _threshold(revenue_wan=300, total_assets_wan=300)),
    "批发业": SizingCategory("批发业", _threshold(employee_count=200, revenue_wan=40000), _threshold(employee_count=20, revenue_wan=5000), _threshold(employee_count=5, revenue_wan=1000)),
    "零售业": SizingCategory("零售业", _threshold(employee_count=300, revenue_wan=20000), _threshold(employee_count=50, revenue_wan=500), _threshold(employee_count=10, revenue_wan=100)),
    "交通运输业": SizingCategory("交通运输业", _threshold(employee_count=1000, revenue_wan=30000), _threshold(employee_count=300, revenue_wan=3000), _threshold(employee_count=20, revenue_wan=200)),
    "仓储业": SizingCategory("仓储业", _threshold(employee_count=200, revenue_wan=30000), _threshold(employee_count=100, revenue_wan=1000), _threshold(employee_count=20, revenue_wan=100)),
    "邮政业": SizingCategory("邮政业", _threshold(employee_count=1000, revenue_wan=30000), _threshold(employee_count=300, revenue_wan=2000), _threshold(employee_count=20, revenue_wan=100)),
    "住宿业": SizingCategory("住宿业", _threshold(employee_count=300, revenue_wan=10000), _threshold(employee_count=100, revenue_wan=2000), _threshold(employee_count=10, revenue_wan=100)),
    "餐饮业": SizingCategory("餐饮业", _threshold(employee_count=300, revenue_wan=10000), _threshold(employee_count=100, revenue_wan=2000), _threshold(employee_count=10, revenue_wan=100)),
    "信息传输业": SizingCategory("信息传输业", _threshold(employee_count=2000, revenue_wan=100000), _threshold(employee_count=100, revenue_wan=1000), _threshold(employee_count=10, revenue_wan=100)),
    "软件和信息技术服务业": SizingCategory("软件和信息技术服务业", _threshold(employee_count=300, revenue_wan=10000), _threshold(employee_count=100, revenue_wan=1000), _threshold(employee_count=10, revenue_wan=50)),
    "房地产开发经营": SizingCategory("房地产开发经营", _threshold(revenue_wan=200000, total_assets_wan=10000), _threshold(revenue_wan=1000, total_assets_wan=5000), _threshold(revenue_wan=100, total_assets_wan=2000)),
    "物业管理": SizingCategory("物业管理", _threshold(employee_count=1000, revenue_wan=5000), _threshold(employee_count=300, revenue_wan=1000), _threshold(employee_count=100, revenue_wan=500)),
    "租赁和商务服务业": SizingCategory("租赁和商务服务业", _threshold(employee_count=300, total_assets_wan=120000), _threshold(employee_count=100, total_assets_wan=8000), _threshold(employee_count=10, total_assets_wan=100)),
    "其他未列明行业": SizingCategory("其他未列明行业", _threshold(employee_count=300), _threshold(employee_count=100), _threshold(employee_count=10)),
}


def map_industry_to_sizing_category(
    industry_code: object, industry_major_code: object
) -> str | None:
    """Map a Stage A GB/T 4754 industry code to one of the 16 sizing groups."""
    code_digits = _digits(industry_code)
    major_digits = _digits(industry_major_code)
    medium_code = code_digits[:3] if len(code_digits) >= 3 else major_digits[:3]
    major_code = code_digits[:2] if len(code_digits) >= 2 else major_digits[:2]
    if not major_code:
        return None
    if medium_code == "701":
        return "房地产开发经营"
    if medium_code == "702":
        return "物业管理"

    major = int(major_code)
    if 1 <= major <= 5:
        return "农林牧渔业"
    if 6 <= major <= 46:
        return "工业"
    if 47 <= major <= 50:
        return "建筑业"
    if major == 51:
        return "批发业"
    if major == 52:
        return "零售业"
    if 53 <= major <= 58:
        return "交通运输业"
    if major == 59:
        return "仓储业"
    if major == 60:
        return "邮政业"
    if major == 61:
        return "住宿业"
    if major == 62:
        return "餐饮业"
    if 63 <= major <= 64:
        return "信息传输业"
    if major == 65:
        return "软件和信息技术服务业"
    if 71 <= major <= 72:
        return "租赁和商务服务业"
    return "其他未列明行业"


def classify_enterprise_size(
    category: object,
    revenue_wan: object,
    employee_count: object,
    total_assets_wan: object,
) -> EnterpriseSize:
    """Classify by the required metrics only; missing/unparseable metrics are unknown."""
    sizing_category = SIZING_CATEGORIES.get(str(category))
    if sizing_category is None:
        return "不可判定"
    values = {
        "revenue_wan": _decimal(revenue_wan),
        "employee_count": _decimal(employee_count),
        "total_assets_wan": _decimal(total_assets_wan),
    }
    if any(values[metric] is None for metric in sizing_category.required_metrics):
        return "不可判定"
    if sizing_category.large.is_met_by(**values):
        return "大型"
    if sizing_category.medium.is_met_by(**values):
        return "中型"
    if sizing_category.small.is_met_by(**values):
        return "小型"
    return "微型"


def _digits(value: object) -> str:
    return "".join(re.findall(r"\d", str(value or "")))


def _decimal(value: object) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    text = str(value).strip().replace(",", "").replace("，", "")
    if not text:
        return None
    try:
        parsed = Decimal(text)
    except InvalidOperation:
        return None
    return parsed if parsed >= 0 else None
