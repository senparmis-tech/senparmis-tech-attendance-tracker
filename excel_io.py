"""
Excel import and export only. The website's data lives in SQLite (see db.py and store.py);
this module reads an old attendance_records.xlsx into it and writes a fresh .xlsx copy out.
"""
from openpyxl import Workbook, load_workbook
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from config import FIRST_DATE_COL, FIRST_ROW, HEADER_ROW, LOW_RATE, MAX_COL, MAX_ROW, TOPIC_ROW
from helpers import clean_name, norm_code, to_date

# --------------------------------------------------------- workbook styling
THIN = Side(style="thin", color="D0D5DD")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
HEAD_FILL = PatternFill("solid", start_color="E8ECF4", end_color="E8ECF4")
CENTER = Alignment(horizontal="center", vertical="center")
LAST_COL = get_column_letter(MAX_COL)


def put_formulas(ws, r):
    rng = f"$H{r}:${LAST_COL}{r}"
    ws.cell(r, 3).value = f'=IF($B{r}="","",COUNTIF({rng},"p")+COUNTIF({rng},"r"))'
    ws.cell(r, 4).value = f'=IF($B{r}="","",COUNTIF({rng},"x"))'
    ws.cell(r, 5).value = f'=IF($B{r}="","",COUNTIF({rng},"l"))'
    ws.cell(r, 6).value = f'=IF($B{r}="","",COUNTIF({rng},"e"))'
    ws.cell(r, 7).value = f'=IF($B{r}="","",IF(COUNTA({rng})=0,"",(C{r}+E{r})/COUNTA({rng})))'
    ws.cell(r, 7).number_format = "0%"


def last_date_col(ws):
    last = FIRST_DATE_COL - 1
    for c in range(FIRST_DATE_COL, min(ws.max_column, MAX_COL) + 1):
        if to_date(ws.cell(HEADER_ROW, c).value):
            last = c
    return last


def style_row(ws, r):
    for c in range(1, 8):
        cell = ws.cell(r, c)
        cell.border = BORDER
        cell.alignment = CENTER if c != 2 else Alignment(vertical="center")
    for c in range(FIRST_DATE_COL, last_date_col(ws) + 1):
        ws.cell(r, c).border = BORDER
        ws.cell(r, c).alignment = CENTER


def style_date_header(ws, col):
    h = ws.cell(HEADER_ROW, col)
    h.number_format = "mmm d"
    h.font = Font(bold=True)
    h.fill = HEAD_FILL
    h.alignment = CENTER
    h.border = BORDER
    t = ws.cell(TOPIC_ROW, col)
    t.font = Font(size=9, italic=True, color="475467")
    t.alignment = Alignment(wrap_text=True, vertical="top", horizontal="center")
    t.border = BORDER


def renumber(ws):
    """Number the students and (re)write each row's formulas."""
    n = 0
    for r in range(FIRST_ROW, max(ws.max_row, FIRST_ROW) + 1):
        if ws.cell(r, 2).value not in (None, ""):
            n += 1
            ws.cell(r, 1).value = n
            put_formulas(ws, r)
            style_row(ws, r)


