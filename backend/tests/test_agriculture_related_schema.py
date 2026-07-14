from datetime import datetime

from app.schemas.agriculture_related import AgricultureRelatedResultResponse
from app.schemas.inclusive_finance import InclusiveFinanceResultResponse


def test_result_response_localizes_legacy_farmer_identity_field_keys() -> None:
    field_key = "farmer_town_village_resident"
    basis = f"农户身份字段 {field_key} 的填写值为“是”，命中农户贷款类别。"

    result = AgricultureRelatedResultResponse.model_validate(
        {
            "id": 1,
            "version": 1,
            "status": "completed",
            "stage_a_result_id": 1,
            "is_agriculture_related": True,
            "matched_categories": [{"category": 1, "basis": basis}],
            "basis": basis,
            "evidence_refs": [],
            "model_output": None,
            "error_detail": None,
            "created_at": datetime(2026, 7, 14),
        }
    )

    expected = "农户身份字段 是否为城关镇所辖行政村住户 的填写值为“是”，命中农户贷款类别。"
    assert result.basis == expected
    assert result.matched_categories[0]["basis"] == expected
    assert field_key not in result.basis


def test_inclusive_result_response_localizes_borrower_type() -> None:
    result = InclusiveFinanceResultResponse.model_validate(
        {
            "id": 1,
            "version": 1,
            "status": "completed",
            "stage_a_result_id": 1,
            "borrower_type": "farmer",
            "computed_size": None,
            "filled_size": None,
            "size_consistent": None,
            "is_operating_loan": True,
            "credit_amount_wan": 500,
            "qualifies": True,
            "inclusive_category": "农户经营性贷款",
            "basis": "测试依据",
            "evidence_refs": [],
            "anomalies": [],
            "determination": None,
            "error_detail": None,
            "created_at": datetime(2026, 7, 14),
        }
    )

    assert result.borrower_type == "农户"
