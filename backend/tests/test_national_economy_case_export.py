from io import BytesIO

from openpyxl import load_workbook

from app.models import (
    NationalEconomyClassificationCase,
    NationalEconomyClassificationResult,
)
from app.services.national_economy_case_export import export_case_workbook
from app.services.national_economy_case_ingestion import FIELD_LABELS


def _case() -> NationalEconomyClassificationCase:
    return NationalEconomyClassificationCase(
        id=1,
        scenario="national_economy_classification",
        original_filename="示例企业.docx",
        input_payload={field: f"{label}内容" for field, label in FIELD_LABELS.items()},
        status="needs_review",
    )


def test_export_case_workbook_contains_input_current_result_and_full_history() -> None:
    case = _case()
    NationalEconomyClassificationResult(
        case=case,
        version=2,
        status="needs_review",
        candidate_snapshot=[],
        rationale="候选均不匹配",
        objection={"description": "主营收入结构已变化"},
    )
    NationalEconomyClassificationResult(
        case=case,
        version=1,
        status="completed",
        industry_code="0111",
        industry_name="稻谷种植",
        confidence=92,
        rationale="主营业务与目录定义一致",
        ai_summary="企业主要从事稻谷种植",
        candidate_snapshot=[],
    )

    workbook = load_workbook(BytesIO(export_case_workbook(case)))

    assert workbook.sheetnames == ["案例输入", "当前结论", "判定历史"]

    input_rows = dict(workbook["案例输入"].iter_rows(min_row=2, values_only=True))
    assert input_rows["业务场景"] == "national_economy_classification"
    assert input_rows["原始文件名"] == "示例企业.docx"
    assert input_rows[FIELD_LABELS["enterprise_name"]] == "企业名称内容"
    assert len(input_rows) == len(FIELD_LABELS) + 3

    current_sheet = workbook["当前结论"]
    assert tuple(cell.value for cell in current_sheet[1]) == (
        "行业代码",
        "行业名称",
        "置信度",
        "匹配依据",
        "AI 总结",
    )
    assert tuple(cell.value for cell in current_sheet[2]) == (
        "0111",
        "稻谷种植",
        92,
        "主营业务与目录定义一致",
        "企业主要从事稻谷种植",
    )

    history_sheet = workbook["判定历史"]
    assert tuple(cell.value for cell in history_sheet[1]) == (
        "版本号",
        "状态",
        "行业代码",
        "行业名称",
        "置信度",
        "匹配依据",
        "AI 总结",
        "关联异议",
    )
    assert tuple(cell.value for cell in history_sheet[2])[:4] == (
        1,
        "completed",
        "0111",
        "稻谷种植",
    )
    assert tuple(cell.value for cell in history_sheet[3]) == (
        2,
        "needs_review",
        None,
        None,
        None,
        "候选均不匹配",
        None,
        "主营收入结构已变化",
    )


def test_export_case_workbook_uses_readable_placeholder_without_completed_result() -> None:
    case = _case()
    NationalEconomyClassificationResult(
        case=case,
        version=1,
        status="needs_review",
        candidate_snapshot=[],
        rationale="需要人工复核",
    )

    workbook = load_workbook(BytesIO(export_case_workbook(case)))

    current_values = tuple(cell.value for cell in workbook["当前结论"][2])
    assert current_values[:3] == (None, None, None)
    assert current_values[3] == "暂无成功结论（案例状态：needs_review）"
