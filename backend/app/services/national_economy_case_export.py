import json
from io import BytesIO

from openpyxl import Workbook
from openpyxl.worksheet.worksheet import Worksheet

from app.models import (
    NationalEconomyClassificationCase,
    NationalEconomyClassificationResult,
)
from app.services.national_economy_case_ingestion import FIELD_LABELS
from app.services.national_economy_classification_workflow import (
    get_current_completed_result,
)


CASE_INPUT_SHEET = "案例输入"
CURRENT_RESULT_SHEET = "当前结论"
RESULT_HISTORY_SHEET = "判定历史"


def export_case_workbook(case: NationalEconomyClassificationCase) -> bytes:
    workbook = Workbook()
    input_sheet = workbook.active
    input_sheet.title = CASE_INPUT_SHEET
    _write_case_input(input_sheet, case)

    current_sheet = workbook.create_sheet(CURRENT_RESULT_SHEET)
    _write_current_result(current_sheet, case)

    history_sheet = workbook.create_sheet(RESULT_HISTORY_SHEET)
    _write_result_history(history_sheet, case)

    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def _write_case_input(sheet: Worksheet, case: NationalEconomyClassificationCase) -> None:
    sheet.append(("字段", "内容"))
    sheet.append(("业务场景", case.scenario))
    sheet.append(("原始文件名", case.original_filename or ""))
    sheet.append(("案例状态", case.status))
    for field, label in FIELD_LABELS.items():
        sheet.append((label, _cell_value(case.input_payload.get(field))))


def _write_current_result(
    sheet: Worksheet, case: NationalEconomyClassificationCase
) -> None:
    sheet.append(("行业代码", "行业名称", "置信度", "匹配依据", "AI 总结"))
    result = get_current_completed_result(case)
    if result is None:
        sheet.append(("", "", "", f"暂无成功结论（案例状态：{case.status}）", ""))
        return
    sheet.append(_result_values(result))


def _write_result_history(
    sheet: Worksheet, case: NationalEconomyClassificationCase
) -> None:
    sheet.append(
        (
            "版本号",
            "状态",
            "行业代码",
            "行业名称",
            "置信度",
            "匹配依据",
            "AI 总结",
            "关联异议",
        )
    )
    for result in sorted(case.result_versions, key=lambda item: item.version):
        sheet.append(
            (
                result.version,
                result.status,
                *_result_values(result),
                _objection_text(result.objection),
            )
        )


def _result_values(
    result: NationalEconomyClassificationResult,
) -> tuple[object, object, object, object, object]:
    return (
        _cell_value(result.industry_code),
        _cell_value(result.industry_name),
        _cell_value(result.confidence),
        _cell_value(result.rationale),
        _cell_value(result.ai_summary),
    )


def _objection_text(objection: dict[str, object] | None) -> str:
    if not objection:
        return ""
    description = objection.get("description")
    if description is not None:
        return str(description)
    return json.dumps(objection, ensure_ascii=False, sort_keys=True)


def _cell_value(value: object | None) -> object:
    return "" if value is None else value
