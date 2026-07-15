from io import BytesIO

import pytest
from openpyxl import load_workbook

from app.models import (
    FiveArticlesResult,
    NationalEconomyClassificationCase,
    NationalEconomyClassificationResult,
)
from app.services.national_economy_case_export import export_case_workbook
from app.services.scenario_registry import (
    DIGITAL_FINANCE_REGISTRATION,
    GREEN_FINANCE_REGISTRATION,
    PENSION_FINANCE_REGISTRATION,
    TECHNOLOGY_FINANCE_FIELD_SCHEMA,
    TECHNOLOGY_FINANCE_SCENARIO,
    ScenarioRegistration,
)


def _case_with_stage_a(
    *,
    stage_a_id: int = 11,
    stage_a_version: int = 1,
) -> tuple[NationalEconomyClassificationCase, NationalEconomyClassificationResult]:
    case = NationalEconomyClassificationCase(
        id=1,
        scenario=TECHNOLOGY_FINANCE_SCENARIO,
        original_filename="科技金融案例.docx",
        input_payload={
            field.key: f"{field.label}内容" for field in TECHNOLOGY_FINANCE_FIELD_SCHEMA
        },
        status="completed",
    )
    stage_a = NationalEconomyClassificationResult(
        id=stage_a_id,
        case=case,
        version=stage_a_version,
        status="completed",
        industry_code="3011",
        industry_major_code="C30",
        industry_name="水泥制造",
        loan_industry_code="2710",
        loan_industry_major_code="C27",
        loan_industry_name="化学药品原料药制造",
        loan_matching_basis="贷款用于医药项目建设",
        loan_matches_enterprise=False,
        rationale="企业主营命中国民经济行业目录",
        candidate_snapshot=[],
    )
    return case, stage_a


def _completed_stage_b(
    *,
    stage_a_result_id: int,
    consistency_status: str,
) -> FiveArticlesResult:
    return FiveArticlesResult(
        id=21,
        case_id=1,
        scenario_id=TECHNOLOGY_FINANCE_SCENARIO,
        version=1,
        status="completed",
        stage_a_result_id=stage_a_result_id,
        mapping_version_id=3,
        labels=[
            {
                "mapping_version_id": 3,
                "subject": "高技术产业（制造业）",
                "taxonomy_path": [
                    "医药制造业",
                    "化学药品制造",
                    "原料药制造",
                    "创新药原料",
                ],
                "NEIC_Code": "2710",
                "NEIC_Name": "化学药品原料药制造",
                "source_row": 12,
                "matching_basis": "贷款用于创新药原料项目，命中科技金融映射。",
                "evidence_refs": [
                    {
                        "type": "mapping",
                        "mapping_version_id": 3,
                        "source_row": 12,
                        "NEIC_Code": "2710",
                        "NEIC_Name": "化学药品原料药制造",
                        "taxonomy_path": [
                            "医药制造业",
                            "化学药品制造",
                            "原料药制造",
                            "创新药原料",
                        ],
                    },
                    {
                        "type": "business",
                        "field_key": "loan_purpose",
                        "field_label": "贷款用途详细描述",
                        "excerpt": "用于创新药原料项目建设",
                    },
                    {
                        "type": "business",
                        "field_key": "qualification_certification",
                        "field_label": "企业核心资质与认证",
                        "excerpt": "高新技术企业认证",
                    },
                ],
            },
            {
                "mapping_version_id": 3,
                "subject": "战略性新兴产业",
                "taxonomy_path": ["生物产业", "生物医药产业"],
                "NEIC_Code": "27",
                "NEIC_Name": "医药制造业",
                "source_row": 28,
                "matching_basis": "贷款投向命中显式医药制造业大类映射。",
                "evidence_refs": [
                    {
                        "type": "mapping",
                        "mapping_version_id": 3,
                        "source_row": 28,
                        "NEIC_Code": "27",
                        "NEIC_Name": "医药制造业",
                        "taxonomy_path": ["生物产业", "生物医药产业"],
                    },
                    {
                        "type": "business",
                        "field_key": "stage_a.loan_matching_basis",
                        "field_label": "Stage A 贷款投向匹配依据",
                        "excerpt": "贷款用于医药项目建设",
                    },
                ],
            },
        ],
        loan_neic_code="2710",
        loan_neic_name="化学药品原料药制造",
        enterprise_neic_code="3011",
        enterprise_neic_name="水泥制造",
        consistency_status=consistency_status,
        consistency_basis="已综合企业类别、贷款用途与 Stage A 投向证据判断。",
        consistency_evidence_refs=[],
    )


