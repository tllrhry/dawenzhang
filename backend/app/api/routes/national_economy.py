from io import BytesIO
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.session import get_db
from app.models import FiveArticlesResult, NationalEconomyClassificationCase
from app.schemas.five_articles import (
    FiveArticlesHistoryResponse,
    FiveArticlesResultResponse,
    TechnologyFinanceWorkflowResponse,
)
from app.schemas.national_economy import (
    CaseCreatedResponse,
    CaseInputField,
    CaseResponse,
    ClassificationResultResponse,
    ObjectionRequest,
    ResultHistoryResponse,
    ScenarioListResponse,
)
from app.services.national_economy_case_export import export_case_workbook
from app.services.national_economy_case_ingestion import (
    FIELD_LABELS,
    SCENARIO,
    NationalEconomyTemplateError,
    create_case_from_template,
    read_template_bytes,
)
from app.services.national_economy_classification_workflow import (
    classify_case,
    get_current_completed_result,
    reclassify_case,
)
from app.services.scenario_registry import (
    SCENARIO_REGISTRY,
    ScenarioRegistration,
)
from app.services.technology_finance_case_ingestion import (
    create_technology_finance_case_from_template,
)
from app.services.technology_finance_classification_workflow import (
    TechnologyFinanceWorkflowResult,
    classify_technology_finance_case,
    reclassify_technology_finance_case,
)


DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

router = APIRouter(tags=["national-economy"])


@router.get("/scenarios", response_model=ScenarioListResponse)
def list_scenarios() -> dict[str, object]:
    return {
        "items": [
            {
                "id": SCENARIO,
                "name": "国民经济行业分类",
                "status": "available",
                "description": "上传单企业 Word 模板并生成四级行业分类结论",
            },
            {
                "id": "agriculture_related",
                "name": "涉农业务",
                "status": "coming_soon",
                "description": "暂未开放",
            },
            {
                "id": "five_major_articles",
                "name": "五篇大文章",
                "status": "coming_soon",
                "description": "暂未开放",
            },
            *[
                {
                    "id": registration.id,
                    "name": registration.name,
                    "status": registration.status,
                    "description": registration.description,
                    "parent_id": registration.parent_id,
                }
                for registration in SCENARIO_REGISTRY.values()
                if registration.parent_id == "five_major_articles"
            ],
        ]
    }


@router.get("/scenarios/national-economy/template")
def download_template() -> StreamingResponse:
    return _download_response(
        read_template_bytes(),
        DOCX_MIME,
        "national-economy-template.docx",
    )


@router.get("/scenarios/{scenario_id}/template")
def download_scenario_template(scenario_id: str) -> StreamingResponse:
    registration = _get_available_scenario(scenario_id)
    return _download_response(
        registration.template_path().read_bytes(),
        DOCX_MIME,
        f"{scenario_id.replace('_', '-')}-template.docx",
    )


@router.post(
    "/national-economy/cases",
    response_model=CaseCreatedResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_case(
    file: UploadFile = File(...),
    session: Session = Depends(get_db),
) -> CaseCreatedResponse:
    filename = Path(file.filename or "").name
    if not filename.lower().endswith(".docx"):
        raise HTTPException(status_code=422, detail="请上传单个 .docx 文件")
    document_bytes = await file.read()
    try:
        case = create_case_from_template(session, document_bytes, filename)
    except NationalEconomyTemplateError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "message": str(exc),
                "missing": list(exc.issues.missing),
                "duplicate": list(exc.issues.duplicate),
                "unrecognized": list(exc.issues.unrecognized),
            },
        ) from exc
    return CaseCreatedResponse.model_validate(case, from_attributes=True)


