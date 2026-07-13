from collections.abc import Iterator
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.api.routes import national_economy as route_module
from app.core.config import get_settings
from app.db.session import get_db, get_sessionmaker
from app.main import app
from app.models import (
    FiveArticlesResult,
    NationalEconomyClassificationCase,
    NationalEconomyClassificationResult,
)
from app.services.scenario_registry import TECHNOLOGY_FINANCE_FIELD_SCHEMA
from app.services.technology_finance_classification_workflow import (
    TechnologyFinanceWorkflowResult,
)


FIXTURES = Path(__file__).parent / "fixtures" / "national_economy"
SCENARIO_ID = "technology_finance"


@pytest.fixture()
def db_session() -> Iterator[Session]:
    session = get_sessionmaker()()
    _clear_cases(session)
    try:
        yield session
    finally:
        session.rollback()
        _clear_cases(session)
        session.close()


@pytest.fixture()
def client(db_session: Session) -> Iterator[TestClient]:
    def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db, None)


def _clear_cases(session: Session) -> None:
    session.execute(delete(FiveArticlesResult))
    session.execute(delete(NationalEconomyClassificationResult))
    session.execute(delete(NationalEconomyClassificationCase))
    session.commit()


def _upload_technology_finance(client: TestClient):
    template_path = get_settings().technology_finance_template_path
    return client.post(
        f"/api/v1/scenarios/{SCENARIO_ID}/cases",
        files={
            "file": (
                template_path.name,
                template_path.read_bytes(),
                route_module.DOCX_MIME,
            )
        },
    )


def _upload_national_economy(client: TestClient):
    path = FIXTURES / "valid.docx"
    return client.post(
        "/api/v1/national-economy/cases",
        files={"file": (path.name, path.read_bytes(), route_module.DOCX_MIME)},
    )


def _persist_workflow_result(
    session: Session,
    case: NationalEconomyClassificationCase,
    *,
    version: int,
    objection_text: str | None = None,
) -> TechnologyFinanceWorkflowResult:
    stage_a = NationalEconomyClassificationResult(
        case_id=case.id,
        version=version,
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
        objection=(
            None if objection_text is None else {"description": objection_text}
        ),
        model_output={"stage": "a"},
    )
    session.add(stage_a)
    session.flush()
    stage_b = FiveArticlesResult(
        case_id=case.id,
        scenario_id=case.scenario,
        version=version,
        status="completed",
        stage_a_result_id=stage_a.id,
        mapping_version_id=None,
        labels=[
            {
                "subject": "高技术产业（制造业）",
                "taxonomy_path": ["医药制造业"],
                "NEIC_Code": "2710",
                "NEIC_Name": "化学药品原料药制造",
                "source_row": 12,
                "matching_basis": "贷款投向命中科技金融映射。",
                "evidence_refs": [],
            }
        ],
        loan_neic_code="2710",
        loan_neic_name="化学药品原料药制造",
        enterprise_neic_code="3011",
        enterprise_neic_name="水泥制造",
        consistency_status="consistent",
        consistency_basis="贷款用途服务于企业科技活动。",
        consistency_evidence_refs=[],
        model_output={"stage": "b"},
    )
    session.add(stage_b)
    case.status = "completed"
    session.commit()
    session.refresh(stage_a)
    session.refresh(stage_b)
    return TechnologyFinanceWorkflowResult(stage_a, stage_b)


