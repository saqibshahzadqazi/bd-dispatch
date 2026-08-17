"""Excel output. Column widths and a frozen header row, because these sheets
get opened on a phone as often as a laptop.
"""
from __future__ import annotations

import io

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

HEADER_FILL = PatternFill("solid", fgColor="14202C")
HEADER_FONT = Font(color="FFFFFF", bold=True, size=10)
WIDTHS = {"#": 5, "Job title": 46, "Client": 26, "Platform": 14, "Job link": 52,
          "Already tried by": 22, "Match ref": 30, "Metric": 34, "Value": 14,
          "BD": 20, "Applied by": 30, "People": 9, "Status": 12}


# Excel treats a leading =, +, - or @ as the start of a formula. These sheets
# are built from cells somebody typed into their own spreadsheet, then opened by
# a colleague — so a title of `=cmd|'/c calc'!A1` would execute on their machine,
# not ours. A leading apostrophe tells Excel "this is text", and is not shown.
_FORMULA_LEAD = ("=", "+", "-", "@", "\t", "\r")


def _safe_cell(value):
    if isinstance(value, str) and value.startswith(_FORMULA_LEAD):
        return "'" + value
    return value


def _write_sheet(book: Workbook, title: str, columns: list[str], rows: list[list]) -> None:
    sheet = book.create_sheet(title[:31] or "Sheet")
    sheet.append(columns)
    for cell in sheet[1]:
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(vertical="center")
    for row in rows:
        sheet.append([_safe_cell(value) for value in row])
    for index, column in enumerate(columns, start=1):
        sheet.column_dimensions[get_column_letter(index)].width = WIDTHS.get(column, 18)
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = sheet.dimensions


def assignment_workbook(person: str, jobs: list[dict]) -> bytes:
    book = Workbook()
    book.remove(book.active)
    columns = ["#", "Job title", "Client", "Platform", "Job link", "Status"]
    rows = [
        [i, j.get("title", ""), j.get("company", ""), j.get("platform", ""),
         j.get("url", ""), j.get("status", "pending")]
        for i, j in enumerate(jobs, start=1)
    ]
    _write_sheet(book, f"{person} jobs", columns, rows)
    stream = io.BytesIO()
    book.save(stream)
    return stream.getvalue()


def report_workbook(report: dict, per_person: dict[str, list[dict]],
                    collisions: list[dict], matrix_names: list[str],
                    matrix: list[list[int]]) -> bytes:
    book = Workbook()
    book.remove(book.active)

    _write_sheet(book, "Summary", ["Metric", "Value"],
                 [[k, v] for k, v in report.items()])

    _write_sheet(book, "Collisions",
                 ["Job title", "Client", "Platform", "Job link", "Applied by", "People"],
                 [[c["title"], c["company"], c["platform"], c["url"],
                   ", ".join(c["applied_by"]), len(c["applied_by"])] for c in collisions])

    _write_sheet(book, "Overlap matrix", ["BD"] + matrix_names,
                 [[matrix_names[i]] + row for i, row in enumerate(matrix)])

    for person, jobs in per_person.items():
        _write_sheet(book, person, ["#", "Job title", "Client", "Platform", "Job link"],
                     [[i, j.get("title", ""), j.get("company", ""),
                       j.get("platform", ""), j.get("url", "")]
                      for i, j in enumerate(jobs, start=1)])

    stream = io.BytesIO()
    book.save(stream)
    return stream.getvalue()
