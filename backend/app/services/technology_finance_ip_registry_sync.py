"""Parse, publish, and store technology-finance enterprise registries."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

import pdfplumber
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import (
    TechnologyFinanceIpRegistryEntry,
    TechnologyFinanceIpRegistryVersion,
)
from app.services.technology_finance_ip_registry import (
    HIGH_TECH_REGISTRY,
    SPECIALIZED_INNOVATION_REGISTRY,
    TechnologyFinanceRegistryType,
)


MAX_REGISTRY_PDF_BYTES = 20 * 1024 * 1024
SUPPORTED_REGISTRY_TYPES = frozenset(
    {HIGH_TECH_REGISTRY, SPECIALIZED_INNOVATION_REGISTRY}
)


class TechnologyFinanceIpRegistryParseError(ValueError):
    """The source PDF does not contain a valid continuous registry."""


class TechnologyFinanceIpRegistryUploadError(ValueError):
    """The uploaded file does not meet the registry upload contract."""


@dataclass(frozen=True)
class RegistryRow:
    source_row: int
    enterprise_name: str


@dataclass(frozen=True)
class RegistrySyncResult:
    version: TechnologyFinanceIpRegistryVersion
    reused: bool


@dataclass(frozen=True)
class RegistryUploadResult:
    version: TechnologyFinanceIpRegistryVersion
    reused: bool


def parse_technology_finance_ip_registry(source_path: Path) -> list[RegistryRow]:
    """Parse and validate all registry rows from *source_path*."""
    rows: list[RegistryRow] = []
    found_header = False
    try:
        with pdfplumber.open(source_path) as pdf:
            for page in pdf.pages:
                for table in page.extract_tables():
                    for raw_row in table:
                        cells = [str(cell or "").strip() for cell in raw_row]
                        is_header = any(cell == "序号" for cell in cells) and any(
                            cell == "企业名称" for cell in cells
                        )
                        if not found_header:
                            if is_header:
                                found_header = True
                            continue
                        # Excel-generated PDFs repeat the table header on every
                        # page. It is metadata, not an invalid registry row.
                        if is_header:
                            continue
                        if not any(cells):
                            continue
                        if len(cells) < 2 or not cells[0].isdigit():
                            raise TechnologyFinanceIpRegistryParseError(
                                f"名单中存在无法识别的行：{raw_row!r}"
                            )
                        enterprise_name = cells[1].strip()
                        if not enterprise_name:
                            raise TechnologyFinanceIpRegistryParseError(
                                f"第 {cells[0]} 行企业名称为空"
                            )
                        rows.append(RegistryRow(int(cells[0]), enterprise_name))
    except TechnologyFinanceIpRegistryParseError:
        raise
    except Exception as exc:
        raise TechnologyFinanceIpRegistryParseError(
            "无法读取 PDF 表格，请确认文件未损坏且不是扫描件"
        ) from exc

    if not found_header:
        raise TechnologyFinanceIpRegistryParseError(
            "未找到包含“序号”和“企业名称”的表头"
        )
    for expected, row in enumerate(rows, start=1):
        if row.source_row != expected:
            raise TechnologyFinanceIpRegistryParseError(
                f"名单序号必须从 1 连续排列：应为 {expected}，实际为 {row.source_row}"
            )
    if not rows:
        raise TechnologyFinanceIpRegistryParseError("名单中没有可导入的企业数据")
    seen_names: set[str] = set()
    for row in rows:
        if row.enterprise_name in seen_names:
            raise TechnologyFinanceIpRegistryParseError(
                f"企业名称重复：{row.enterprise_name}"
            )
        seen_names.add(row.enterprise_name)
    return rows


def synchronize_technology_finance_ip_registry(
    session: Session,
    source_path: Path,
    *,
    registry_type: TechnologyFinanceRegistryType = HIGH_TECH_REGISTRY,
    settings: Settings | None = None,
    parsed_rows: Sequence[RegistryRow] | None = None,
) -> RegistrySyncResult:
    """Validate and publish a source file; the caller owns the transaction/commit."""
    del settings  # Retained for compatibility with existing callers.
    source_bytes = source_path.read_bytes()
    source_hash = sha256(source_bytes).hexdigest()
    latest = session.scalar(
        select(TechnologyFinanceIpRegistryVersion)
        .where(
            TechnologyFinanceIpRegistryVersion.status == "published",
            TechnologyFinanceIpRegistryVersion.registry_type == registry_type,
        )
        .order_by(TechnologyFinanceIpRegistryVersion.version.desc())
        .limit(1)
    )
    if latest is not None and latest.source_hash == source_hash:
        return RegistrySyncResult(version=latest, reused=True)

    rows = (
        list(parsed_rows)
        if parsed_rows is not None
        else parse_technology_finance_ip_registry(source_path)
    )
    next_version = (
        session.scalar(select(func.max(TechnologyFinanceIpRegistryVersion.version))) or 0
    ) + 1
    version = TechnologyFinanceIpRegistryVersion(
        version=next_version,
        registry_type=registry_type,
        source_path=str(source_path),
        source_hash=source_hash,
        row_count=len(rows),
        status="published",
    )
    version.entries = [
        TechnologyFinanceIpRegistryEntry(
            enterprise_name=row.enterprise_name,
            source_row=row.source_row,
        )
        for row in rows
    ]
    session.add(version)
    session.flush()
    return RegistrySyncResult(version=version, reused=False)


def publish_uploaded_technology_finance_ip_registry(
    session: Session,
    source_bytes: bytes,
    original_filename: str,
    *,
    registry_type: TechnologyFinanceRegistryType,
    upload_dir: Path,
) -> RegistryUploadResult:
    """Validate, store, and publish one uploaded registry PDF."""
    filename = Path(original_filename).name
    if registry_type not in SUPPORTED_REGISTRY_TYPES:
        raise TechnologyFinanceIpRegistryUploadError("不支持的企业名单类型")
    if not filename.lower().endswith(".pdf"):
        raise TechnologyFinanceIpRegistryUploadError("请上传单个 .pdf 文件")
    if not source_bytes:
        raise TechnologyFinanceIpRegistryUploadError("上传的 PDF 文件为空")
    if len(source_bytes) > MAX_REGISTRY_PDF_BYTES:
        raise TechnologyFinanceIpRegistryUploadError("PDF 文件不能超过 20 MB")
    if not source_bytes.startswith(b"%PDF-"):
        raise TechnologyFinanceIpRegistryUploadError("文件内容不是有效的 PDF")

    source_hash = sha256(source_bytes).hexdigest()
    registry_dir = upload_dir / "technology-finance-registries" / registry_type
    registry_dir.mkdir(parents=True, exist_ok=True)
    final_path = registry_dir / f"{source_hash}.pdf"
    temporary_path = registry_dir / f".{source_hash}.{uuid4().hex}.tmp"
    temporary_path.write_bytes(source_bytes)
    created_final_file = False

    try:
        rows = parse_technology_finance_ip_registry(temporary_path)
        if final_path.exists() and final_path.read_bytes() != source_bytes:
            raise TechnologyFinanceIpRegistryUploadError(
                "上传目录中的同哈希 PDF 文件异常，请联系管理员检查"
            )
        if final_path.exists():
            temporary_path.unlink(missing_ok=True)
        else:
            temporary_path.replace(final_path)
            created_final_file = True

        result = synchronize_technology_finance_ip_registry(
            session,
            final_path,
            registry_type=registry_type,
            parsed_rows=rows,
        )
        if result.reused:
            if created_final_file and Path(result.version.source_path) != final_path:
                final_path.unlink(missing_ok=True)
            return RegistryUploadResult(version=result.version, reused=True)

        try:
            session.commit()
            session.refresh(result.version)
        except Exception:
            session.rollback()
            if created_final_file:
                final_path.unlink(missing_ok=True)
            raise
        return RegistryUploadResult(version=result.version, reused=False)
    finally:
        temporary_path.unlink(missing_ok=True)