def test_technology_finance_seven_endpoint_types(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    template_response = client.get(f"/api/v1/scenarios/{SCENARIO_ID}/template")
    assert template_response.status_code == 200
    assert template_response.content == (
        get_settings().technology_finance_template_path.read_bytes()
    )

    upload_response = _upload_technology_finance(client)
    assert upload_response.status_code == 201
    case_id = upload_response.json()["id"]

    detail_response = client.get(f"/api/v1/scenarios/{SCENARIO_ID}/cases/{case_id}")
    assert detail_response.status_code == 200
    assert [item["field"] for item in detail_response.json()["input_fields"]] == [
        field.key for field in TECHNOLOGY_FINANCE_FIELD_SCHEMA
    ]

    def fake_classify(session: Session, case: NationalEconomyClassificationCase):
        return _persist_workflow_result(session, case, version=1)

    monkeypatch.setattr(
        route_module,
        "classify_technology_finance_case",
        fake_classify,
    )
    classification_response = client.post(
        f"/api/v1/scenarios/{SCENARIO_ID}/cases/{case_id}/classifications"
    )
    assert classification_response.status_code == 200
    classification = classification_response.json()
    assert classification["stage_a"]["status"] == "completed"
    assert classification["stage_b"]["status"] == "completed"
    assert classification["stage_b"]["labels"][0]["source_row"] == 12
    assert classification["stage_b"]["consistency_status"] == "consistent"

    def fake_reclassify(
        session: Session,
        case: NationalEconomyClassificationCase,
        objection_text: str,
    ):
        return _persist_workflow_result(
            session,
            case,
            version=2,
            objection_text=objection_text,
        )

    monkeypatch.setattr(
        route_module,
        "reclassify_technology_finance_case",
        fake_reclassify,
    )
    objection_response = client.post(
        f"/api/v1/scenarios/{SCENARIO_ID}/cases/{case_id}/objections",
        json={"objection_text": "请按医药项目重新判定"},
    )
    assert objection_response.status_code == 200
    assert objection_response.json()["stage_a"]["version"] == 2
    assert objection_response.json()["stage_b"]["stage_a_result_id"] == (
        objection_response.json()["stage_a"]["id"]
    )

    history_response = client.get(
        f"/api/v1/scenarios/{SCENARIO_ID}/cases/{case_id}/history"
    )
    assert history_response.status_code == 200
    history = history_response.json()["items"]
    assert [item["version"] for item in history] == [1, 2]
    assert all(item["stage_a_result_id"] for item in history)

    export_response = client.get(
        f"/api/v1/scenarios/{SCENARIO_ID}/cases/{case_id}/export"
    )
    assert export_response.status_code == 200
    assert export_response.headers["content-type"] == route_module.XLSX_MIME
    workbook = load_workbook(BytesIO(export_response.content))
    assert workbook.sheetnames == ["案例输入", "当前结论", "判定历史"]
    exported_labels = {
        cell.value for cell in workbook["案例输入"]["A"] if cell.value is not None
    }
    assert {field.label for field in TECHNOLOGY_FINANCE_FIELD_SCHEMA} <= exported_labels


@pytest.mark.parametrize(
    "scenario_id",
    [
        "agriculture_related",
        "green_finance",
        "inclusive_finance",
        "pension_finance",
        "digital_finance",
    ],
)
def test_coming_soon_scenarios_are_rejected(
    client: TestClient,
    scenario_id: str,
) -> None:
    response = client.get(f"/api/v1/scenarios/{scenario_id}/template")

    assert response.status_code == 409
    assert response.json()["detail"] == "场景暂未开放"


def test_coming_soon_case_upload_is_rejected(client: TestClient) -> None:
    template_path = get_settings().technology_finance_template_path

    response = client.post(
        "/api/v1/scenarios/green_finance/cases",
        files={
            "file": (
                template_path.name,
                template_path.read_bytes(),
                route_module.DOCX_MIME,
            )
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"] == "场景暂未开放"


@pytest.mark.parametrize(
    ("method", "suffix", "json"),
    [
        ("GET", "", None),
        ("POST", "/classifications", None),
        ("POST", "/objections", {"objection_text": "场景错配"}),
        ("GET", "/history", None),
        ("GET", "/export", None),
    ],
)
def test_scenario_case_mismatch_is_rejected_before_workflow(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    suffix: str,
    json: dict[str, str] | None,
) -> None:
    national_case_id = _upload_national_economy(client).json()["id"]
    classifier = MagicMock()
    reclassifier = MagicMock()
    monkeypatch.setattr(route_module, "classify_technology_finance_case", classifier)
    monkeypatch.setattr(
        route_module,
        "reclassify_technology_finance_case",
        reclassifier,
    )

    response = client.request(
        method,
        f"/api/v1/scenarios/{SCENARIO_ID}/cases/{national_case_id}{suffix}",
        json=json,
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "案例不存在"
    classifier.assert_not_called()
    reclassifier.assert_not_called()


def test_unknown_scenario_is_not_treated_as_coming_soon(client: TestClient) -> None:
    response = client.get("/api/v1/scenarios/not_registered/template")

    assert response.status_code == 404
    assert response.json()["detail"] == "场景不存在"
