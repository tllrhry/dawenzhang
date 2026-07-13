import json
from collections.abc import Mapping, Sequence
from io import BytesIO

from openpyxl import Workbook
from openpyxl.worksheet.worksheet import Worksheet

from app.models import (
    FiveArticlesResult,
    InclusiveFinanceResult,
    NationalEconomyClassificationCase,
    NationalEconomyClassificationResult,
)
from app.services.national_economy_case_ingestion import FIELD_LABELS
from app.services.national_economy_classification_workflow import (
    get_current_completed_result,
)
from app.services.national_economy_result_presentation import (
    format_industry_display_code,
)
from app.services.scenario_registry import (
    SCENARIO_REGISTRY,
    TECHNOLOGY_FINANCE_SCENARIO,
)


CASE_INPUT_SHEET = "案例输入"
CURRENT_RESULT_SHEET = "当前结论"
RESULT_HISTORY_SHEET = "判定历史"
TECHNOLOGY_FINANCE_RESULT_SHEET = "科技金融判定"
INCLUSIVE_FINANCE_RESULT_SHEET = "普惠金融判定"
TECHNOLOGY_FINANCE_CONSISTENCY_LABEL = (
    "贷款对应的五篇大文章类别与企业类别是否一致"
)

_TECHNOLOGY_FINANCE_HEADERS = (
    "Stage B版本",
    "科技金融状态",
    "状态说明",
    "Stage A结果ID",
    "贷款投向国民经济行业代码",
    "贷款投向国民经济行业名称",
    "企业国民经济行业代码",
    "企业国民经济行业名称",
    "主题",
    "第一层",
    "第二层",
    "第三层",
    "第四层",
    "映射代码",
    "映射名称",
    "映射源行",
    "匹配依据",
    "业务证据摘要",
    TECHNOLOGY_FINANCE_CONSISTENCY_LABEL,
    "一致性依据",
)

_RESULT_STATUS_LABELS = {
    "completed": "判定完成",
    "not_applicable": "不属于科技金融",
    "needs_review": "待人工复核",
    "classification_failed": "判定失败",
}

_CONSISTENCY_STATUS_LABELS = {
    "consistent": "一致",
    "inconsistent": "不一致",
    "needs_review": "待人工复核",
    "not_applicable": "不适用",
}


def export_case_workbook(
    case: NationalEconomyClassificationCase,
    *,
    five_articles_results: Sequence[FiveArticlesResult] = (),
    inclusive_finance_results: Sequence[InclusiveFinanceResult] = (),
) -> bytes:
    workbook = Workbook()
    input_sheet = workbook.active
    input_sheet.title = CASE_INPUT_SHEET
    _write_case_input(input_sheet, case)

    current_sheet = workbook.create_sheet(CURRENT_RESULT_SHEET)
    _write_current_result(current_sheet, case)

    history_sheet = workbook.create_sheet(RESULT_HISTORY_SHEET)
    _write_result_history(history_sheet, case)

    if case.scenario == TECHNOLOGY_FINANCE_SCENARIO:
        technology_finance_sheet = workbook.create_sheet(
            TECHNOLOGY_FINANCE_RESULT_SHEET
        )
        _write_technology_finance_result(
            technology_finance_sheet,
            five_articles_results,
        )
    if case.scenario == "inclusive_finance":
        sheet = workbook.create_sheet(INCLUSIVE_FINANCE_RESULT_SHEET)
        _write_inclusive_finance_result(sheet, inclusive_finance_results)

    output = BytesIO()
    workbook.save(output)
    return output.getvalue()

