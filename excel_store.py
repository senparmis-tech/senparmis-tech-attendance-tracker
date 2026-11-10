"""
Excel workbook reading, writing, styling, backups, students, and subjects.
"""
import os
import re
import shutil
import threading
import time
from datetime import datetime

from flask import url_for
from openpyxl import Workbook, load_workbook
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

from config import (BACKUP_DIR, BACKUP_EVERY_MIN, BACKUP_KEEP, FIRST_DATE_COL,
                    FIRST_ROW, HEADER_ROW, LOW_RATE, MAX_COL, MAX_ROW,
                    SAMPLE_STUDENTS, SAMPLE_SUBJECTS, SUBJECT_IMG_DIR,
                    TOPIC_ROW, XLSX)
from helpers import clean_name, clean_sheet_name, norm_code, safe_text, to_date

write_lock = threading.RLock()


class FileLocked(Exception):
    pass


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


def ensure_r_support(ws):
    """Ensure older workbooks support code 'r' (Recited) in validation, rules, and formulas."""
    try:
        dvs = ws.data_validations.dataValidation
        has_r = any("r" in (getattr(d, "formula1", "") or "").split(",") for d in dvs)
        if not has_r:
            area = f"H{FIRST_ROW}:{LAST_COL}{MAX_ROW}"
            dv = DataValidation(type="list", formula1='"p,x,l,e,r"', allow_blank=True,
                                showErrorMessage=True, errorTitle="Attendance code",
                                error="Use p (present), x (absent), l (late), e (excused) or r (present + recited).")
            ws.add_data_validation(dv)
            dv.add(area)
            def fmt(color, bg):
                return dict(font=Font(color=color, bold=True),
                            fill=PatternFill(start_color=bg, end_color=bg, fill_type="solid"))
            ws.conditional_formatting.add(area, CellIsRule(operator="equal", formula=['"r"'], **fmt("6B21A8", "EFE7FD")))
            for r in range(FIRST_ROW, max(ws.max_row, FIRST_ROW) + 1):
                if ws.cell(r, 2).value not in (None, ""):
                    put_formulas(ws, r)
    except Exception:
        pass


def is_subject_sheet(ws):
    return str(ws.cell(HEADER_ROW, 2).value or "").strip().lower() == "student name"


def create_workbook():
    wb = Workbook()
    wb.remove(wb.active)
    for sub in SAMPLE_SUBJECTS:
        ws = wb.create_sheet(sub)
        setup_sheet(ws, sub)
        for i, name in enumerate(SAMPLE_STUDENTS):
            ws.cell(FIRST_ROW + i, 2).value = name
        renumber(ws)
    guide = wb.create_sheet("Guide")
    lines = [
        "How this workbook works",
        "",
        "• One tab per subject. Students are listed down column B, dates run across row 4 (from column H).",
        "• Row 3 holds the lesson topic for each date.",
        "• Cells use p (present), x (absent), l (late), e (excused). Columns C-G count them automatically.",
        "• The website and this workbook share the same data. After editing here, save and close Excel,",
        "  then refresh the website. While Excel has the file open, the website cannot save.",
        "• To add a date by hand, type it in the next empty cell of row 4 (for example 2026-10-05).",
        "• Rate = (Present + Late) / all recorded days.",
    ]
    for i, line in enumerate(lines, start=1):
        guide.cell(i, 1, line)
    guide["A1"].font = Font(bold=True, size=14)
    guide.column_dimensions["A"].width = 110
    return wb


def ensure_workbook():
    if not os.path.exists(XLSX):
        wb = create_workbook()
        wb.save(XLSX)


# ------------------------------------------------------------- reading data
_cache = {"stamp": None, "data": None}


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


def load_data():
    ensure_workbook()
    with write_lock:
        try:
            st = os.stat(XLSX)
            stamp = (st.st_mtime_ns, st.st_size)
        except OSError:
            stamp = None
        if _cache["data"] is not None and _cache["stamp"] == stamp:
            return _cache["data"]
        try:
            wb = load_workbook(XLSX)
        except PermissionError:
            if _cache["data"] is not None:
                return _cache["data"]
            raise FileLocked()
        data = {}
        for ws in wb.worksheets:
            if is_subject_sheet(ws):
                data[ws.title] = read_sheet(ws)
        _cache.update(stamp=stamp, data=data)
        return data