@pytest.mark.parametrize(
    ("consistency_status", "display_name"),
    [
        ("consistent", "一致"),
        ("inconsistent", "不一致"),
        ("needs_review", "待人工复核"),
    ],
)
def test_completed_export_reads_back_multi_labels_sources_evidence_and_consistency(
    consistency_status: str,
    display_name: str,
) -> None:
    case, stage_a = _case_with_stage_a()
    stage_b = _completed_stage_b(
        stage_a_result_id=stage_a.id,
        consistency_status=consistency_status,
    )

    workbook = load_workbook(
        BytesIO(
            export_case_workbook(
                case,
                five_articles_results=[stage_b],
            )
        )
    )

    assert workbook.sheetnames == [
        "案例输入",
        "当前结论",
        "判定历史",
        "科技金融判定",
    ]
    input_rows = dict(workbook["案例输入"].iter_rows(min_row=2, values_only=True))
    assert {field.label for field in TECHNOLOGY_FINANCE_FIELD_SCHEMA} <= set(input_rows)

    sheet = workbook["科技金融判定"]
    headers = tuple(cell.value for cell in sheet[1])
    rows = [
        dict(zip(headers, row, strict=True))
        for row in sheet.iter_rows(min_row=2, values_only=True)
    ]
    assert len(rows) == 2
    assert rows[0]["主题"] == "高技术产业（制造业）"
    assert [rows[0][f"第{name}层"] for name in ("一", "二", "三", "四")] == [
        "医药制造业",
        "化学药品制造",
        "原料药制造",
        "创新药原料",
    ]
    assert rows[1]["第三层"] is None
    assert [row["映射源行"] for row in rows] == [12, 28]
    assert rows[0]["映射代码"] == "2710"
    assert rows[0]["映射名称"] == "化学药品原料药制造"
    assert rows[0]["业务证据摘要"] == (
        "贷款用途详细描述：用于创新药原料项目建设\n"
        "企业核心资质与认证：高新技术企业认证"
    )
    assert "mapping" not in rows[0]["业务证据摘要"]
    assert rows[0]["Stage A结果ID"] == stage_a.id
    assert all(
        row["贷款对应的五篇大文章类别与企业类别是否一致"] == display_name
        for row in rows
    )
    assert all(row["一致性依据"] == stage_b.consistency_basis for row in rows)


def test_export_writes_ip_intensive_industry_condition_per_label() -> None:
    case, stage_a = _case_with_stage_a()
    stage_b = _completed_stage_b(
        stage_a_result_id=stage_a.id,
        consistency_status="consistent",
    )
    stage_b.labels[0] = {
        **stage_b.labels[0],
        "subject": "知识产权(专利)密集型产业",
        "ip_intensive_industry_status": "satisfied",
        "ip_intensive_industry_basis": "企业名称已在名录中匹配到。",
    }
    stage_b.labels[1] = {
        **stage_b.labels[1],
        "subject": "知识产权(专利)密集型产业",
        "ip_intensive_industry_status": "unsatisfied",
        "ip_intensive_industry_basis": "企业名称未在名录中匹配到。",
    }

    workbook = load_workbook(
        BytesIO(export_case_workbook(case, five_articles_results=[stage_b]))
    )
    sheet = workbook["科技金融判定"]
    headers = tuple(cell.value for cell in sheet[1])
    rows = [
        dict(zip(headers, row, strict=True))
        for row in sheet.iter_rows(min_row=2, values_only=True)
    ]

    assert rows[0]["知识产权条件"] == "满足"
    assert rows[1]["知识产权条件"] == "不满足：企业名称未在名录中匹配到。"


