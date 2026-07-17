#!/usr/bin/env python3
"""Validate the local green, digital, and pension finance DOCX assets."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys

from docx import Document
from docx.opc.exceptions import PackageNotFoundError


ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = ROOT / "模板文件" / "五篇大文章"
HEADER = ("字段名称", "填写内容", "填写提示")

STAGE_A_FIELD_ALIASES = {
    "enterprise_name": ("企业名称", "企业全称"),
    "unified_social_credit_code": ("统一社会信用代码",),
    "business_scope": ("营业执照经营范围（全文）",),
    "main_business": ("主营业务",),
    "main_business_revenue_share": ("主营业务及营收占比",),
    "core_products_services": ("核心产品 / 服务名称",),
    "loan_purpose": ("贷款用途详细描述",),
    "counterparty_name": (
        "贸易合同本次交易对手名称",
        "本次交易对手名称",
    ),
    "counterparty_business_industry": ("交易对手主营业务 / 所属行业",),
    "trade_goods_services": (
        "贸易合同核心交易品类 / 服务内容",
        "核心交易品类 / 服务内容",
    ),
    "industry_chain_position": ("企业产业链定位",),
    "industry_position_competitiveness": ("企业行业定位与核心竞争力",),
    "credit_approval_opinion": ("授信审批意见",),
}


@dataclass(frozen=True)
class DocxAssetSpec:
    scenario_id: str
    filename: str
    fields: tuple[str, ...]

    @property
    def path(self) -> Path:
        return ASSET_DIR / self.filename


COMMON_DIGITAL_PENSION_FIELDS = (
    "企业全称",
    "统一社会信用代码",
    "主体类型",
    "上年度营业收入",
    "营业执照经营范围（全文）",
    "主营业务",
    "主营业务及营收占比",
    "核心产品 / 服务名称",
    "贷款用途详细描述",
    "对应项目名称",
    "项目建设 / 运营内容",
    "本次交易对手名称",
    "交易对手主营业务 / 所属行业",
    "核心交易品类 / 服务内容",
    "企业产业链定位",
    "企业行业定位与核心竞争力",
)

ASSET_SPECS = (
    DocxAssetSpec(
        scenario_id="green_finance",
        filename="绿色金融模版.docx",
        fields=(
            "企业名称",
            "统一社会信用代码",
            "营业执照经营范围（全文）",
            "主营业务",
            "主营业务及营收占比",
            "核心产品 / 服务名称",
            "贷款用途详细描述",
            "贸易合同本次交易对手名称",
            "交易对手主营业务 / 所属行业",
            "贸易合同核心交易品类 / 服务内容",
            "企业产业链定位",
            "企业行业定位与核心竞争力",
            "授信审批意见",
            "对应绿色项目名称",
            "项目建设 / 运营内容",
            "节能减排 / 污染治理内容",
            "环保与绿色资质认证",
            "碳排放与环境效益",
            "重大环保违法失信情况",
        ),
    ),
    DocxAssetSpec(
        scenario_id="digital_finance",
        filename="数字金融模版.docx",
        fields=COMMON_DIGITAL_PENSION_FIELDS
        + ("数字核心竞争力", "研发与知识产权情况", "授信审批意见"),
    ),
    DocxAssetSpec(
        scenario_id="pension_finance",
        filename="养老金融模版.docx",
        fields=COMMON_DIGITAL_PENSION_FIELDS
        + (
            "该笔贷款实际投向养老产业占总贷款额度比",
            "企业核心资质与认证",
            "授信审批意见",
        ),
    ),
)


class DocxAssetValidationError(ValueError):
    """Raised when a scenario DOCX does not match its locked asset contract."""


def _clean(text: str) -> str:
    return " ".join(text.split())


def validate_docx_asset(path: Path, spec: DocxAssetSpec) -> tuple[str, ...]:
    """Return field labels after validating one three-column DOCX table."""
    if not path.is_file():
        raise DocxAssetValidationError(f"{spec.scenario_id}: 资产不存在: {path}")

    try:
        document = Document(path)
    except (PackageNotFoundError, ValueError, KeyError) as exc:
        raise DocxAssetValidationError(
            f"{spec.scenario_id}: 不是可解析的 DOCX: {path}"
        ) from exc

    three_column_tables = [table for table in document.tables if len(table.columns) == 3]
    if len(three_column_tables) != 1:
        raise DocxAssetValidationError(
            f"{spec.scenario_id}: 应有且仅有一个三列表格，实际 {len(three_column_tables)} 个"
        )

    table = three_column_tables[0]
    if not table.rows:
        raise DocxAssetValidationError(f"{spec.scenario_id}: 三列表格为空")
    header = tuple(_clean(cell.text) for cell in table.rows[0].cells)
    if header != HEADER:
        raise DocxAssetValidationError(
            f"{spec.scenario_id}: 表头应为 {HEADER}，实际为 {header}"
        )

    field_rows = [
        tuple(_clean(cell.text) for cell in row.cells)
        for row in table.rows[1:]
        if any(_clean(cell.text) for cell in row.cells)
    ]
    labels = tuple(row[0] for row in field_rows)
    if any(not label for label in labels):
        raise DocxAssetValidationError(f"{spec.scenario_id}: 存在空字段名称行")

    duplicates = sorted({label for label in labels if labels.count(label) > 1})
    if duplicates:
        raise DocxAssetValidationError(
            f"{spec.scenario_id}: 字段名称重复: {', '.join(duplicates)}"
        )

    expected = set(spec.fields)
    actual = set(labels)
    missing = sorted(expected - actual)
    unexpected = sorted(actual - expected)
    if len(labels) != len(spec.fields) or missing or unexpected:
        details = [f"字段行应为 {len(spec.fields)}，实际 {len(labels)}"]
        if missing:
            details.append(f"缺失: {', '.join(missing)}")
        if unexpected:
            details.append(f"多余: {', '.join(unexpected)}")
        raise DocxAssetValidationError(f"{spec.scenario_id}: {'; '.join(details)}")

    missing_stage_a = [
        key
        for key, aliases in STAGE_A_FIELD_ALIASES.items()
        if not actual.intersection(aliases)
    ]
    if missing_stage_a:
        raise DocxAssetValidationError(
            f"{spec.scenario_id}: Stage A 字段缺失: {', '.join(missing_stage_a)}"
        )

    embedded = sorted(
        {
            label
            for _, _, hint in field_rows
            for label in spec.fields
            if f"{label}：" in hint or f"{label}:" in hint
        }
    )
    if embedded:
        raise DocxAssetValidationError(
            f"{spec.scenario_id}: 字段仍嵌入填写提示: {', '.join(embedded)}"
        )

    return labels


def validate_all_docx_assets() -> dict[str, tuple[str, ...]]:
    """Validate every locked scenario asset and return labels by scenario."""
    return {spec.scenario_id: validate_docx_asset(spec.path, spec) for spec in ASSET_SPECS}


def main() -> int:
    try:
        validated = validate_all_docx_assets()
    except DocxAssetValidationError as exc:
        print(f"FAIL {exc}", file=sys.stderr)
        return 1

    for spec in ASSET_SPECS:
        print(f"PASS {spec.scenario_id} fields={len(validated[spec.scenario_id])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