@router.post(
    "/scenarios/{scenario_id}/cases",
    response_model=CaseCreatedResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_scenario_case(
    scenario_id: str,
    file: UploadFile = File(...),
    session: Session = Depends(get_db),
) -> CaseCreatedResponse:
    _get_available_scenario(scenario_id)
    filename = Path(file.filename or "").name
    if not filename.lower().endswith(".docx"):
        raise HTTPException(status_code=422, detail="请上传单个 .docx 文件")
    document_bytes = await file.read()
    try:
        case = create_technology_finance_case_from_template(
            session,
            document_bytes,
            filename,
        )
    except NationalEconomyTemplateError as exc:
        raise HTTPException(
            status_code=422,
            detail={
                "message": str(exc),
                "missing": list(exc.issues.missing),
                "duplicate": list(exc.issues.duplicate),
                "unrecognized": list(exc.issues.unrecognized),
            },
        ) from exc
    return CaseCreatedResponse.model_validate(case, from_attributes=True)


@router.get("/national-economy/cases/{case_id}", response_model=CaseResponse)
def get_case(case_id: int, session: Session = Depends(get_db)) -> CaseResponse:
    return _case_response(_get_case(session, case_id))


@router.get(
    "/scenarios/{scenario_id}/cases/{case_id}",
    response_model=CaseResponse,
)
def get_scenario_case(
    scenario_id: str,
    case_id: int,
    session: Session = Depends(get_db),
) -> CaseResponse:
    return _case_response(_get_scenario_case(session, scenario_id, case_id))


@router.post(
    "/national-economy/cases/{case_id}/classifications",
    response_model=ClassificationResultResponse,
)
def classify(case_id: int, session: Session = Depends(get_db)) -> object:
    case = _get_case(session, case_id)
    try:
        return classify_case(session, case)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"message": "分类服务暂时不可用，请稍后重试", "error": str(exc)},
        ) from exc


@router.post(
    "/national-economy/cases/{case_id}/objections",
    response_model=ClassificationResultResponse,
)
def object_to_classification(
    case_id: int,
    payload: ObjectionRequest,
    session: Session = Depends(get_db),
) -> object:
    objection_text = payload.objection_text.strip()
    if not objection_text:
        raise HTTPException(status_code=422, detail="异议说明不能为空")
    case = _get_case(session, case_id)
    try:
        return reclassify_case(session, case, objection_text)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"message": "异议重判暂时不可用，请稍后重试", "error": str(exc)},
        ) from exc


@router.get(
    "/national-economy/cases/{case_id}/history",
    response_model=ResultHistoryResponse,
)
def get_history(
    case_id: int,
    session: Session = Depends(get_db),
) -> ResultHistoryResponse:
    case = _get_case(session, case_id)
    return ResultHistoryResponse(
        items=[
            ClassificationResultResponse.model_validate(result)
            for result in sorted(case.result_versions, key=lambda item: item.version)
        ]
    )


@router.get("/national-economy/cases/{case_id}/export")
def export_case(case_id: int, session: Session = Depends(get_db)) -> StreamingResponse:
    case = _get_case(session, case_id)
    return _download_response(
        export_case_workbook(case),
        XLSX_MIME,
        f"national-economy-case-{case.id}.xlsx",
    )


@router.post(
    "/scenarios/{scenario_id}/cases/{case_id}/classifications",
    response_model=TechnologyFinanceWorkflowResponse,
)
def classify_scenario_case(
    scenario_id: str,
    case_id: int,
    session: Session = Depends(get_db),
) -> TechnologyFinanceWorkflowResponse:
    case = _get_scenario_case(session, scenario_id, case_id)
    try:
        outcome = classify_technology_finance_case(session, case)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"message": "分类服务暂时不可用，请稍后重试", "error": str(exc)},
        ) from exc
    return _technology_finance_workflow_response(outcome)


@router.post(
    "/scenarios/{scenario_id}/cases/{case_id}/objections",
    response_model=TechnologyFinanceWorkflowResponse,
)
def object_to_scenario_classification(
    scenario_id: str,
    case_id: int,
    payload: ObjectionRequest,
    session: Session = Depends(get_db),
) -> TechnologyFinanceWorkflowResponse:
    case = _get_scenario_case(session, scenario_id, case_id)
    objection_text = payload.objection_text.strip()
    if not objection_text:
        raise HTTPException(status_code=422, detail="异议说明不能为空")
    try:
        outcome = reclassify_technology_finance_case(
            session,
            case,
            objection_text,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={"message": "异议重判暂时不可用，请稍后重试", "error": str(exc)},
        ) from exc
    return _technology_finance_workflow_response(outcome)


