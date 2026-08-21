from openpyxl import Workbook

from app.parsers import parse_file


def test_xlsx_parser_keeps_sheet_and_row_location(tmp_path) -> None:
    path = tmp_path / "sample.xlsx"
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "项目清单"
    sheet.append(["项目", "业态"])
    sheet.append(["示例医院项目", "医院"])
    workbook.save(path)
    workbook.close()

    parsed = parse_file(path, 10)

    assert parsed.parse_status == "parsed"
    assert parsed.blocks[0].location["sheet"] == "项目清单"
    assert parsed.blocks[0].location["row"] == 2
