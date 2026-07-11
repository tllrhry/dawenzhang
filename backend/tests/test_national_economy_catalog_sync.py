from pathlib import Path
from unittest.mock import Mock

import pytest
from openpyxl import Workbook

from app.models import NationalEconomyCatalogVersion
from app.services.national_economy_catalog_sync import (
    EXPECTED_HEADERS,
    CatalogHeaderError,
    read_catalog_source,
    synchronize_catalog,
)


def write_catalog(path: Path, headers: tuple[str, ...] = EXPECTED_HEADERS) -> None:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.append(headers)
    worksheet.append(("农、林、牧、渔业", "A01", "稻谷种植", "A0111", None, "包括稻谷种植", None))
    workbook.save(path)
    workbook.close()


def test_read_catalog_source_validates_exact_headers(tmp_path: Path) -> None:
    catalog_path = tmp_path / "catalog.xlsx"
    write_catalog(catalog_path, EXPECTED_HEADERS[:-1] + ("错误表头",))

    with pytest.raises(CatalogHeaderError, match="invalid catalog headers"):
        read_catalog_source(catalog_path)


def test_unchanged_identity_skips_full_resync(tmp_path: Path) -> None:
    catalog_path = tmp_path / "catalog.xlsx"
    write_catalog(catalog_path)
    source = read_catalog_source(catalog_path)
    existing = NationalEconomyCatalogVersion(
        id=1,
        version="existing",
        source_hash=source.source_hash,
        embedding_model="embedding-model",
        embedding_dimension=4096,
    )
    session = Mock()
    session.scalar.return_value = existing
    full_resync = Mock()

    result = synchronize_catalog(session, source, "embedding-model", 4096, full_resync)

    assert result.created is False
    assert result.version is existing
    statement = session.scalar.call_args.args[0]
    assert set(statement.compile().params.values()) == {
        source.source_hash,
        "embedding-model",
        4096,
    }
    session.add.assert_not_called()
    full_resync.assert_not_called()


@pytest.mark.parametrize(
    ("existing_hash", "existing_model", "existing_dimension"),
    [
        ("different-hash", "embedding-model", 4096),
        (None, "different-model", 4096),
        (None, "embedding-model", 1024),
    ],
)
def test_any_identity_change_triggers_full_resync(
    tmp_path: Path,
    existing_hash: str | None,
    existing_model: str,
    existing_dimension: int,
) -> None:
    catalog_path = tmp_path / "catalog.xlsx"
    write_catalog(catalog_path)
    source = read_catalog_source(catalog_path)
    prior_version = NationalEconomyCatalogVersion(
        id=1,
        version="prior",
        source_hash=existing_hash or source.source_hash,
        embedding_model=existing_model,
        embedding_dimension=existing_dimension,
    )
    session = Mock()
    session.scalar.return_value = None
    full_resync = Mock()

    result = synchronize_catalog(session, source, "embedding-model", 4096, full_resync)

    assert prior_version.source_hash != source.source_hash or (
        prior_version.embedding_model,
        prior_version.embedding_dimension,
    ) != ("embedding-model", 4096)
    assert result.created is True
    assert result.version.source_hash == source.source_hash
    assert result.version.embedding_model == "embedding-model"
    assert result.version.embedding_dimension == 4096
    assert len(result.version.version) == 64
    session.add.assert_called_once_with(result.version)
    session.flush.assert_called_once_with()
    full_resync.assert_called_once_with(session, result.version, source.rows)