def student_stats(sd):
    out = []
    for s in sd["students"]:
        counts = {"p": 0, "x": 0, "l": 0, "e": 0, "r": 0}
        for dd in sd["dates"]:
            code = sd["cells"].get((s["row"], dd["col"]), "")
            if code and code in counts:
                counts[code] += 1
        total = sum(counts.values())
        rate = (counts["p"] + counts["r"] + counts["l"]) / total if total else None
        out.append({**s, **counts, "total": total, "rate": rate})
    return out


# ------------------------------------------------------------ writing data
def save_workbook(wb):
    if os.path.exists(XLSX):
        backup_workbook("auto", BACKUP_EVERY_MIN)      # the file as it was before this save
    tmp = XLSX + ".tmp"
    try:
        wb.save(tmp)
        os.replace(tmp, XLSX)
    except PermissionError:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise FileLocked()
    backup_latest()                                    # the file as it is now
    _cache.update(stamp=None, data=None)


def mutate(fn):
    ensure_workbook()
    with write_lock:
        try:
            wb = load_workbook(XLSX)
        except PermissionError:
            raise FileLocked()
        result = fn(wb)
        save_workbook(wb)
        return result


def get_subject_ws(wb, subject):
    if subject not in wb.sheetnames or not is_subject_sheet(wb[subject]):
        raise ValueError("That subject was not found in the workbook.")
    return wb[subject]


def find_date_col(ws, d):
    for c in range(FIRST_DATE_COL, min(ws.max_column, MAX_COL) + 1):
        if to_date(ws.cell(HEADER_ROW, c).value) == d:
            return c
    return None


def insert_date_col(ws, d):
    dated = []
    for c in range(FIRST_DATE_COL, min(ws.max_column, MAX_COL) + 1):
        x = to_date(ws.cell(HEADER_ROW, c).value)
        if x:
            dated.append((c, x))
    col = None
    for c, x in dated:
        if x > d:
            col = c
            break
    if col is None:
        col = dated[-1][0] + 1 if dated else FIRST_DATE_COL
    else:
        ws.insert_cols(col)
    if col >= MAX_COL:
        raise ValueError("This sheet has no room for more dates.")
    ws.cell(HEADER_ROW, col).value = d
    style_date_header(ws, col)
    return col


def apply_marks(subject, d, topic, items, new_names=()):
    def run(wb):
        ws = get_subject_ws(wb, subject)
        ensure_r_support(ws)
        col = find_date_col(ws, d)
        created = col is None
        if created:
            col = insert_date_col(ws, d)
        ws.cell(TOPIC_ROW, col).value = safe_text(topic) or None
        names, last = {}, FIRST_ROW - 1
        for r in range(FIRST_ROW, ws.max_row + 1):
            n = clean_name(str(ws.cell(r, 2).value or ""))
            if n:
                names.setdefault(n.lower(), r)
                last = r
        for n in new_names:                      # students added from a scanned sheet
            n = safe_text(n)
            if n and n.lower() not in names:
                last += 1
                ws.cell(last, 2).value = n
                names[n.lower()] = last
        saved, changes, added = 0, [], []
        for n in new_names:
            n = safe_text(n)
            if n and n.lower() in names:
                added.append(n)
        for it in items:
            name = clean_name(str(it.get("name", "")))
            raw_code = it.get("code")
            code = norm_code(raw_code)
            clearing = (not code) and raw_code in ("", None) and bool(it.get("clear"))
            if not name or (not code and not clearing):
                continue
            row = it.get("row")
            if not (isinstance(row, int) and clean_name(str(ws.cell(row, 2).value or "")).lower() == name.lower()):
                row = names.get(name.lower())
            if not row:
                continue
            cell = ws.cell(row, col)
            old = norm_code(cell.value)
            cell.value = code if code else None
            cell.alignment = CENTER
            cell.border = BORDER
            changes.append((name, old, code))
            saved += 1
        renumber(ws)
        return {"saved": saved, "created": created, "changes": changes, "added": added}
    return mutate(run)


def backup_workbook(tag, min_gap_min=0):
    """Save a timestamped copy of the workbook in the backups folder. Never blocks the action."""
    try:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        prefix = f"attendance_records_{tag}_"
        mine = sorted(f for f in os.listdir(BACKUP_DIR) if f.startswith(prefix))
        if min_gap_min and mine:
            if time.time() - os.path.getmtime(os.path.join(BACKUP_DIR, mine[-1])) < min_gap_min * 60:
                return
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        shutil.copyfile(XLSX, os.path.join(BACKUP_DIR, f"{prefix}{stamp}.xlsx"))
        mine = sorted(f for f in os.listdir(BACKUP_DIR) if f.startswith(prefix))
        for old in mine[:-BACKUP_KEEP.get(tag, 30)]:
            os.remove(os.path.join(BACKUP_DIR, old))
    except OSError:
        pass


