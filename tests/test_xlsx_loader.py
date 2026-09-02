from pathlib import Path

from openpyxl import Workbook

from app.ingestion.loaders.xlsx_loader import XLSXLoader


FIXTURES = Path(__file__).parent / "fixtures" / "xlsx"
LOADER = XLSXLoader()


def test_normal_xlsx_identifies_workbook_sheet_and_range() -> None:
    result = LOADER.load(FIXTURES / "normal.xlsx", "normal")

    assert result.status == "parsed"
    assert result.workbook_name == "normal.xlsx"
    assert result.sheet_names == ["设计管理"]
    assert len(result.blocks) == 1
    block = result.blocks[0]
    assert block.source_path.endswith("normal.xlsx")
    assert block.file_name == "normal.xlsx"
    assert block.heading_path == "设计管理"
    assert block.location == {
        "sheet_name": "设计管理",
        "row_start": 1,
        "row_end": 3,
        "column_count": 2,
        "header_row": 1,
    }
    assert "表头（第1行）：项目 | 状态" in block.text
    assert "第2行：项目：EPC | 状态：可解析" in block.text


def test_multi_sheet_xlsx_emits_one_block_per_valid_sheet() -> None:
    result = LOADER.load(FIXTURES / "multi_sheet.xlsx", "multi")

    assert result.status == "parsed"
    assert result.sheet_names == ["第一张", "第二张", "空Sheet"]
    assert [block.location["sheet_name"] for block in result.blocks] == ["第一张", "第二张"]
    assert [block.location["column_count"] for block in result.blocks] == [2, 3]


def test_table_xlsx_preserves_row_column_relationships() -> None:
    result = LOADER.load(FIXTURES / "table.xlsx", "table")

    assert result.status == "parsed"
    block = result.blocks[0]
    assert block.location["sheet_name"] == "表格"
    assert block.location["row_start"] == 1
    assert block.location["row_end"] == 3
    assert block.location["column_count"] == 3
    assert "字段 | 内容 | 单位" in block.text
    assert "字段：数量 | 内容：12 | 单位：个" in block.text


def test_empty_xlsx_returns_empty_status() -> None:
    result = LOADER.load(FIXTURES / "empty.xlsx", "empty")

    assert result.status == "empty"
    assert result.blocks == []
    assert result.sheet_names == ["Sheet"]


def test_broken_xlsx_returns_read_error_without_raising() -> None:
    result = LOADER.load(FIXTURES / "broken.xlsx", "broken")

    assert result.status == "read_error"
    assert result.blocks == []
    assert result.error


def test_legacy_xls_is_not_converted(tmp_path: Path) -> None:
    legacy_path = tmp_path / "legacy.xls"
    legacy_path.write_bytes(b"legacy workbook placeholder")

    result = LOADER.load(legacy_path, "legacy")

    assert result.status == "read_error"
    assert result.blocks == []
    assert result.error and "不自动转换" in result.error


def test_header_is_padded_when_later_rows_have_more_columns(tmp_path: Path) -> None:
    path = tmp_path / "header-shorter.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(("字段",))
    sheet.append(("A", "B", "C"))
    workbook.save(path)

    result = LOADER.load(path, "header-shorter")

    assert result.status == "parsed"
    assert result.blocks[0].location["column_count"] == 3
    assert "列2：B | 列3：C" in result.blocks[0].text
