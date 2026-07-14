from io import BytesIO

from openpyxl import load_workbook

from app.models import InclusiveFinanceResult, NationalEconomyClassificationCase
from app.services.national_economy_case_export import export_case_workbook


def test_inclusive_finance_export_uses_chinese_borrower_and_evidence_labels() -> None:
    case = NationalEconomyClassificationCase(
        id=1,
        scenario="inclusive_finance",
        original_filename="普惠测试.docx",
        input_payload={},
        status="completed",
    )
    result = InclusiveFinanceResult(
        id=1,
        case=case,
        scenario_id="inclusive_finance",
        version=1,
        status="completed",
        stage_a_result_id=1,
        borrower_type="farmer",
        is_operating_loan=True,
        credit_amount_wan=500,
        qualifies=True,
        inclusive_category="农户经营性贷款",
        basis="测试依据",
        evidence_refs=[
            {
                "type": "field",
                "field_key": "credit_approval_opinion",
                "raw_value": "支持生产经营周转",
            }
        ],
        anomalies=[],
    )

    workbook = load_workbook(
        BytesIO(export_case_workbook(case, inclusive_finance_results=[result]))
    )
    row = next(workbook["普惠金融判定"].iter_rows(min_row=2, values_only=True))

    assert row[2] == "农户"
    assert row[11] == "授信审批意见：支持生产经营周转"