def _write_inclusive_finance_result(sheet: Worksheet, results: Sequence[InclusiveFinanceResult]) -> None:
    headers = ("Stage B版本", "普惠状态", "借款主体", "计算划型", "填报划型", "划型一致性", "是否经营性", "授信金额(万元)", "是否属于普惠", "普惠子类别", "判定依据", "业务证据摘要", "异常")
    sheet.append(headers)
    if not results:
        sheet.append(("", "尚未判定", "", "", "", "", "", "", "", "", "尚无普惠金融判定结果。", "", "")); return
    result = max(results, key=lambda item: (item.version, item.id or 0))
    evidence = "\n".join(f"{ref.get('field_key', ref.get('field', '证据'))}：{ref.get('raw_value', '')}" for ref in result.evidence_refs if isinstance(ref, dict))
    anomalies = "\n".join(str(item.get("message", item)) for item in result.anomalies if isinstance(item, dict))
    sheet.append((result.version, _RESULT_STATUS_LABELS.get(result.status, result.status), result.borrower_type, result.computed_size, result.filled_size, "一致" if result.size_consistent else ("不一致" if result.size_consistent is False else "未判定"), "是" if result.is_operating_loan else ("否" if result.is_operating_loan is False else "未判定"), result.credit_amount_wan, "是" if result.qualifies else ("否" if result.qualifies is False else "未判定"), result.inclusive_category, result.basis, evidence, anomalies))


def _write_technology_finance_result(
    sheet: Worksheet,
    results: Sequence[FiveArticlesResult],
) -> None:
    sheet.append(_TECHNOLOGY_FINANCE_HEADERS)
    if not results:
        sheet.append(
            (
                "",
                "尚未判定",
                "尚无科技金融判定结果。",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "不适用",
                "尚无科技金融判定结果，一致性不适用。",
            )
        )
        return

    current = max(results, key=lambda result: (result.version, result.id or 0))
    status_label = _RESULT_STATUS_LABELS.get(current.status, current.status)
    status_detail = _technology_finance_status_detail(current)
    consistency_label = _consistency_status_label(current)
    consistency_basis = _consistency_basis(current)
    common_values = (
        current.version,
        status_label,
        status_detail,
        current.stage_a_result_id,
        _cell_value(current.loan_neic_code),
        _cell_value(current.loan_neic_name),
        _cell_value(current.enterprise_neic_code),
        _cell_value(current.enterprise_neic_name),
    )

    if current.status != "completed" or not current.labels:
        sheet.append(
            (
                *common_values,
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                "",
                consistency_label,
                consistency_basis,
            )
        )
        return

    for label in current.labels:
        taxonomy = _label_taxonomy(label)
        sheet.append(
            (
                *common_values,
                *taxonomy,
                _cell_value(label.get("NEIC_Code", label.get("code"))),
                _cell_value(label.get("NEIC_Name", label.get("name"))),
                _cell_value(label.get("source_row")),
                _cell_value(label.get("matching_basis")),
                _business_evidence_summary(label.get("evidence_refs")),
                consistency_label,
                consistency_basis,
            )
        )


def _technology_finance_status_detail(result: FiveArticlesResult) -> str:
    if result.status == "completed":
        return "科技金融判定完成。"
    if result.status == "not_applicable":
        return "贷款投向未命中已发布科技金融映射，不属于科技金融。"
    if result.status == "needs_review":
        detail = result.error_detail or result.consistency_basis
        return f"科技金融判定需人工复核：{detail or '映射或证据需要人工确认。'}"
    if result.status == "classification_failed":
        return f"科技金融判定失败：{result.error_detail or '未提供失败详情。'}"
    return result.error_detail or f"科技金融判定状态：{result.status}"


def _consistency_status_label(result: FiveArticlesResult) -> str:
    if result.status == "classification_failed":
        return "不适用"
    return _CONSISTENCY_STATUS_LABELS.get(
        result.consistency_status or "not_applicable",
        result.consistency_status or "不适用",
    )


def _consistency_basis(result: FiveArticlesResult) -> str:
    if result.status == "completed":
        return result.consistency_basis or "未提供一致性依据。"
    if result.status == "not_applicable":
        return (
            result.consistency_basis
            or "当前贷款投向不属于科技金融，一致性不适用。"
        )
    if result.status == "needs_review":
        detail = result.consistency_basis or result.error_detail
        return (
            "当前无正式科技金融标签，一致性比较不适用；"
            f"{detail or '映射或证据需人工复核。'}"
        )
    if result.status == "classification_failed":
        return "科技金融判定失败，未形成正式标签，一致性不适用。"
    return "当前无正式科技金融标签，一致性不适用。"


