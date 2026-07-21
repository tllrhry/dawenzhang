from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.session import get_db
from app.schemas.technology_finance_registry import EnterpriseRegistryUploadResponse
from app.services.technology_finance_ip_registry import TechnologyFinanceRegistryType
from app.services.technology_finance_ip_registry_sync import (
    MAX_REGISTRY_PDF_BYTES,
    TechnologyFinanceIpRegistryParseError,
    TechnologyFinanceIpRegistryUploadError,
    publish_uploaded_technology_finance_ip_registry,
)


router = APIRouter(prefix="/technology-finance", tags=["technology-finance"])


@router.post(
    "/enterprise-registries",
    response_model=EnterpriseRegistryUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_enterprise_registry(
    registry_type: Annotated[TechnologyFinanceRegistryType, Form(...)],
    file: Annotated[UploadFile, File(...)],
    session: Session = Depends(get_db),
) -> EnterpriseRegistryUploadResponse:
    filename = Path(file.filename or "").name
    source_bytes = await file.read(MAX_REGISTRY_PDF_BYTES + 1)
    try:
        result = publish_uploaded_technology_finance_ip_registry(
            session,
            source_bytes,
            filename,
            registry_type=registry_type,
            upload_dir=get_settings().upload_dir,
        )
    except TechnologyFinanceIpRegistryUploadError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except TechnologyFinanceIpRegistryParseError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"企业名单 PDF 解析失败：{exc}",
        ) from exc
    except SQLAlchemyError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="企业名单发布冲突，请稍后重试",
        ) from exc

    return EnterpriseRegistryUploadResponse(
        registry_type=registry_type,
        version=result.version.version,
        row_count=result.version.row_count,
        reused=result.reused,
        published_at=result.version.published_at,
    )