@pytest.mark.parametrize(
    (
        "result_status",
        "consistency_status",
        "status_label",
        "consistency_label",
        "error_detail",
    ),
    [
        (
            "not_applicable",
            "not_applicable",
            "不属于科技金融",
            "不适用",
            "loan_direction_has_no_explicit_mapping",
        ),
        (
            "needs_review",
            "needs_review",
            "待人工复核",
            "待人工复核",
            "published_mapping_version_not_found",
        ),
        (
            "classification_failed",
            None,
            "判定失败",
            "不适用",
            "DeepSeek request timed out",
        ),
    ],
)
def test_export_without_formal_labels_has_readable_status_and_stage_a_context(
    result_status: str,
    consistency_status: str | None,
    status_label: str,
    consistency_label: str,
    error_detail: str,
) -> None:
    case, stage_a = _case_with_stage_a()
    stage_b = FiveArticlesResult(
        id=22,
        case_id=case.id,
        scenario_id=case.scenario,
        version=2,
        status=result_status,
        stage_a_result_id=stage_a.id,
        mapping_version_id=3,
        labels=[],
        loan_neic_code="2710",
        loan_neic_name="化学药品原料药制造",
        enterprise_neic_code="3011",
        enterprise_neic_name="水泥制造",
        consistency_status=consistency_status,
        consistency_basis=(
            "贷款投向未命中映射，一致性不适用。"
            if result_status == "not_applicable"
            else "科技金融映射数据异常，需人工复核。"
        ),
        consistency_evidence_refs=[],
        error_detail=error_detail,
    )

    workbook = load_workbook(
        BytesIO(export_case_workbook(case, five_articles_results=[stage_b]))
    )
    sheet = workbook["科技金融判定"]
    headers = tuple(cell.value for cell in sheet[1])
    row = dict(zip(headers, tuple(cell.value for cell in sheet[2]), strict=True))

    assert row["科技金融状态"] == status_label
    assert row["状态说明"]
    assert row["主题"] is None
    assert row["映射源行"] is None
    assert row["Stage A结果ID"] == stage_a.id
    assert row["贷款投向国民经济行业代码"] == "2710"
    assert row["企业国民经济行业名称"] == "水泥制造"
    assert row["贷款对应的五篇大文章类别与企业类别是否一致"] == (
        consistency_label
    )
    assert "不适用" in row["一致性依据"]


def test_export_uses_latest_stage_b_version_and_its_stage_a_association() -> None:
    case, first_stage_a = _case_with_stage_a()
    second_stage_a = NationalEconomyClassificationResult(
        id=12,
        case=case,
        version=2,
        status="completed",
        industry_code="2710",
        industry_name="化学药品原料药制造",
        loan_industry_code="2720",
        loan_industry_name="化学药品制剂制造",
        loan_matching_basis="异议后按制剂项目判定",
        rationale="异议重判后的 Stage A 依据",
        candidate_snapshot=[],
    )
    older = _completed_stage_b(
        stage_a_result_id=first_stage_a.id,
        consistency_status="consistent",
    )
    latest = FiveArticlesResult(
        id=23,
        case_id=case.id,
        scenario_id=case.scenario,
        version=2,
        status="classification_failed",
        stage_a_result_id=second_stage_a.id,
        labels=[],
        loan_neic_code="2720",
        loan_neic_name="化学药品制剂制造",
        enterprise_neic_code="2710",
        enterprise_neic_name="化学药品原料药制造",
        consistency_evidence_refs=[],
        error_detail="模型输出校验失败",
    )

    workbook = load_workbook(
        BytesIO(
            export_case_workbook(
                case,
                five_articles_results=[latest, older],
            )
        )
    )
    sheet = workbook["科技金融判定"]
    headers = tuple(cell.value for cell in sheet[1])
    row = dict(zip(headers, tuple(cell.value for cell in sheet[2]), strict=True))

    assert row["Stage B版本"] == 2
    assert row["Stage A结果ID"] == second_stage_a.id
    assert row["贷款投向国民经济行业代码"] == "2720"
    assert row["科技金融状态"] == "判定失败"