def setup_sheet(ws, title):
    ws["A1"] = title
    ws["A1"].font = Font(bold=True, size=16)
    ws["A2"] = ("p = present   x = absent   l = late   e = excused   r = present + recited.   "
                "Type a topic in row 3 and a date in row 4 (next empty column from H).")
    ws["A2"].font = Font(italic=True, color="667085")
    ws.cell(TOPIC_ROW, 7).value = "Topic →"
    ws.cell(TOPIC_ROW, 7).font = Font(bold=True, color="475467")
    ws.cell(TOPIC_ROW, 7).alignment = Alignment(horizontal="right", vertical="top")
    ws.row_dimensions[TOPIC_ROW].height = 48
    heads = ["No.", "Student Name", "Present", "Absent", "Late", "Excused", "Rate"]
    for i, h in enumerate(heads, start=1):
        c = ws.cell(HEADER_ROW, i, h)
        c.font = Font(bold=True)
        c.fill = HEAD_FILL
        c.alignment = CENTER
        c.border = BORDER
    widths = {1: 6, 2: 30, 3: 9, 4: 9, 5: 9, 6: 9, 7: 9}
    for c in range(1, MAX_COL + 1):
        ws.column_dimensions[get_column_letter(c)].width = widths.get(c, 9)
    ws.freeze_panes = ws.cell(FIRST_ROW, FIRST_DATE_COL)

    area = f"H{FIRST_ROW}:{LAST_COL}{MAX_ROW}"
    dv = DataValidation(type="list", formula1='"p,x,l,e,r"', allow_blank=True,
                        showErrorMessage=True, errorTitle="Attendance code",
                        error="Use p (present), x (absent), l (late), e (excused) or r (present + recited).")
    ws.add_data_validation(dv)
    dv.add(area)

    def fmt(color, bg):
        return dict(font=Font(color=color, bold=True),
                    fill=PatternFill(start_color=bg, end_color=bg, fill_type="solid"))
    ws.conditional_formatting.add(area, CellIsRule(operator="equal", formula=['"x"'], **fmt("C00000", "FDE2E2")))
    ws.conditional_formatting.add(area, CellIsRule(operator="equal", formula=['"p"'], **fmt("1F7A45", "E3F6EA")))
    ws.conditional_formatting.add(area, CellIsRule(operator="equal", formula=['"l"'], **fmt("9A6700", "FDF3DC")))
    ws.conditional_formatting.add(area, CellIsRule(operator="equal", formula=['"e"'], **fmt("2B6CB0", "E4EFFB")))
    ws.conditional_formatting.add(area, CellIsRule(operator="equal", formula=['"r"'], **fmt("6B21A8", "EFE7FD")))
    ws.conditional_formatting.add(
        f"G{FIRST_ROW}:G{MAX_ROW}",
        CellIsRule(operator="lessThan", formula=[str(LOW_RATE)], font=Font(color="C00000", bold=True)))



def is_subject_sheet(ws):
    return str(ws.cell(HEADER_ROW, 2).value or "").strip().lower() == "student name"



def read_sheet(ws):
    students = []
    for r in range(FIRST_ROW, ws.max_row + 1):
        name = clean_name(str(ws.cell(r, 2).value or ""))
        if name:
            students.append({"row": r, "name": name})
    dates = []
    for c in range(FIRST_DATE_COL, min(ws.max_column, MAX_COL) + 1):
        d = to_date(ws.cell(HEADER_ROW, c).value)
        if d:
            dates.append({"col": c, "date": d,
                          "topic": clean_name(str(ws.cell(TOPIC_ROW, c).value or ""))})
    cells = {}
    for s in students:
        for dd in dates:
            code = norm_code(ws.cell(s["row"], dd["col"]).value)
            if code:
                cells[(s["row"], dd["col"])] = code
    return {"students": students, "dates": dates, "cells": cells}


def read_workbook(path):
    """Read every subject sheet of an attendance workbook: {subject: {students, dates, cells}}."""
    wb = load_workbook(path)
    return {ws.title: read_sheet(ws) for ws in wb.worksheets if is_subject_sheet(ws)}


def build_workbook(data):
    """Build a workbook (one sheet per subject) from load_data() output."""
    wb = Workbook()
    wb.remove(wb.active)
    for subject, sd in data.items():
        ws = wb.create_sheet(subject)
        setup_sheet(ws, subject)
        for i, s in enumerate(sd["students"]):
            ws.cell(FIRST_ROW + i, 2).value = s["name"]
        for j, dd in enumerate(sd["dates"][: MAX_COL - FIRST_DATE_COL]):
            col = FIRST_DATE_COL + j
            ws.cell(HEADER_ROW, col).value = dd["date"]
            ws.cell(TOPIC_ROW, col).value = dd["topic"] or None
            style_date_header(ws, col)
            for i, s in enumerate(sd["students"]):
                code = sd["cells"].get((s["row"], dd["col"]), "")
                if code:
                    ws.cell(FIRST_ROW + i, col).value = code
        renumber(ws)
    if not wb.worksheets:
        wb.create_sheet("Guide")
    return wb
