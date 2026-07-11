from dataclasses import dataclass
from io import BytesIO
from pathlib import Path

from docx import Document
from docx.opc.exceptions import PackageNotFoundError
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models import NationalEconomyClassificationCase


SCENARIO = "national_economy_classification"
PENDING_STATUS = "pending_classification"

FIELD_LABELS = {
    "enterprise_name": "企业名称",
    "unified_social_credit_code": "统一社会信用代码",
    "business_scope": "营业执照经营范围（全文）",
    "main_business": "主营业务",
    "main_business_revenue_share": "主营业务及营收占比",
    "core_products_services": "核心产品 / 服务名称",
    "loan_purpose": "贷款用途详细描述",
    "counterparty_name": "贸易合同本次交易对手名称",
    "counterparty_business_industry": "交易对手主营业务 / 所属行业",
    "trade_goods_services": "贸易合同核心交易品类 / 服务内容",
    "industry_chain_position": "企业产业链定位",
    "industry_position_competitiveness": "企业行业定位与核心竞争力",
    "credit_approval_opinion": "授信审批意见",
}
_LABEL_TO_FIELD = {label: field for field, label in FIELD_LABELS.items()}


@dataclass(frozen=True)
class TemplateValidationIssues:
    missing: tuple[str, ...] = ()
    duplicate: tuple[str, ...] = ()
    unrecognized: tuple[str, ...] = ()


class NationalEconomyTemplateError(ValueError):
    def __init__(self, issues: TemplateValidationIssues) -> None:
        self.issues = issues
        details = []
        if issues.missing:
            details.append(f"缺失标签: {', '.join(issues.missing)}")
        if issues.duplicate:
            details.append(f"重复标签: {', '.join(issues.duplicate)}")
        if issues.unrecognized:
            details.append(f"无法识别标签: {', '.join(issues.unrecognized)}")
        super().__init__("; ".join(details))


def read_template_bytes(settings: Settings | None = None) -> bytes:
    template_path = (settings or get_settings()).national_economy_template_path
    return template_path.read_bytes()


def parse_template(document_bytes: bytes) -> dict[str, str]:
    try:
        document = Document(BytesIO(document_bytes))
    except (PackageNotFoundError, ValueError, KeyError) as exc:
        raise NationalEconomyTemplateError(
            TemplateValidationIssues(unrecognized=("文件不是可解析的 .docx 模板",))
        ) from exc

    values: dict[str, str] = {}
    duplicate_labels: list[str] = []
    unrecognized_labels: list[str] = []

    for paragraph in document.paragraphs:
        text = paragraph.text.strip()
        if not text:
            continue
        label, separator, value = text.partition("：")
        if not separator:
            unrecognized_labels.append(text)
            continue
        label = label.strip()
        field = _LABEL_TO_FIELD.get(label)
        if field is None:
            unrecognized_labels.append(label)
            continue
        if field in values:
            duplicate_labels.append(label)
            continue
        values[field] = value.strip()

    missing_labels = [
        label for field, label in FIELD_LABELS.items() if field not in values
    ]
    issues = TemplateValidationIssues(
        missing=tuple(missing_labels),
        duplicate=tuple(duplicate_labels),
        unrecognized=tuple(unrecognized_labels),
    )
    if issues.missing or issues.duplicate or issues.unrecognized:
        raise NationalEconomyTemplateError(issues)

    return {field: values[field] for field in FIELD_LABELS}


def create_case_from_template(
    session: Session,
    document_bytes: bytes,
    original_filename: str,
) -> NationalEconomyClassificationCase:
    input_payload = parse_template(document_bytes)
    case = NationalEconomyClassificationCase(
        scenario=SCENARIO,
        input_payload=input_payload,
        original_filename=Path(original_filename).name,
        status=PENDING_STATUS,
    )
    session.add(case)
    session.commit()
    session.refresh(case)
    return case
