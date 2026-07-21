from datetime import datetime

from pydantic import BaseModel

from app.services.technology_finance_ip_registry import TechnologyFinanceRegistryType


class EnterpriseRegistryUploadResponse(BaseModel):
    registry_type: TechnologyFinanceRegistryType
    version: int
    row_count: int
    reused: bool
    published_at: datetime