@router.get(
    "/scenarios/{scenario_id}/cases/{case_id}/history",
    response_model=FiveArticlesHistoryResponse,
)
def get_scenario_history(
    scenario_id: str,
    case_id: int,
    session: Session = Depends(get_db),
) -> FiveArticlesHistoryResponse:
    case = _get_scenario_case(session, scenario_id, case_id)
    results = session.scalars(
        select(FiveArticlesResult)
        .where(FiveArticlesResult.case_id == case.id)
        .order_by(FiveArticlesResult.version, FiveArticlesResult.id)
    ).all()
    return FiveArticlesHistoryResponse(
        items=[FiveArticlesResultResponse.model_validate(result) for result in results]
    )


@router.get("/scenarios/{scenario_id}/cases/{case_id}/export")
def export_scenario_case(
    scenario_id: str,
    case_id: int,
    session: Session = Depends(get_db),
) -> StreamingResponse:
    case = _get_scenario_case(session, scenario_id, case_id)
    five_articles_results = session.scalars(
        select(FiveArticlesResult)
        .where(FiveArticlesResult.case_id == case.id)
        .order_by(FiveArticlesResult.version, FiveArticlesResult.id)
    ).all()
    return _download_response(
        export_case_workbook(
            case,
            five_articles_results=five_articles_results,
        ),
        XLSX_MIME,
        f"{scenario_id.replace('_', '-')}-case-{case.id}.xlsx",
    )


def _get_case(session: Session, case_id: int) -> NationalEconomyClassificationCase:
    case = session.scalar(
        select(NationalEconomyClassificationCase)
        .where(NationalEconomyClassificationCase.id == case_id)
        .options(selectinload(NationalEconomyClassificationCase.result_versions))
    )
    if case is None:
        raise HTTPException(status_code=404, detail="案例不存在")
    return case


def _get_available_scenario(scenario_id: str) -> ScenarioRegistration:
    registration = SCENARIO_REGISTRY.get(scenario_id)
    if registration is None:
        raise HTTPException(status_code=404, detail="场景不存在")
    if registration.status != "available":
        raise HTTPException(status_code=409, detail="场景暂未开放")
    return registration


def _get_scenario_case(
    session: Session,
    scenario_id: str,
    case_id: int,
) -> NationalEconomyClassificationCase:
    _get_available_scenario(scenario_id)
    case = _get_case(session, case_id)
    if case.scenario != scenario_id:
        raise HTTPException(status_code=404, detail="案例不存在")
    return case


def _technology_finance_workflow_response(
    outcome: TechnologyFinanceWorkflowResult,
) -> TechnologyFinanceWorkflowResponse:
    return TechnologyFinanceWorkflowResponse(
        stage_a=ClassificationResultResponse.model_validate(outcome.stage_a_result),
        stage_b=(
            FiveArticlesResultResponse.model_validate(outcome.stage_b_result)
            if outcome.stage_b_result is not None
            else None
        ),
    )


def _case_response(case: NationalEconomyClassificationCase) -> CaseResponse:
    current_result = get_current_completed_result(case)
    registration = SCENARIO_REGISTRY.get(case.scenario)
    field_labels = (
        tuple((field.key, field.label) for field in registration.field_schema)
        if registration is not None
        else tuple(FIELD_LABELS.items())
    )
    return CaseResponse(
        id=case.id,
        scenario=case.scenario,
        status=case.status,
        original_filename=case.original_filename,
        input_fields=[
            CaseInputField(
                field=field,
                label=label,
                value=case.input_payload.get(field, ""),
            )
            for field, label in field_labels
        ],
        current_result=(
            ClassificationResultResponse.model_validate(current_result)
            if current_result is not None
            else None
        ),
        created_at=case.created_at,
        updated_at=case.updated_at,
    )


def _download_response(content: bytes, media_type: str, filename: str) -> StreamingResponse:
    return StreamingResponse(
        BytesIO(content),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