def _label_taxonomy(label: Mapping[str, object]) -> tuple[object, ...]:
    raw_path = label.get("taxonomy_path")
    if isinstance(raw_path, list):
        path = raw_path[:4]
        return (
            _cell_value(label.get("subject")),
            *(_cell_value(item) for item in path),
            *("" for _ in range(4 - len(path))),
        )

    raw_taxonomy = label.get("taxonomy")
    taxonomy = raw_taxonomy if isinstance(raw_taxonomy, dict) else {}
    return (
        _cell_value(taxonomy.get("subject", label.get("subject"))),
        *(_cell_value(taxonomy.get(f"tier{level}")) for level in range(1, 5)),
    )


def _business_evidence_summary(raw_refs: object) -> str:
    if not isinstance(raw_refs, list):
        return ""
    summaries = []
    for ref in raw_refs:
        if not isinstance(ref, dict) or ref.get("type") != "business":
            continue
        label = ref.get("field_label") or ref.get("field_key") or "业务证据"
        excerpt = ref.get("excerpt")
        if excerpt is not None:
            summaries.append(f"{label}：{excerpt}")
    return "\n".join(summaries)


def _write_case_input(sheet: Worksheet, case: NationalEconomyClassificationCase) -> None:
    sheet.append(("字段", "内容"))
    sheet.append(("业务场景", case.scenario))
    sheet.append(("原始文件名", case.original_filename or ""))
    sheet.append(("案例状态", case.status))
    registration = SCENARIO_REGISTRY.get(case.scenario)
    field_labels = (
        tuple((field.key, field.label) for field in registration.field_schema)
        if registration is not None
        else tuple(FIELD_LABELS.items())
    )
    for field, label in field_labels:
        sheet.append((label, _cell_value(case.input_payload.get(field))))


def _write_current_result(
    sheet: Worksheet, case: NationalEconomyClassificationCase
) -> None:
    sheet.append(
        (
            "行业代码",
            "行业名称",
            "匹配依据",
            "贷款投向代码",
            "贷款投向名称",
            "贷款投向匹配依据",
            "贷款投向是否一致",
        )
    )
    result = get_current_completed_result(case)
    if result is None:
        sheet.append(
            ("", "", f"暂无成功结论（案例状态：{case.status}）", "", "", "", "")
        )
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
            "匹配依据",
            "贷款投向代码",
            "贷款投向名称",
            "贷款投向匹配依据",
            "贷款投向是否一致",
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
) -> tuple[object, object, object, object, object, object, object]:
    if result.loan_industry_code is None and result.loan_matching_basis is None:
        loan_code = result.industry_code
        loan_major_code = result.industry_major_code
        loan_name = result.industry_name if result.industry_code is not None else None
        loan_basis = "贷款投向未单独评估，与企业主营一致"
        loan_matches = "一致"
    elif result.loan_industry_code is None:
        loan_code = None
        loan_major_code = None
        loan_name = None
        loan_basis = result.loan_matching_basis
        loan_matches = "不一致"
    else:
        loan_code = result.loan_industry_code
        loan_major_code = result.loan_industry_major_code
        loan_name = result.loan_industry_name
        loan_basis = result.loan_matching_basis
        loan_matches = "一致" if result.loan_matches_enterprise is True else "不一致"

    return (
        _cell_value(
            format_industry_display_code(
                result.industry_major_code,
                result.industry_code,
            )
        ),
        _cell_value(result.industry_name),
        _cell_value(result.rationale),
        _cell_value(format_industry_display_code(loan_major_code, loan_code)),
        _cell_value(loan_name),
        _cell_value(loan_basis),
        loan_matches,
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
