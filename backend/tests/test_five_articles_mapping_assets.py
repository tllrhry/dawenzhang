from hashlib import sha256
from pathlib import Path
from openpyxl import Workbook
import pytest

from scripts.preflight_five_articles_mapping_assets import (
    ASSET_SPECS,
    MAPPING_SOURCE_FILENAME,
    MappingAssetValidationError,
    REQUIRED_HEADERS,
    discover_mapping_assets,
    validate_mapping_asset,
)


def _spec(scenario_id: str):
    return next(spec for spec in ASSET_SPECS if spec.scenario_id == scenario_id)


def _write_workbook(
    path: Path,
    *,
    headers: tuple[str, ...] = REQUIRED_HEADERS,
    category: str | None = None,
) -> None:
    workbook = Workbook()
    worksheet = workbook.active
    actual_headers = (*headers, "属于类别") if category is not None else headers
    worksheet.append(actual_headers)
    values = {
        "主题": "测试主题",
        "第一层": "测试第一层",
        "第二层": "",
        "第三层": "",
        "第四层": "",
        "NEIC_Code": "1234",
        "NEIC_Name": "测试行业",
        "属于类别": category,
    }
    worksheet.append(
        [
            values.get(header, "1234" if "NEIC_Code" in header else "")
            for header in actual_headers
        ]
    )
    workbook.save(path)
    workbook.close()


@pytest.mark.parametrize("spec", ASSET_SPECS, ids=lambda spec: spec.scenario_id)
def test_formal_mapping_asset_has_unified_headers_and_metadata(spec) -> None:
    path = Path("五篇大文章映射") / MAPPING_SOURCE_FILENAME
    report = validate_mapping_asset(path, spec)

    assert set(REQUIRED_HEADERS).issubset(report.headers)
    assert report.source_hash == sha256(report.path.read_bytes()).hexdigest()
    assert len(report.source_hash) == 64
    assert report.data_row_count > 0


def test_mapping_asset_preflight_rejects_missing_header(tmp_path: Path) -> None:
    path = tmp_path / "数字金融.xlsx"
    _write_workbook(path, headers=REQUIRED_HEADERS[:-1])

    with pytest.raises(MappingAssetValidationError, match="缺少表头: NEIC_Name"):
        validate_mapping_asset(path, _spec("digital_finance"))


def test_mapping_asset_preflight_rejects_normalized_duplicate_header(
    tmp_path: Path,
) -> None:
    path = tmp_path / "养老金融.xlsx"
    _write_workbook(path, headers=(*REQUIRED_HEADERS, "国民经济行业代码\nNEIC_Code"))

    with pytest.raises(MappingAssetValidationError, match="重复表头: NEIC_Code"):
        validate_mapping_asset(path, _spec("pension_finance"))


def test_mapping_asset_preflight_rejects_missing_category_data(
    tmp_path: Path,
) -> None:
    path = tmp_path / "绿色金融.xlsx"
    _write_workbook(path, category="数字金融")

    with pytest.raises(MappingAssetValidationError, match="未找到属于类别“绿色金融”的数据"):
        validate_mapping_asset(path, _spec("green_finance"))


def test_mapping_asset_discovery_ignores_lock_file_and_ds_store(
    tmp_path: Path,
) -> None:
    source = Path("五篇大文章映射") / MAPPING_SOURCE_FILENAME
    (tmp_path / MAPPING_SOURCE_FILENAME).write_bytes(source.read_bytes())
    (tmp_path / "~$绿色金融.xlsx").write_bytes(b"not an xlsx")
    (tmp_path / ".DS_Store").write_bytes(b"filesystem metadata")

    discovered = discover_mapping_assets(tmp_path)

    assert set(discovered) == {spec.scenario_id for spec in ASSET_SPECS}
    assert all(not path.name.startswith("~$") for path in discovered.values())
    assert set(discovered.values()) == {tmp_path / MAPPING_SOURCE_FILENAME}