def backup_latest():
    """Keep one always-up-to-date copy (attendance_records_LATEST.xlsx) next to the history copies."""
    try:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        shutil.copyfile(XLSX, os.path.join(BACKUP_DIR, "attendance_records_LATEST.xlsx"))
    except OSError:
        pass


def delete_date(subject, d):
    """Remove one date column (topic, header and every mark) from a subject's sheet."""
    def run(wb):
        ws = get_subject_ws(wb, subject)
        col = find_date_col(ws, d)
        if col is None:
            raise ValueError("That date was not found.")
        topic = clean_name(str(ws.cell(TOPIC_ROW, col).value or ""))
        marks = sum(1 for r in range(FIRST_ROW, ws.max_row + 1) if norm_code(ws.cell(r, col).value))
        ws.delete_cols(col)
        return marks, topic
    return mutate(run)



def add_students(subjects, names):
    def run(wb):
        added, skipped = 0, []
        for sub in subjects:
            ws = get_subject_ws(wb, sub)
            existing, last = set(), FIRST_ROW - 1
            for r in range(FIRST_ROW, ws.max_row + 1):
                n = clean_name(str(ws.cell(r, 2).value or ""))
                if n:
                    existing.add(n.lower())
                    last = r
            for n in names:
                if n.lower() in existing:
                    skipped.append(f"{n} ({sub})")
                    continue
                last += 1
                ws.cell(last, 2).value = n
                existing.add(n.lower())
                added += 1
            renumber(ws)
        return added, skipped
    return mutate(run)


def remove_student(subject, row, name, everywhere):
    def run(wb):
        targets = [s.title for s in wb.worksheets if is_subject_sheet(s)] if everywhere else [subject]
        removed = 0
        for sub in targets:
            ws = get_subject_ws(wb, sub)
            hit = None
            if (not everywhere and isinstance(row, int)
                    and clean_name(str(ws.cell(row, 2).value or "")).lower() == name.lower()):
                hit = row
            else:
                for r in range(FIRST_ROW, ws.max_row + 1):
                    if clean_name(str(ws.cell(r, 2).value or "")).lower() == name.lower():
                        hit = r
                        break
            if hit:
                ws.delete_rows(hit)
                renumber(ws)
                removed += 1
        return removed
    return mutate(run)


# -------------------------------------------------------- subject customization
def get_subject_image_file(subject):
    if not os.path.exists(SUBJECT_IMG_DIR):
        return None
    safe = re.sub(r'[^a-zA-Z0-9_\-]', '_', clean_sheet_name(subject).lower())
    for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        fn = f"{safe}{ext}"
        if os.path.isfile(os.path.join(SUBJECT_IMG_DIR, fn)):
            return fn
    return None


def subject_image_url(subject):
    img = get_subject_image_file(subject)
    return url_for("subject_image", subject=subject) if img else None


def remove_subject_image(subject):
    if not os.path.exists(SUBJECT_IMG_DIR):
        return
    safe = re.sub(r'[^a-zA-Z0-9_\-]', '_', clean_sheet_name(subject).lower())
    for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        p = os.path.join(SUBJECT_IMG_DIR, f"{safe}{ext}")
        if os.path.isfile(p):
            try:
                os.remove(p)
            except OSError:
                pass


def delete_subject(name):
    def run(wb):
        ws = get_subject_ws(wb, name)
        wb.remove(ws)
        if not wb.worksheets:
            wb.create_sheet("Guide")
    mutate(run)
    remove_subject_image(name)


def add_subject(name, copy_from):
    def run(wb):
        if name.lower() in [s.lower() for s in wb.sheetnames]:
            raise ValueError("A sheet with that name already exists.")
        names = []
        if copy_from and copy_from in wb.sheetnames and is_subject_sheet(wb[copy_from]):
            src = wb[copy_from]
            for r in range(FIRST_ROW, src.max_row + 1):
                n = clean_name(str(src.cell(r, 2).value or ""))
                if n:
                    names.append(n)
        ws = wb.create_sheet(name, index=len([s for s in wb.worksheets if is_subject_sheet(s)]))
        setup_sheet(ws, name)
        for i, n in enumerate(names):
            ws.cell(FIRST_ROW + i, 2).value = n
        renumber(ws)
        return len(names)
    return mutate(run)