@pytest.mark.parametrize(
    "profile",
    [
        GREEN_FINANCE_REGISTRATION,
        DIGITAL_FINANCE_REGISTRATION,
        PENSION_FINANCE_REGISTRATION,
    ],
    ids=lambda profile: profile.id,
)
@pytest.mark.parametrize(
    ("result_status", "status_label"),
    [
        ("completed", "判定完成"),
        ("not_applicable", None),
        ("needs_review", "待人工复核"),
        ("classification_failed", "判定失败"),
    ],
)
def test_new_finance_export_uses_profile_sheet_and_readable_statuses(
    profile: ScenarioRegistration,
    result_status: str,
    status_label: str | None,
) -> None:
    case = NationalEconomyClassificationCase(
        id=1,
        scenario=profile.id,
        original_filename=f"{profile.name}案例.docx",
        input_payload={
            field.key: f"{field.label}内容" for field in profile.field_schema
        },
        status="completed",
    )
    stage_a = NationalEconomyClassificationResult(
        id=11,
        case=case,
        version=1,
        status="completed",
        industry_code="3011",
        industry_name="水泥制造",
        loan_industry_code="2710",
        loan_industry_name="化学药品原料药制造",
        loan_matching_basis="贷款用于项目建设",
        rationale="企业主营命中国民经济行业目录",
        candidate_snapshot=[],
    )
    labels = (
        [
            {
                "subject": f"{profile.name}主题",
                "taxonomy_path": ["第一层", "第二层"],
                "NEIC_Code": "2710",
                "NEIC_Name": "化学药品原料药制造",
                "source_row": 12,
                "matching_basis": f"命中{profile.name}映射。",
                "evidence_refs": [
                    {
                        "type": "business",
                        "field_key": "loan_purpose",
                        "field_label": "贷款用途详细描述",
                        "excerpt": "用于项目建设",
                    }
                ],
            }
        ]
        if result_status == "completed"
        else []
    )
    stage_b = FiveArticlesResult(
        id=21,
        case_id=case.id,
        scenario_id=profile.id,
        version=1,
        status=result_status,
        stage_a_result_id=stage_a.id,
        mapping_version_id=3,
        labels=labels,
        loan_neic_code="2710",
        loan_neic_name="化学药品原料药制造",
        enterprise_neic_code="3011",
        enterprise_neic_name="水泥制造",
        consistency_status=(
            "consistent" if result_status == "completed" else "not_applicable"
        ),
        consistency_basis="已综合场景业务证据判断。",
        consistency_evidence_refs=[],
        error_detail="需要人工确认" if result_status == "needs_review" else None,
    )

    workbook = load_workbook(
        BytesIO(
            export_case_workbook(
                case,
                five_articles_results=[stage_b],
                profile=profile,
            )
        )
    )

    assert profile.export_sheet_name in workbook.sheetnames
    assert {"案例输入", "当前结论", "判定历史"} <= set(workbook.sheetnames)
    sheet = workbook[profile.export_sheet_name]
    headers = tuple(cell.value for cell in sheet[1])
    row = dict(zip(headers, tuple(cell.value for cell in sheet[2]), strict=True))
    assert row[f"{profile.name}状态"] == (
        status_label or f"不属于{profile.name}"
    )
    assert row["Stage A结果ID"] == stage_a.id
    assert profile.name in row["状态说明"]
    if result_status == "completed":
        assert row["映射源行"] == 12
        assert row["业务证据摘要"] == "贷款用途详细描述：用于项目建设"
        assert row["一致性依据"] == stage_b.consistency_basis
    else:
        assert row["映射源行"] is None
        assert row["业务证据摘要"] is None
        assert row["一致性依据"]
