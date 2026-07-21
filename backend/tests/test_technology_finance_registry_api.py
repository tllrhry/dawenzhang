from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.api.routes import technology_finance_registry as route_module
from app.db.session import get_db, get_sessionmaker
from app.main import app
from app.models import (
    TechnologyFinanceIpRegistryEntry,
    TechnologyFinanceIpRegistryVersion,
)
from app.services import technology_finance_ip_registry_sync as sync_service


ROOT_DIR = Path(__file__).resolve().parents[2]
HIGH_TECH_PDF = ROOT_DIR / "模板文件/江苏省高新技术企业备案公示名单.pdf"
SPECIALIZED_INNOVATION_PDF = (
    ROOT_DIR / "模板文件/2025年省级专精特新中小企业.pdf"
)
ENDPOINT = "/api/v1/technology-finance/enterprise-registries"


@pytest.fixture()
def db_session() -> Session:
    session = get_sessionmaker()()
    session.execute(delete(TechnologyFinanceIpRegistryEntry))
    session.execute(delete(TechnologyFinanceIpRegistryVersion))
    session.commit()
    try:
        yield session
    finally:
        session.rollback()
        session.execute(delete(TechnologyFinanceIpRegistryEntry))
        session.execute(delete(TechnologyFinanceIpRegistryVersion))
        session.commit()
        session.close()


@pytest.fixture()
def client(
    db_session: Session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> TestClient:
    def override_get_db():
        yield db_session

    monkeypatch.setattr(
        route_module,
        "get_settings",
        lambda: SimpleNamespace(upload_dir=tmp_path),
    )
    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.pop(get_db, None)


@pytest.mark.parametrize(
    ("registry_type", "source_path", "expected_rows"),
    [
        ("high_tech", HIGH_TECH_PDF, 571),
        ("specialized_innovation", SPECIALIZED_INNOVATION_PDF, 753),
    ],
)
def test_upload_current_registry_pdf_publishes_selected_type(
    client: TestClient,
    db_session: Session,
    tmp_path: Path,
    registry_type: str,
    source_path: Path,
    expected_rows: int,
) -> None:
    response = client.post(
        ENDPOINT,
        data={"registry_type": registry_type},
        files={"file": (source_path.name, source_path.read_bytes(), "application/pdf")},
    )

    assert response.status_code == 201
    assert response.json() | {"published_at": "ignored"} == {
        "registry_type": registry_type,
        "version": 1,
        "row_count": expected_rows,
        "reused": False,
        "published_at": "ignored",
    }
    version = db_session.scalar(select(TechnologyFinanceIpRegistryVersion))
    assert version is not None
    assert version.registry_type == registry_type
    assert version.row_count == expected_rows
    assert Path(version.source_path).is_file()
    assert Path(version.source_path).parent == (
        tmp_path / "technology-finance-registries" / registry_type
    )
    assert db_session.scalar(
        select(func.count(TechnologyFinanceIpRegistryEntry.id))
    ) == expected_rows


def test_reupload_same_pdf_reuses_current_version(
    client: TestClient,
    db_session: Session,
) -> None:
    files = {
        "file": (HIGH_TECH_PDF.name, HIGH_TECH_PDF.read_bytes(), "application/pdf")
    }
    first = client.post(ENDPOINT, data={"registry_type": "high_tech"}, files=files)
    second = client.post(ENDPOINT, data={"registry_type": "high_tech"}, files=files)

    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json()["reused"] is True
    assert second.json()["version"] == first.json()["version"]
    assert db_session.scalar(
        select(func.count(TechnologyFinanceIpRegistryVersion.id))
    ) == 1
    assert db_session.scalar(
        select(func.count(TechnologyFinanceIpRegistryEntry.id))
    ) == 571


@pytest.mark.parametrize(
    ("filename", "content", "expected_detail"),
    [
        ("registry.txt", b"%PDF-test", "请上传单个 .pdf 文件"),
        ("registry.pdf", b"", "上传的 PDF 文件为空"),
        ("registry.pdf", b"not-a-pdf", "文件内容不是有效的 PDF"),
    ],
)
def test_invalid_file_rejected_without_publication(
    client: TestClient,
    db_session: Session,
    filename: str,
    content: bytes,
    expected_detail: str,
) -> None:
    response = client.post(
        ENDPOINT,
        data={"registry_type": "high_tech"},
        files={"file": (filename, content, "application/pdf")},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == expected_detail
    assert db_session.scalar(
        select(func.count(TechnologyFinanceIpRegistryVersion.id))
    ) == 0


def test_unsupported_registry_type_is_rejected_without_publication(
    client: TestClient,
    db_session: Session,
) -> None:
    response = client.post(
        ENDPOINT,
        data={"registry_type": "unknown"},
        files={
            "file": (
                HIGH_TECH_PDF.name,
                HIGH_TECH_PDF.read_bytes(),
                "application/pdf",
            )
        },
    )

    assert response.status_code == 422
    assert db_session.scalar(
        select(func.count(TechnologyFinanceIpRegistryVersion.id))
    ) == 0


def test_invalid_registry_table_is_rejected_and_temporary_file_is_removed(
    client: TestClient,
    db_session: Session,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def reject_table(_source_path: Path) -> None:
        raise sync_service.TechnologyFinanceIpRegistryParseError(
            "名单序号必须从 1 连续排列"
        )

    monkeypatch.setattr(
        sync_service,
        "parse_technology_finance_ip_registry",
        reject_table,
    )
    response = client.post(
        ENDPOINT,
        data={"registry_type": "high_tech"},
        files={
            "file": (
                HIGH_TECH_PDF.name,
                HIGH_TECH_PDF.read_bytes(),
                "application/pdf",
            )
        },
    )

    assert response.status_code == 422
    assert "名单序号必须从 1 连续排列" in response.json()["detail"]
    assert db_session.scalar(
        select(func.count(TechnologyFinanceIpRegistryVersion.id))
    ) == 0
    registry_dir = (
        tmp_path / "technology-finance-registries" / "high_tech"
    )
    assert not registry_dir.exists() or list(registry_dir.iterdir()) == []
