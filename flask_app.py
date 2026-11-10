"""
School attendance website that uses an Excel workbook as its database.

Layout of every subject sheet (matches a classic attendance sheet):
  - one sheet (tab) per subject
  - students go down the side (column B, from row 5)
  - dates go across the top (row 4, from column H)
  - the lesson topic for each date sits in row 3
  - cells hold  p = present, x = absent, l = late, e = excused
  - columns C-G are formulas (Present, Absent, Late, Excused, Rate)

Run it with start.bat (double-click) or:  py app.py
"""
import base64
import csv
import io
import unicodedata
import difflib
import hashlib
import hmac
import secrets
import shutil
from markupsafe import escape
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from datetime import date, datetime, timedelta

from flask import (Flask, flash, g, jsonify, redirect, render_template, request, session,
                   send_file, url_for)
from jinja2 import DictLoader
from openpyxl import Workbook, load_workbook
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.datavalidation import DataValidation

# ----------------------------------------------------------------- settings
HOST = "0.0.0.0"            # "0.0.0.0" allows phones and other devices on your Wi-Fi to open the site
START_PORT = 5000
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
XLSX = os.path.join(BASE_DIR, "attendance_records.xlsx")

SAMPLE_SUBJECTS = ["College Algebra", "MMW"]
SAMPLE_STUDENTS = ["Sample Student A", "Sample Student B", "Sample Student C"]
LOW_RATE = 0.80             # attendance rates below this are shown in red

# AI sheet scanning (optional). The key comes from the ANTHROPIC_API_KEY environment
# variable or from a file called api_key.txt next to this script.
API_KEY_FILE = os.path.join(BASE_DIR, "api_key.txt")
SUBJECT_IMG_DIR = os.path.join(BASE_DIR, "subject_images")
AI_MODEL = os.environ.get("ATTENDANCE_MODEL", "claude-sonnet-5-5")          # used with Claude keys
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")         # used with Gemini keys
GEMINI_FALLBACKS = [m.strip() for m in os.environ.get("GEMINI_FALLBACK_MODEL", "gemini-flash-lite-latest").split(",") if m.strip()]
PASSWORD_FILE = os.path.join(BASE_DIR, "passwords.txt")    # lines: teacher=...  and (optional) student=...
SECRET_FILE = os.path.join(BASE_DIR, "secret_key.txt")      # made automatically; keeps sign-ins private
MIN_PASSWORD = 8
OPEN_MODE = False        # On PythonAnywhere, always False to require password sign-in
# Backups: a copy of the workbook is saved here automatically. To keep them in Google Drive,
# set the environment variable ATTENDANCE_BACKUP_DIR to a folder inside your Google Drive folder.
BACKUP_DIR = os.environ.get("ATTENDANCE_BACKUP_DIR", "").strip() or os.path.join(BASE_DIR, "backups")
BACKUP_EVERY_MIN = 10       # at most one timestamped copy per this many minutes of saving
BACKUP_KEEP = {"auto": 60, "before_delete_date": 30}   # how many timestamped copies of each kind to keep
# Google Meet CSV import
MEET_PRESENT_PCT = 0.75     # present if the student was in the call at least this share of the meeting
MEET_ALIAS_FILE = os.path.join(BASE_DIR, "meet_aliases.json")   # remembers "Meet name -> class-list name"
MAX_CSV = 1024 * 1024
LOG_FILE = os.path.join(BASE_DIR, "changes_log.jsonl")     # the "Changes log" page reads this file
LOG_MAX_SHOWN = 500
MAX_UPLOAD = 12 * 1024 * 1024
MAX_IMAGES = 6

TOPIC_ROW, HEADER_ROW, FIRST_ROW = 3, 4, 5
FIRST_DATE_COL = 8          # column H
MAX_COL, MAX_ROW = 200, 300
CODES = {"p": "Present", "x": "Absent", "l": "Late", "e": "Excused", "r": "Recited"}

app = Flask(__name__)


def load_secret():
    env = os.environ.get("ATTENDANCE_SECRET_KEY", "").strip()
    if len(env) >= 32:
        return env
    try:
        with open(SECRET_FILE, encoding="utf-8") as f:
            s = f.read().strip()
        if len(s) >= 32:
            return s
    except OSError:
        pass
    s = secrets.token_hex(32)
    try:
        with open(SECRET_FILE, "w", encoding="utf-8") as f:
            f.write(s)
    except OSError:
        pass
    return s


app.secret_key = load_secret()
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
                  PERMANENT_SESSION_LIFETIME=timedelta(hours=12))
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD * 4
write_lock = threading.RLock()


class FileLocked(Exception):
    pass


# ------------------------------------------------------------ small helpers
def clean_name(s):
    return re.sub(r"\s+", " ", (s or "").strip())


def safe_text(s):
    """Text going into Excel: tidy it and stop it being read as a formula."""
    return clean_name(s).lstrip("=+-@ ")


def clean_sheet_name(s):
    return clean_name(re.sub(r"[\[\]:*?/\\]", " ", s or ""))[:31]


def norm_code(v):
    if v is None:
        return ""
    s = str(v).strip().lower()
    return s[0] if s and s[0] in CODES else ""


def to_date(v):
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    if isinstance(v, str):
        for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m/%d/%y", "%b %d %Y", "%B %d %Y", "%d-%b-%Y"):
            try:
                return datetime.strptime(v.strip(), fmt).date()
            except ValueError:
                pass
    return None


def parse_iso(s, default=None):
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return default


# ------------------------------------------------------------- changes log
log_lock = threading.Lock()
LETTER = {"p": "P", "x": "A", "l": "L", "e": "E", "r": "R", "": "blank"}


def who_is_it():
    ip = request.remote_addr or ""
    return "This PC" if ip in ("127.0.0.1", "::1") else (ip or "unknown")


def log_change(action, subject="", detail=""):
    """Add one line to changes_log.jsonl. Never lets a logging problem break a save."""
    try:
        entry = {"t": datetime.now().isoformat(timespec="seconds"), "action": action,
                 "subject": subject, "detail": detail, "who": who_is_it()}
        with log_lock:
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def read_log():
    rows = []
    try:
        with log_lock, open(LOG_FILE, encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        return rows, 0
    for line in lines:
        try:
            e = json.loads(line)
            t = datetime.fromisoformat(e["t"])
        except (ValueError, KeyError, TypeError):
            continue
        e["when"] = t.strftime("%b %d, %Y  %I:%M %p").replace(" 0", " ")
        rows.append(e)
    rows.reverse()
    return rows[:LOG_MAX_SHOWN], len(rows)


def short_list(items, cap):
    items = list(items)
    return ", ".join(items[:cap]) + (f" (+{len(items) - cap} more)" if len(items) > cap else "")


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


NAME_COLS = ("full name", "name", "participant", "participant name", "display name")
TIME_COLS = ("time in call", "duration", "total time", "time")


def name_tokens(s):
    """Lower-case words of a name with accents and punctuation removed ('Teña, J.' -> ['tena'])."""
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).lower()
    return [t for t in re.split(r"[^a-z0-9]+", s) if len(t) >= 2]


def parse_clock(v):
    s = str(v or "").strip()
    m = re.fullmatch(r"(?:(\d+):)?(\d{1,2}):(\d{2})", s)
    if m:
        return int(m.group(1) or 0) * 3600 + int(m.group(2)) * 60 + int(m.group(3))
    m = re.fullmatch(r"(\d+(?:\.\d+)?)\s*(?:m|min|mins|minute|minutes)?", s, re.I)
    return int(float(m.group(1)) * 60) if m else None


def parse_meet_csv(raw):
    """Read a Google Meet attendance export. Returns who joined, for how long, and the meeting length."""
    for enc in ("utf-8-sig", "cp1252"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = raw.decode("latin-1")
    rows = list(csv.reader(io.StringIO(text)))
    created = ended = None
    head = None
    for i, row in enumerate(rows[:40]):
        line = " ".join(row)
        m = re.search(r"Created on\s+(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2})", line)
        if m:
            created = datetime.fromisoformat(m.group(1))
        m = re.search(r"Ended on\s+(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2})", line)
        if m:
            ended = datetime.fromisoformat(m.group(1))
        low = [c.strip().lower() for c in row]
        if head is None and any(c in NAME_COLS for c in low) and any(c in TIME_COLS for c in low):
            head = (i, next(j for j, c in enumerate(low) if c in NAME_COLS),
                    next(j for j, c in enumerate(low) if c in TIME_COLS))
    if head is None:
        raise ValueError("I could not find the 'Full Name' and 'Time in Call' columns. Is this the Meet attendance CSV?")
    hi, ni, ti = head
    people = {}
    for row in rows[hi + 1:]:
        if len(row) <= max(ni, ti):
            continue
        name, secs = clean_name(row[ni])[:120], parse_clock(row[ti])
        if name and secs is not None:
            people[name] = people.get(name, 0) + secs
    if not people:
        raise ValueError("That file has no attendees in it.")
    length = int((ended - created).total_seconds()) if created and ended and ended > created else 0
    length = max(length, max(people.values()))
    return {"people": list(people.items()), "length": length, "created": created, "ended": ended}


def read_aliases():
    try:
        with open(MEET_ALIAS_FILE, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def write_aliases(d):
    try:
        with write_lock, open(MEET_ALIAS_FILE, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=1)
    except OSError:
        pass


def match_roster(meet_name, roster, tokens, aliases):
    """Find which class-list student a Meet display name belongs to ('' when unsure)."""
    key = clean_name(meet_name).lower()
    saved = aliases.get(key)
    if saved in roster:
        return saved
    mt = name_tokens(meet_name)
    if len(mt) < 2:
        return ""
    found = []
    for rn in roster:
        rt = tokens[rn]
        squashed = "".join(rt)
        hits = 0
        for t in mt:
            if (t in rt or (len(t) >= 6 and t in squashed)
                    or any(len(t) >= 4 and len(r) >= 4 and difflib.SequenceMatcher(None, t, r).ratio() >= 0.85 for r in rt)):
                hits += 1
        if hits >= 2 and hits / len(mt) >= 0.6:
            found.append((hits, hits / len(mt), hits / max(len(rt), 1), rn))
    if not found:
        return ""
    found.sort(reverse=True)
    if len(found) > 1 and found[0][:3] == found[1][:3]:
        return ""                                   # two students look equally likely: let the user choose
    return found[0][3]


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


# ------------------------------------------------------------- AI sheet reader
class AIError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code, self.message = code, message


def get_api_key():
    key = ""
    for var in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"):
        key = os.environ.get(var, "").strip()
        if key:
            break
    if not key and os.path.exists(API_KEY_FILE):
        try:
            with open(API_KEY_FILE, encoding="utf-8") as f:
                key = f.read().strip()
        except OSError:
            key = ""
    return key


SHEET_TOOL = {
    "name": "record_sheet",
    "description": "Record every name found on the photographed attendance sheet.",
    "input_schema": {
        "type": "object",
        "properties": {
            "sheet_title": {"type": "string", "description": "Class or title written at the top, if any"},
            "date_text": {"type": "string", "description": "Date exactly as written on the sheet, or empty"},
            "date_iso": {"type": "string", "description": "That date as YYYY-MM-DD (month/day/year unless clearly otherwise), or empty"},
            "entries": {
                "type": "array",
                "description": "One item per name line on the sheet, in order",
                "items": {
                    "type": "object",
                    "properties": {
                        "written_name": {"type": "string", "description": "The name as you read it"},
                        "roster_match": {"type": "string", "description": "The matching name copied exactly from the class list, or empty if nobody on the class list fits"},
                        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                        "mark": {"type": "string", "enum": ["signed", "checked", "crossed_out", "none"],
                                 "description": "What is written next to the name: signature or scribble = signed, tick = checked, name struck through = crossed_out, nothing = none"},
                        "written_status": {"type": "string", "enum": ["p", "x", "l", "e", ""],
                                           "description": "Only if the sheet itself writes a status next to the name (P/present, A or X/absent, L/late, E/excused); otherwise empty"},
                        "attended_percent": {"type": "number",
                                             "description": "For online-meeting attendance reports: the attended percentage shown for this person (0-100). Use -1 if no percentage is shown"},
                    },
                    "required": ["written_name", "roster_match", "confidence", "mark"],
                },
            },
        },
        "required": ["entries"],
    },
}


def build_prompt(roster):
    class_list = "\n".join(f"- {n}" for n in roster) or "(empty)"
    return (
        "You are given one or more photos or screenshots of ONE attendance record for a class: a handwritten sheet, "
        "or an online-meeting attendance report with durations and percentages. Several images may be pages or "
        "scrolled parts of the same list and may overlap; list each person once. Read carefully and report "
        "every name line, in order (record_sheet format). Do not skip lines and do not invent names. "
        "The record may also contain people who are NOT in this class (other sections, teachers, room or school "
        "accounts): still list them, with an empty roster_match.\n\n"
        "The official class list is:\n" + class_list + "\n\n"
        "For each line on the sheet, set roster_match to the class-list name it refers to, copied EXACTLY as spelled "
        "in the class list. Names on paper may be written 'Last, First M.' or 'First Last', abbreviated or misspelled. "
        "If nobody on the class list plausibly fits, leave roster_match empty. Never match two lines to the same person. "
        "If handwriting is hard to read, give your best guess and lower the confidence. "
        "Do not add class-list students who are not on the sheet."
    )


def provider_of(key):
    """Claude keys start with sk-ant-; any other key is treated as a Google Gemini key (AIza... or AQ....)."""
    key = key or ""
    return "anthropic" if key.startswith("sk-ant-") or not key else "gemini"


def call_claude(images, roster, key=None):
    """Send the photos [(base64, media_type), ...] to Claude and return the structured reading."""
    key = key or get_api_key()
    if not key:
        raise AIError("no_key", "No API key is set up yet.")
    content = [{"type": "image", "source": {"type": "base64", "media_type": mt, "data": b64}} for b64, mt in images]
    content.append({"type": "text", "text": build_prompt(roster)})
    payload = {
        "model": AI_MODEL,
        "max_tokens": 8000,
        "tools": [SHEET_TOOL],
        "tool_choice": {"type": "tool", "name": "record_sheet"},
        "messages": [{"role": "user", "content": content}],
    }
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages", data=json.dumps(payload).encode("utf-8"),
        headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = json.load(resp)
    except urllib.error.HTTPError as e:
        try:
            detail = json.load(e).get("error", {}).get("message", "")
        except Exception:
            detail = ""
        if e.code in (401, 403):
            raise AIError("bad_key", "The API key was rejected. Check that it was copied completely.")
        if e.code == 429 or e.code >= 500:
            raise AIError("busy", "The AI service is busy right now. Wait a minute and try again.")
        if "credit" in detail.lower():
            raise AIError("credit", "The API account has no credit left. Add credit in the Claude Console and try again.")
        raise AIError("api", "The AI service could not read this photo. " + detail)
    except (urllib.error.URLError, TimeoutError, OSError):
        raise AIError("network", "Could not reach the AI service. Check the internet connection and try again.")
    for block in body.get("content", []):
        if block.get("type") == "tool_use":
            return block.get("input") or {}
    raise AIError("parse", "The AI did not return a readable result. Try a clearer photo.")


def gemini_schema(node):
    """Convert the tool schema into the schema format Gemini accepts."""
    if isinstance(node, dict):
        out = {}
        for k, v in node.items():
            if k == "enum" and "" in v:      # Gemini does not accept an empty-string enum value
                continue
            out[k] = gemini_schema(v)
        return out
    if isinstance(node, list):
        return [gemini_schema(x) for x in node]
    return node


def call_gemini(images, roster, key=None):
    """Same job as call_claude, using a Google Gemini API key."""
    key = key or get_api_key()
    if not key:
        raise AIError("no_key", "No API key is set up yet.")
    parts = [{"text": build_prompt(roster)}]
    parts += [{"inline_data": {"mime_type": mt, "data": b64}} for b64, mt in images]
    payload = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {"temperature": 0, "responseMimeType": "application/json",
                             "responseSchema": gemini_schema(SHEET_TOOL["input_schema"])},
    }
    data = json.dumps(payload).encode("utf-8")

    def post(style, model):
        base = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        url, headers = base, {"content-type": "application/json"}
        if style == "header":
            headers["x-goog-api-key"] = key
        elif style == "query":
            url = base + "?key=" + urllib.parse.quote(key, safe="")
        else:
            headers["Authorization"] = "Bearer " + key
        try:
            with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=headers), timeout=120) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            try:
                detail = json.load(e).get("error", {}).get("message", "")
            except Exception:
                detail = ""
            if e.code in (401, 403) or "api key" in detail.lower():
                raise AIError("bad_key", "Google rejected the Gemini API key. " + detail[:160])
            if e.code == 429:
                raise AIError("busy", "The Gemini free limit was reached for now. Wait a minute (or until tomorrow) and try again.")
            if e.code >= 500:
                raise AIError("busy", "Google's Gemini service is overloaded right now (the site already retried a few times). Wait a minute and try again.")
            if e.code == 404:
                raise AIError("api", "Gemini model '" + model + "' was not found. Set the GEMINI_MODEL setting to a current model name.")
            raise AIError("api", "The AI service could not read this photo. " + detail[:200])
        except (urllib.error.URLError, TimeoutError, OSError):
            raise AIError("network", "Could not reach the AI service. Check the internet connection and try again.")

    # Google's newer "AQ." keys are reported to be refused in some setups, so try each way of sending the key.
    styles = ["header", "query", "bearer"] if key.startswith("AQ.") else ["header"]

    def attempt(model):
        last = None
        for style in styles:
            try:
                return post(style, model)
            except AIError as err:
                last = err
                if err.code != "bad_key":
                    raise
        if key.startswith("AQ."):
            last.message += (" Google's new AQ. keys are sometimes refused by the Gemini web API. "
                             "Try creating a new key, or use a Claude key instead.")
        raise last

    # The free Gemini models are often overloaded: retry a few times, then try a lighter fallback model.
    models = [GEMINI_MODEL] + [m for m in GEMINI_FALLBACKS if m != GEMINI_MODEL]
    body, busy = None, None
    for i, model in enumerate(models):
        for n in range(3):
            try:
                body = attempt(model)
                break
            except AIError as err:
                if i == 0 and err.code != "busy":
                    raise                       # wrong key, bad photo, etc.: retrying will not help
                if err.code != "busy" and i > 0:
                    break                       # fallback model unusable: move on
                busy = busy or err
                if n < 2:
                    time.sleep(2 * (n + 1))
        if body is not None:
            break
    if body is None:
        raise busy
    try:
        text = body["candidates"][0]["content"]["parts"][0]["text"]
        result = json.loads(text)
    except (KeyError, IndexError, TypeError, ValueError):
        raise AIError("parse", "The AI did not return a readable result. Try a clearer photo.")
    if isinstance(result, list):             # tolerate a bare list of entries
        result = {"entries": result}
    if not isinstance(result, dict):
        raise AIError("parse", "The AI did not return a readable result. Try a clearer photo.")
    return result


def call_ai(images, roster):
    key = get_api_key()
    if not key:
        raise AIError("no_key", "No API key is set up yet.")
    fn = call_gemini if provider_of(key) == "gemini" else call_claude
    return fn(images, roster, key)


RANK = {"low": 0, "medium": 1, "high": 2}


def _percent(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return -1
    return round(x, 1) if 0 <= x <= 100 else -1


def normalize_scan(raw, roster):
    """Clean the AI output: real class-list names only, repeated lines merged, safe text."""
    lookup = {n.lower(): n for n in roster}
    merged, order = {}, []
    for it in (raw.get("entries") or []):
        if not isinstance(it, dict):
            continue
        written = safe_text(str(it.get("written_name", "")))[:80]
        if not written:
            continue
        match = lookup.get(clean_name(str(it.get("roster_match", ""))).lower(), "")
        conf = it.get("confidence") if it.get("confidence") in RANK else "medium"
        if not match:
            close = difflib.get_close_matches(written.lower(), list(lookup), n=1, cutoff=0.85)
            if close:
                match, conf = lookup[close[0]], "medium"
        mark = it.get("mark") if it.get("mark") in ("signed", "checked", "crossed_out", "none") else "none"
        entry = {"written_name": written, "roster_match": match, "confidence": conf, "mark": mark,
                 "written_status": norm_code(it.get("written_status")),
                 "attended_percent": _percent(it.get("attended_percent"))}
        key = ("m", match) if match else ("u", written.lower())
        old = merged.get(key)
        if old is None:                      # first time this person appears
            merged[key] = entry
            order.append(key)
            continue
        # the same person on overlapping photos: keep the most informative values
        if old["mark"] == "none" and mark != "none":
            old["mark"] = mark
        if not old["written_status"]:
            old["written_status"] = entry["written_status"]
        old["attended_percent"] = max(old["attended_percent"], entry["attended_percent"])
        if RANK[conf] > RANK[old["confidence"]]:
            old["confidence"] = conf
    d = parse_iso(str(raw.get("date_iso", "")))
    return {"sheet_title": safe_text(str(raw.get("sheet_title", "")))[:60],
            "date_text": clean_name(str(raw.get("date_text", "")))[:30],
            "date_iso": d.isoformat() if d else "", "entries": [merged[k] for k in order]}


# ----------------------------------------------------------------- templates
BASE = r"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover, maximum-scale=1">
<meta name="theme-color" content="#2563eb">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="default">
<title>{% block title %}Attendance{% endblock %}</title>
<style>
:root {
  --bg: #f8fafc;
  --card: #ffffff;
  --ink: #0f172a;
  --muted: #64748b;
  --line: #e2e8f0;
  --brand: #2563eb;
  --brand2: #1d4ed8;
  --hover: #f1f5f9;
  --p: #10b981;
  --pbg: #ecfdf5;
  --x: #ef4444;
  --xbg: #fef2f2;
  --l: #f59e0b;
  --lbg: #fffbeb;
  --e: #3b82f6;
  --ebg: #eff6ff;
  --r: #7c3aed;
  --rbg: #ede9fe;
  --radius: 12px;
}
* { box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--ink);
  font: 15px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
  touch-action: manipulation;
  -webkit-font-smoothing: antialiased;
}
header.top {
  background: #fff;
  border-bottom: 1px solid var(--line);
  position: sticky;
  top: 0;
  z-index: 50;
  padding: 0 16px;
  padding-top: env(safe-area-inset-top, 0px);
}
.header-inner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  height: 54px;
  max-width: 1100px;
  margin: 0 auto;
}
.brand {
  font-weight: 700;
  font-size: 17px;
  color: var(--ink);
  text-decoration: none;
  display: flex;
  align-items: center;
  gap: 8px;
}
nav.desktop-nav {
  display: flex;
  gap: 4px;
  align-items: center;
}
nav.desktop-nav a {
  padding: 8px 12px;
  border-radius: 8px;
  color: var(--muted);
  text-decoration: none;
  font-weight: 600;
  font-size: 14px;
  transition: all 0.15s ease;
}
nav.desktop-nav a.on {
  color: var(--brand);
  background: var(--ebg);
}
nav.desktop-nav a:hover {
  color: var(--ink);
  background: var(--hover);
}
.nav-toggle-btn {
  display: none;
  background: #f8fafc;
  border: 1px solid var(--line);
  padding: 7px 12px;
  border-radius: 8px;
  font-weight: 600;
  font-size: 14px;
  color: var(--ink);
  cursor: pointer;
}
.mobile-nav-panel {
  display: none;
  border-top: 1px solid var(--line);
  padding: 10px 0 14px;
  background: #fff;
}
.mobile-nav-panel.open {
  display: block;
}
.mobile-nav-panel a {
  display: block;
  padding: 10px 14px;
  color: var(--ink);
  text-decoration: none;
  font-weight: 600;
  font-size: 15px;
  border-radius: 8px;
}
.mobile-nav-panel a.on {
  color: var(--brand);
  background: var(--ebg);
}
@media (max-width: 860px) {
  nav.desktop-nav { display: none; }
  .nav-toggle-btn { display: inline-flex; align-items: center; gap: 6px; }
}
main {
  max-width: 1100px;
  margin: 0 auto;
  padding: 16px 16px 115px;
}
@media (max-width: 600px) {
  main { padding: 12px 10px 120px; }
}
h1 { font-size: 22px; margin: 4px 0 14px; font-weight: 700; letter-spacing: -0.02em; }
h2 { font-size: 17px; margin: 0 0 10px; font-weight: 600; }
.card {
  background: var(--card);
  border: 1px solid var(--line);
  border-radius: var(--radius);
  padding: 16px;
  margin-bottom: 14px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.04);
}
.grid2 { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 14px; }
.tabs {
  display: flex;
  gap: 8px;
  overflow-x: auto;
  white-space: nowrap;
  padding: 2px 2px 10px;
  margin-bottom: 14px;
  -webkit-overflow-scrolling: touch;
  scrollbar-width: none;
}
.tabs::-webkit-scrollbar { display: none; }
.tab {
  flex-shrink: 0;
  padding: 8px 16px;
  border-radius: 9999px;
  border: 1px solid var(--line);
  background: #fff;
  color: var(--ink);
  text-decoration: none;
  font-weight: 600;
  font-size: 14px;
  transition: all 0.15s ease;
}
.tab.on {
  background: var(--brand);
  border-color: var(--brand);
  color: #fff;
  box-shadow: 0 2px 8px rgba(37,99,235,0.25);
}
.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 9px 14px;
  border-radius: 8px;
  border: 1px solid var(--line);
  background: #fff;
  color: var(--ink);
  font: inherit;
  font-weight: 600;
  cursor: pointer;
  text-decoration: none;
  user-select: none;
  touch-action: manipulation;
  transition: all 0.12s ease;
}
.btn:active { transform: scale(0.97); }
.btn:hover { background: var(--hover); }
.btn.primary { background: var(--brand); border-color: var(--brand); color: #fff; }
.btn.primary:hover { background: var(--brand2); }
.btn.danger { color: var(--x); border-color: #fca5a5; }
.btn.danger:hover { background: var(--xbg); }
.btn.small { padding: 5px 10px; font-size: 13px; }
.btn:disabled { opacity: 0.55; cursor: not-allowed; transform: none; }
.muted { color: var(--muted); }
.flash { padding: 12px 14px; border-radius: 10px; margin-bottom: 14px; font-weight: 600; font-size: 14px; }
.flash.ok { background: var(--pbg); color: #065f46; border: 1px solid #a7f3d0; }
.flash.err { background: var(--xbg); color: #991b1b; border: 1px solid #fecaca; }
.stats { display: flex; gap: 8px; margin: 10px 0; flex-wrap: wrap; }
.stat { flex: 1; min-width: 60px; text-align: center; border-radius: 10px; padding: 10px 4px; }
.stat b { display: block; font-size: 22px; line-height: 1.1; }
.stat span { font-size: 12px; font-weight: 600; }
.s-p { background: var(--pbg); color: var(--p); }
.s-x { background: var(--xbg); color: var(--x); }
.s-l { background: var(--lbg); color: var(--l); }
.s-e { background: var(--ebg); color: var(--e); }
.s-r { background: var(--rbg); color: var(--r); }
table { border-collapse: collapse; width: 100%; }
th, td { padding: 8px 10px; text-align: left; border-bottom: 1px solid var(--line); }
th { font-size: 12px; text-transform: uppercase; letter-spacing: 0.04em; color: var(--muted); font-weight: 700; }
td.n, th.n { text-align: center; }
.pill { display: inline-block; min-width: 44px; text-align: center; padding: 3px 8px; border-radius: 9999px; font-weight: 700; font-size: 12px; background: var(--pbg); color: var(--p); }
.pill.low { background: var(--xbg); color: var(--x); }
.pill.none { background: #f1f5f9; color: var(--muted); }
.chip { display: inline-block; padding: 3px 10px; border-radius: 9999px; font-size: 13px; font-weight: 600; background: var(--xbg); color: var(--x); margin: 2px 4px 2px 0; }
.badge { display: inline-block; padding: 4px 10px; border-radius: 9999px; font-size: 12px; font-weight: 700; }
.badge.done { background: var(--pbg); color: #065f46; }
.badge.todo { background: var(--lbg); color: #92400e; }
details summary { cursor: pointer; font-weight: 600; color: var(--brand); margin-top: 6px; }
.scroll { overflow: auto; max-height: 70vh; border: 1px solid var(--line); border-radius: 10px; background: #fff; }
table.grid th, table.grid td { border: 1px solid var(--line); white-space: nowrap; padding: 7px 10px; }
table.grid thead th { position: sticky; top: 0; background: #f1f5f9; z-index: 2; }
table.grid .sticky { position: sticky; left: 0; background: #fff; z-index: 1; font-weight: 600; }
table.grid thead .sticky { z-index: 3; background: #f1f5f9; }
table.grid small { display: block; font-weight: 400; text-transform: none; letter-spacing: 0; max-width: 110px; overflow: hidden; text-overflow: ellipsis; color: var(--muted); }
td.c { text-align: center; font-weight: 800; }
td.c.p { background: var(--pbg); color: var(--p); }
td.c.x { background: var(--xbg); color: var(--x); }
td.c.l { background: var(--lbg); color: var(--l); }
td.c.e { background: var(--ebg); color: var(--e); }
td.c.r { background: var(--rbg); color: var(--r); }
form.inline { display: inline; }
.toolbar { display: flex; gap: 10px; flex-wrap: wrap; align-items: center; margin-bottom: 12px; }
.toolbar input[type=date], .toolbar input[type=text], textarea, input.txt, select { font: inherit; padding: 8px 10px; border: 1px solid var(--line); border-radius: 8px; background: #fff; }
.toolbar .grow { flex: 1; min-width: 180px; }
</style></head><body>
<header class="top">
  <div class="header-inner">
    <a href="{{ url_for('dashboard') if role == 'teacher' else (url_for('records') if role == 'student' else url_for('login')) }}" class="brand">📋 Attendance</a>
    {% if role == 'teacher' %}
    <nav class="desktop-nav">
      <a href="{{ url_for('dashboard') }}" class="{{ 'on' if page=='dashboard' }}">Dashboard</a>
      <a href="{{ url_for('mark') }}" class="{{ 'on' if page=='mark' }}">Mark attendance</a>
      <a href="{{ url_for('scan') }}" class="{{ 'on' if page=='scan' }}">📥 Import</a>
      <a href="{{ url_for('records') }}" class="{{ 'on' if page=='records' }}">Records</a>
      <a href="{{ url_for('students') }}" class="{{ 'on' if page=='students' }}">Students</a>
      <a href="{{ url_for('log_page') }}" class="{{ 'on' if page=='log' }}">Log</a>
      <a href="{{ url_for('files_page') }}" class="{{ 'on' if page=='files' }}">📁 File</a>
      <a href="{{ url_for('download') }}">⬇ Download</a>
      {% if auth_on %}<a href="{{ url_for('logout') }}" style="color:var(--x)">Sign out</a>{% endif %}
    </nav>
    <button class="nav-toggle-btn" id="navToggleBtn" type="button" aria-label="Toggle menu">☰ Menu</button>
    {% elif role == 'student' %}
    <nav class="desktop-nav">
      <a href="{{ url_for('records') }}" class="on">Records</a>
      {% if auth_on %}<a href="{{ url_for('logout') }}" style="color:var(--x)">Sign out</a>{% endif %}
    </nav>
    <button class="nav-toggle-btn" id="navToggleBtn" type="button" aria-label="Toggle menu">☰ Menu</button>
    {% endif %}
  </div>
  {% if role == 'teacher' %}
  <div class="mobile-nav-panel" id="mobileNavPanel">
    <a href="{{ url_for('mark') }}" class="{{ 'on' if page=='mark' }}">📋 Mark attendance</a>
    <a href="{{ url_for('records') }}" class="{{ 'on' if page=='records' }}">📊 Records</a>
    <a href="{{ url_for('scan') }}" class="{{ 'on' if page=='scan' }}">📥 Import attendance</a>
    <a href="{{ url_for('dashboard') }}" class="{{ 'on' if page=='dashboard' }}">🏠 Dashboard</a>
    <a href="{{ url_for('students') }}" class="{{ 'on' if page=='students' }}">👥 Students &amp; subjects</a>
    <a href="{{ url_for('log_page') }}" class="{{ 'on' if page=='log' }}">📝 Changes log</a>
    <a href="{{ url_for('files_page') }}" class="{{ 'on' if page=='files' }}">📁 Excel file</a>
    <a href="{{ url_for('download') }}">⬇ Download copy</a>
    {% if auth_on %}<a href="{{ url_for('logout') }}" style="color:var(--x)">🚪 Sign out</a>{% endif %}
  </div>
  {% elif role == 'student' %}
  <div class="mobile-nav-panel" id="mobileNavPanel">
    <a href="{{ url_for('records') }}" class="on">📊 Records</a>
    {% if auth_on %}<a href="{{ url_for('logout') }}" style="color:var(--x)">🚪 Sign out</a>{% endif %}
  </div>
  {% endif %}
</header>
<main>
{% with msgs = get_flashed_messages(with_categories=true) %}{% for cat, m in msgs %}<div class="flash {{ cat }}">{{ m }}</div>{% endfor %}{% endwith %}
{% if tabs %}<div class="tabs">{% for t in tabs %}<a class="tab {{ 'on' if t.active }}" href="{{ t.url }}">{{ t.name }}</a>{% endfor %}</div>{% endif %}
{% block body %}{% endblock %}
</main>
<script>
const nBtn = document.getElementById('navToggleBtn');
const nPan = document.getElementById('mobileNavPanel');
if (nBtn && nPan) {
  nBtn.onclick = () => { nPan.classList.toggle('open'); };
}
</script>
</body></html>"""

DASHBOARD = r"""{% extends "base.html" %}
{% block body %}
<h1>Dashboard <span class="muted" style="font-size:15px;font-weight:400">· {{ today_label }}</span></h1>
{% if not cards %}<div class="card">No subject sheets found. Go to <a href="{{ url_for('students') }}">Students &amp; subjects</a> to add one.</div>{% endif %}
<div class="grid2">
{% for c in cards %}
<div class="card" style="padding:{% if c.image_url %}0 0 16px{% else %}16px{% endif %};overflow:hidden">
  {% if c.image_url %}
  <div style="height:115px;width:100%;overflow:hidden;position:relative;background:#e2e8f0">
    <img src="{{ c.image_url }}" alt="{{ c.name }}" style="width:100%;height:100%;object-fit:cover">
    <div style="position:absolute;inset:0;background:linear-gradient(to top, rgba(15,23,42,0.72) 0%, rgba(15,23,42,0.1) 60%, transparent 100%)"></div>
    <div style="position:absolute;bottom:10px;left:14px;right:14px;display:flex;justify-content:space-between;align-items:flex-end">
      <h2 style="margin:0;color:#fff;font-size:19px;text-shadow:0 1px 4px rgba(0,0,0,0.8)">{{ c.name }}</h2>
      {% if c.today %}<span class="badge done" style="box-shadow:0 2px 6px rgba(0,0,0,0.4)">Today marked</span>{% else %}<span class="badge todo" style="box-shadow:0 2px 6px rgba(0,0,0,0.4)">Today not marked</span>{% endif %}
    </div>
  </div>
  {% else %}
  <div style="display:flex;justify-content:space-between;align-items:center;gap:8px">
    <h2 style="margin:0">{{ c.name }}</h2>
    {% if c.today %}<span class="badge done">Today marked</span>{% else %}<span class="badge todo">Today not marked</span>{% endif %}
  </div>
  {% endif %}
  <div style="{% if c.image_url %}padding:12px 16px 0{% endif %}">
    <div class="muted" style="margin-top:2px">{{ c.n_students }} students · {{ c.held }} class days recorded{% if c.avg is not none %} · average {{ (c.avg*100)|round|int }}%{% endif %}</div>
    {% if c.today %}
    <div class="stats">
      <div class="stat s-p"><b>{{ c.today.p }}</b><span>Present</span></div>
      <div class="stat s-x"><b>{{ c.today.x }}</b><span>Absent</span></div>
      <div class="stat s-l"><b>{{ c.today.l }}</b><span>Late</span></div>
      <div class="stat s-e"><b>{{ c.today.e }}</b><span>Excused</span></div>
      <div class="stat s-r"><b>{{ c.today.r }}</b><span>Recited</span></div>
    </div>
    {% if c.absent_today %}<div>Absent today: {% for n in c.absent_today %}<span class="chip">{{ n }}</span>{% endfor %}</div>{% endif %}
    <p style="margin:10px 0 0"><a class="btn small" href="{{ url_for('mark', subject=c.name, date=today_iso) }}">Edit today</a></p>
    {% else %}
    <p style="margin:14px 0 4px"><a class="btn primary" href="{{ url_for('mark', subject=c.name) }}">Mark attendance now</a></p>
    {% endif %}
    {% if c.watch %}
    <details><summary>Students below {{ (low*100)|int }}% ({{ c.watch|length }})</summary>
      <table style="margin-top:6px">{% for s in c.watch %}<tr><td>{{ s.name }}</td><td class="n">{{ s.x }} absent</td><td class="n"><span class="pill low">{{ (s.rate*100)|round|int }}%</span></td></tr>{% endfor %}</table>
    </details>
    {% endif %}
  </div>
</div>
{% endfor %}
</div>
{% endblock %}"""

MARK = r"""{% extends "base.html" %}
{% block title %}Mark attendance{% endblock %}
{% block body %}
{% if not subject %}
<div class="card">No subjects yet. Add one under <a href="{{ url_for('students') }}">Students &amp; subjects</a>.</div>
{% elif not students %}
<div class="card">No students in {{ subject }} yet. <a href="{{ url_for('students', subject=subject) }}">Add students</a> first.</div>
{% else %}

<style>
/* Mark Page Mobile-First Styles */
.mark-card {
  background: #fff;
  border: 1px solid var(--line);
  border-radius: var(--radius);
  padding: 14px 16px;
  margin-bottom: 12px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.03);
}
.date-header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
}
.date-nav-group {
  display: flex;
  align-items: center;
  gap: 6px;
}
.date-arrow-btn {
  width: 40px;
  height: 40px;
  padding: 0;
  font-size: 20px;
  font-weight: 700;
  border-radius: 10px;
}
.date-input-wrap input[type=date] {
  padding: 8px 10px;
  font-size: 14px;
  font-weight: 600;
  border: 1.5px solid var(--line);
  border-radius: 10px;
  background: #fff;
}
.today-chip {
  padding: 7px 12px;
  font-size: 13px;
  border-radius: 9999px;
  font-weight: 700;
}
.date-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.date-title-text {
  font-weight: 700;
  font-size: 15px;
}
.topic-container {
  margin-top: 10px;
}
.topic-field {
  width: 100%;
  padding: 9px 12px;
  border: 1px solid var(--line);
  border-radius: 9px;
  font-size: 14px;
}

/* View Mode Segmented Bar */
.mode-switch-wrap {
  margin-bottom: 12px;
}
.mode-segmented {
  display: flex;
  background: #e2e8f0;
  border-radius: 12px;
  padding: 3px;
  gap: 4px;
}
.mode-btn {
  flex: 1;
  border: none;
  background: transparent;
  padding: 10px 14px;
  border-radius: 9px;
  font-size: 14px;
  font-weight: 700;
  color: var(--muted);
  cursor: pointer;
  touch-action: manipulation;
  transition: all 0.15s ease;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
}
.mode-btn.on {
  background: #fff;
  color: var(--ink);
  box-shadow: 0 2px 6px rgba(0,0,0,0.08);
}

/* List View Toolbar */
.list-toolbar {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  align-items: center;
  margin-bottom: 10px;
}
.search-wrapper {
  position: relative;
  flex: 1;
  min-width: 180px;
}
.search-wrapper input {
  width: 100%;
  padding: 10px 34px 10px 12px;
  border: 1.5px solid var(--line);
  border-radius: 10px;
  font-size: 14px;
  background: #fff;
  outline: none;
}
.search-wrapper input:focus {
  border-color: var(--brand);
}
.search-clear-btn {
  position: absolute;
  right: 9px;
  top: 50%;
  transform: translateY(-50%);
  background: #e2e8f0;
  border: none;
  width: 20px;
  height: 20px;
  border-radius: 50%;
  font-size: 11px;
  color: #475467;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
}
.fast-actions-wrap {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}
.fast-btn {
  padding: 8px 12px;
  font-size: 13px;
  border-radius: 9px;
}
.fast-btn.pres {
  background: #ecfdf5;
  color: #065f46;
  border-color: #a7f3d0;
}
.fast-btn.pres:hover {
  background: #d1fae5;
}

/* Filter Pills Bar */
.filter-pills-bar {
  display: flex;
  gap: 6px;
  overflow-x: auto;
  white-space: nowrap;
  padding: 2px 2px 10px;
  margin-bottom: 8px;
  -webkit-overflow-scrolling: touch;
  scrollbar-width: none;
}
.filter-pills-bar::-webkit-scrollbar { display: none; }
.fpill {
  flex-shrink: 0;
  border: 1.5px solid var(--line);
  background: #fff;
  border-radius: 9999px;
  padding: 6px 12px;
  font-size: 13px;
  font-weight: 600;
  color: var(--muted);
  cursor: pointer;
  touch-action: manipulation;
  transition: all 0.12s ease;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.fpill-count {
  font-size: 11px;
  font-weight: 700;
  padding: 1px 7px;
  border-radius: 9999px;
  background: #f1f5f9;
  color: var(--muted);
}
.fpill.on {
  border-color: var(--ink);
  background: var(--ink);
  color: #fff;
}
.fpill.on .fpill-count {
  background: rgba(255,255,255,0.22);
  color: #fff;
}
.fpill.on.p { background: #10b981; border-color: #10b981; }
.fpill.on.x { background: #ef4444; border-color: #ef4444; }
.fpill.on.l { background: #f59e0b; border-color: #f59e0b; }
.fpill.on.e { background: #3b82f6; border-color: #3b82f6; }
.fpill.on.r { background: #7c3aed; border-color: #7c3aed; }

/* Student Cards in List View */
.students-list-wrap {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.student-card {
  background: #fff;
  border: 1px solid var(--line);
  border-radius: 12px;
  padding: 10px 12px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.03);
  transition: all 0.12s ease;
}
.student-card-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}
.student-id-name {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  flex: 1;
}
.student-num-badge {
  font-size: 12px;
  font-weight: 700;
  color: var(--muted);
  background: #f1f5f9;
  padding: 2px 7px;
  border-radius: 6px;
  flex-shrink: 0;
}
.student-name-text {
  font-size: 15px;
  font-weight: 700;
  color: var(--ink);
  line-height: 1.25;
  word-break: break-word;
}
.student-status-chip {
  font-size: 11px;
  font-weight: 700;
  padding: 3px 8px;
  border-radius: 9999px;
  flex-shrink: 0;
  text-transform: uppercase;
  letter-spacing: 0.03em;
}
.student-status-chip.p { background: var(--pbg); color: var(--p); }
.student-status-chip.x { background: var(--xbg); color: var(--x); }
.student-status-chip.l { background: var(--lbg); color: var(--l); }
.student-status-chip.e { background: var(--ebg); color: var(--e); }
.student-status-chip.r { background: var(--rbg); color: var(--r); }
.student-status-chip.blank { background: #f1f5f9; color: var(--muted); }

/* 5 Equal Thumb Buttons */
.thumb-buttons-grid {
  display: grid;
  grid-template-columns: repeat(5, 1fr);
  gap: 6px;
}
.cb {
  height: 46px;
  border-radius: 10px;
  border: 1.5px solid var(--line);
  background: #fff;
  font: inherit;
  font-weight: 800;
  font-size: 16px;
  color: var(--muted);
  cursor: pointer;
  touch-action: manipulation;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  user-select: none;
  transition: all 0.12s ease;
}
.cb small {
  font-size: 9px;
  font-weight: 600;
  letter-spacing: 0.02em;
  opacity: 0.85;
  margin-top: 1px;
}
.cb:active {
  transform: scale(0.93);
}
.cb.p.on { background: #10b981; border-color: #10b981; color: #fff; box-shadow: 0 2px 6px rgba(16,185,129,0.3); }
.cb.x.on { background: #ef4444; border-color: #ef4444; color: #fff; box-shadow: 0 2px 6px rgba(239,68,68,0.3); }
.cb.l.on { background: #f59e0b; border-color: #f59e0b; color: #fff; box-shadow: 0 2px 6px rgba(245,158,11,0.3); }
.cb.e.on { background: #3b82f6; border-color: #3b82f6; color: #fff; box-shadow: 0 2px 6px rgba(59,130,246,0.3); }
.cb.r.on { background: #7c3aed; border-color: #7c3aed; color: #fff; box-shadow: 0 2px 6px rgba(124,58,237,0.3); }

/* Roll-Call Flashcard View */
.rc-progress-card {
  padding: 12px 16px;
  margin-bottom: 12px;
}
.rc-progress-meta {
  display: flex;
  justify-content: space-between;
  font-size: 13px;
  margin-bottom: 6px;
}
.rc-progress-track {
  height: 8px;
  background: #e2e8f0;
  border-radius: 9999px;
  overflow: hidden;
}
.rc-progress-bar {
  height: 100%;
  background: var(--brand);
  border-radius: 9999px;
  transition: width 0.25s ease;
}

.rc-flashcard {
  text-align: center;
  padding: 24px 16px;
  border-radius: 16px;
  box-shadow: 0 4px 16px rgba(0,0,0,0.06);
}
.rc-flashcard-index {
  font-size: 14px;
  font-weight: 700;
  color: var(--muted);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.rc-flashcard-name {
  font-size: 24px;
  font-weight: 800;
  color: var(--ink);
  margin: 10px 0 14px;
  word-break: break-word;
  line-height: 1.25;
}
.rc-current-badge-slot {
  margin-bottom: 22px;
}
.rc-current-pill {
  display: inline-block;
  padding: 5px 14px;
  border-radius: 9999px;
  font-weight: 700;
  font-size: 13px;
  background: #f1f5f9;
  color: var(--muted);
}
.rc-current-pill.p { background: var(--pbg); color: var(--p); }
.rc-current-pill.x { background: var(--xbg); color: var(--x); }
.rc-current-pill.l { background: var(--lbg); color: var(--l); }
.rc-current-pill.e { background: var(--ebg); color: var(--e); }
.rc-current-pill.r { background: var(--rbg); color: var(--r); }

.rc-buttons-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 10px;
  margin-bottom: 20px;
  max-width: 480px;
  margin-left: auto;
  margin-right: auto;
}
.rc-big-btn {
  height: 58px;
  border-radius: 12px;
  border: 2px solid var(--line);
  background: #fff;
  cursor: pointer;
  touch-action: manipulation;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  transition: all 0.12s ease;
  user-select: none;
}
.rc-big-btn:active {
  transform: scale(0.96);
}
.rc-big-btn .rc-code {
  font-size: 18px;
  font-weight: 800;
  line-height: 1.1;
}
.rc-big-btn .rc-label {
  font-size: 11px;
  font-weight: 600;
  opacity: 0.85;
}
.rc-big-btn.p { border-color: #a7f3d0; color: #065f46; background: #ecfdf5; }
.rc-big-btn.p:active { background: #10b981; color: #fff; border-color: #10b981; }
.rc-big-btn.x { border-color: #fecaca; color: #991b1b; background: #fef2f2; }
.rc-big-btn.x:active { background: #ef4444; color: #fff; border-color: #ef4444; }
.rc-big-btn.l { border-color: #fde68a; color: #92400e; background: #fffbeb; }
.rc-big-btn.l:active { background: #f59e0b; color: #fff; border-color: #f59e0b; }
.rc-big-btn.e { border-color: #bfdbfe; color: #1e40af; background: #eff6ff; }
.rc-big-btn.e:active { background: #3b82f6; color: #fff; border-color: #3b82f6; }
.rc-big-btn.r { border-color: #ddd6fe; color: #5b21b6; background: #f5f3ff; grid-column: span 2; }
.rc-big-btn.r:active { background: #7c3aed; color: #fff; border-color: #7c3aed; }

.rc-nav-row {
  display: flex;
  justify-content: center;
  gap: 10px;
  margin-top: 6px;
}

/* Roll-Call Done Card */
.rc-done-card {
  text-align: center;
  padding: 32px 16px;
  border-radius: 16px;
}
.done-stats-summary {
  display: flex;
  gap: 6px;
  justify-content: center;
  flex-wrap: wrap;
  margin: 14px 0 20px;
}

/* Floating Bottom Dock */
.mobile-dock {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(255,255,255,0.96);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  border-top: 1px solid var(--line);
  padding: 10px 16px;
  padding-bottom: max(10px, env(safe-area-inset-bottom, 0px));
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  z-index: 40;
  box-shadow: 0 -4px 16px rgba(0,0,0,0.06);
}
.dock-counts {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
  align-items: center;
}
.dcount {
  padding: 3px 8px;
  border-radius: 9999px;
  font-size: 13px;
  font-weight: 700;
}
.save-btn {
  height: 46px;
  padding: 0 18px;
  border-radius: 12px;
  font-size: 15px;
  font-weight: 700;
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  box-shadow: 0 2px 8px rgba(37,99,235,0.3);
}
.save-status-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #cbd5e1;
  display: inline-block;
}
.save-status-dot.dirty {
  background: #f59e0b;
  box-shadow: 0 0 6px #f59e0b;
}

.toast {
  position: fixed;
  left: 50%;
  transform: translateX(-50%);
  bottom: calc(72px + env(safe-area-inset-bottom, 0px));
  background: #0f172a;
  color: #fff;
  padding: 11px 20px;
  border-radius: 12px;
  font-weight: 600;
  font-size: 14px;
  z-index: 60;
  display: none;
  box-shadow: 0 6px 20px rgba(0,0,0,0.25);
  white-space: nowrap;
  max-width: 90vw;
}
.toast.err { background: #dc2626; }
.toast.ok { background: #059669; }
</style>

<!-- Date & Class Header Card -->
<div class="mark-card">
  <div class="date-header-row">
    <div class="date-nav-group">
      {% if date_iso %}<a class="btn date-arrow-btn" href="{{ prev_url }}" title="Previous day" aria-label="Previous day">‹</a>{% endif %}
      <div class="date-input-wrap">
        <input type="date" id="dateIn" value="{{ date_iso }}">
      </div>
      {% if date_iso %}<a class="btn date-arrow-btn" href="{{ next_url }}" title="Next day" aria-label="Next day">›</a>{% endif %}
      {% if today_url %}<a class="btn small today-chip" href="{{ today_url }}">Today</a>{% endif %}
    </div>
    <div class="date-meta">
      {% if subject_img_url %}
      <img src="{{ subject_img_url }}" alt="{{ subject }}" style="width:36px;height:36px;border-radius:9px;object-fit:cover;border:1.5px solid var(--line);box-shadow:0 1px 4px rgba(0,0,0,0.08)">
      {% endif %}
      <span class="date-title-text">{{ date_label }}</span>
      <span class="date-badge-slot">
        {% if recorded %}<span class="badge done">✓ Saved in Excel</span>{% else %}<span class="badge todo">⚪ Not saved yet</span>{% endif %}
      </span>
    </div>
  </div>
  {% if date_iso %}
  <div class="topic-container">
    <input type="text" id="topic" class="topic-field" placeholder="Topic for this lesson (optional)" value="{{ topic }}" maxlength="120">
  </div>
  {% endif %}
</div>

{% if not date_iso %}
<div class="card" style="text-align:center;padding:28px 16px">
  <div style="font-size:32px;margin-bottom:8px">📅</div>
  <p>Pick a date above, or tap <b>Today</b>, to start marking attendance for <b>{{ subject }}</b>.</p>
</div>
<script>
document.getElementById('dateIn').onchange = e => {
  if (e.target.value) location.href = {{ base_url|tojson }} + '&date=' + e.target.value;
};
</script>
{% else %}

<!-- View Switcher (List vs Roll-Call) -->
<div class="mode-switch-wrap">
  <div class="mode-segmented">
    <button type="button" id="btnModeList" class="mode-btn on">☰ List View</button>
    <button type="button" id="btnModeRoll" class="mode-btn">🎯 Roll-Call Mode</button>
  </div>
</div>

<!-- ================= LIST VIEW ================= -->
<div id="listViewArea">
  <!-- Search & Fast Actions -->
  <div class="list-toolbar">
    <div class="search-wrapper">
      <input type="text" id="search" placeholder="Search student name..." autocomplete="off">
      <button type="button" id="clearSearch" class="search-clear-btn" style="display:none">✕</button>
    </div>
    <div class="fast-actions-wrap">
      <button class="btn fast-btn pres" type="button" id="allP">⚡ All Present</button>
      <button class="btn fast-btn" type="button" id="clearAll">↺ Reset</button>
      <a class="btn fast-btn" href="{{ url_for('scan', subject=subject) }}">📥 Import</a>
    </div>
  </div>

  <!-- Filter Pills Bar -->
  <div class="filter-pills-bar" id="filterPills">
    <button type="button" class="fpill on" data-filter="all">All <span class="fpill-count" id="fcount-all">0</span></button>
    <button type="button" class="fpill" data-filter="unmarked">Unmarked <span class="fpill-count" id="fcount-unmarked">0</span></button>
    <button type="button" class="fpill p" data-filter="p">Present <span class="fpill-count" id="fcount-p">0</span></button>
    <button type="button" class="fpill x" data-filter="x">Absent <span class="fpill-count" id="fcount-x">0</span></button>
    <button type="button" class="fpill l" data-filter="l">Late <span class="fpill-count" id="fcount-l">0</span></button>
    <button type="button" class="fpill e" data-filter="e">Excused <span class="fpill-count" id="fcount-e">0</span></button>
    <button type="button" class="fpill r" data-filter="r">Recited <span class="fpill-count" id="fcount-r">0</span></button>
  </div>

  <!-- Student Cards List -->
  <div class="students-list-wrap" id="studentsList"></div>
  <div id="emptyFilterMsg" class="card" style="display:none;text-align:center;padding:24px;color:var(--muted)">No students match this filter.</div>
</div>

<!-- ================= ROLL-CALL FLASHCARD VIEW ================= -->
<div id="rollCallArea" style="display:none">
  <div class="card rc-progress-card">
    <div class="rc-progress-meta">
      <span id="rollCounterText" style="font-weight:700">Student 1 of 28</span>
      <span id="rollPercentText" class="muted">0%</span>
    </div>
    <div class="rc-progress-track">
      <div class="rc-progress-bar" id="rollProgressBar" style="width:0%"></div>
    </div>
  </div>

  <div class="card rc-flashcard" id="rollCardMain">
    <div class="rc-flashcard-index" id="rcStudentIndex">Student #1</div>
    <div class="rc-flashcard-name" id="rcStudentName">Student Name</div>
    <div class="rc-current-badge-slot">
      <span class="rc-current-pill" id="rcCurrentPill">Currently: Present</span>
    </div>

    <!-- Large Thumb Buttons with Auto-Advance -->
    <div class="rc-buttons-grid">
      <button type="button" class="rc-big-btn p" data-code="p">
        <span class="rc-code">✓ P</span>
        <span class="rc-label">Present</span>
      </button>
      <button type="button" class="rc-big-btn x" data-code="x">
        <span class="rc-code">✗ A</span>
        <span class="rc-label">Absent</span>
      </button>
      <button type="button" class="rc-big-btn l" data-code="l">
        <span class="rc-code">⏱ L</span>
        <span class="rc-label">Late</span>
      </button>
      <button type="button" class="rc-big-btn e" data-code="e">
        <span class="rc-code">✉ E</span>
        <span class="rc-label">Excused</span>
      </button>
      <button type="button" class="rc-big-btn r" data-code="r">
        <span class="rc-code">★ R</span>
        <span class="rc-label">Recited</span>
      </button>
    </div>

    <div class="rc-nav-row">
      <button type="button" class="btn" id="rcBtnPrev">‹ Previous</button>
      <button type="button" class="btn" id="rcBtnSkip">Skip ›</button>
      <button type="button" class="btn" id="rcBtnSwitchList">Switch to List</button>
    </div>
  </div>

  <!-- Roll Call Finished -->
  <div class="card rc-done-card" id="rollCardDone" style="display:none">
    <div style="font-size:36px;margin-bottom:8px">🎉</div>
    <h2 style="font-size:22px;margin:4px 0">Roll-Call Complete!</h2>
    <p class="muted" style="margin-bottom:12px">All students have been reviewed for this date.</p>
    <div class="done-stats-summary" id="doneStatsSummary"></div>
    <div style="display:flex;gap:10px;justify-content:center;flex-wrap:wrap;margin-top:20px">
      <button type="button" class="btn primary" id="doneSaveBtn" style="padding:12px 24px;font-size:16px">💾 Save to Excel</button>
      <button type="button" class="btn" id="doneReviewBtn">Review List</button>
    </div>
  </div>
</div>

<!-- ================= FLOATING MOBILE ACTION DOCK ================= -->
<div class="mobile-dock" id="mobileDock">
  <div class="dock-counts" id="dockCounts">
    <span class="dcount s-p" id="cp">P 0</span>
    <span class="dcount s-x" id="cx">A 0</span>
    <span class="dcount s-l" id="cl">L 0</span>
    <span class="dcount s-e" id="ce">E 0</span>
    <span class="dcount s-r" id="cr">R 0</span>
  </div>
  <button class="btn primary save-btn" id="save" type="button">
    <span class="save-status-dot" id="saveDot"></span>
    <span id="saveBtnText">Save to Excel</span>
  </button>
</div>

<!-- Floating Toast -->
<div class="toast" id="toast"></div>

<script>
const students = {{ students|tojson }};
const subject = {{ subject|tojson }};
const dateIso = {{ date_iso|tojson }};
let wasRecorded = {{ recorded|tojson }};
const baseUrl = {{ base_url|tojson }};
const saveUrl = {{ save_url|tojson }};

let dirty = false;
let curRollIndex = 0;
let activeFilter = 'all';
let searchQuery = '';

const codes = ['p', 'x', 'l', 'e', 'r'];
const codeNames = {
  p: 'Present',
  x: 'Absent',
  l: 'Late',
  e: 'Excused',
  r: 'Recited'
};
const codeLetters = {
  p: 'P',
  x: 'A',
  l: 'L',
  e: 'E',
  r: 'R'
};

function vibrate(ms) {
  try {
    if (window.navigator && window.navigator.vibrate) {
      window.navigator.vibrate(ms || 12);
    }
  } catch (e) {}
}

const listEl = document.getElementById('studentsList');
const searchEl = document.getElementById('search');
const clearSearchBtn = document.getElementById('clearSearch');
const emptyFilterMsg = document.getElementById('emptyFilterMsg');
const toastEl = document.getElementById('toast');
const saveBtn = document.getElementById('save');
const saveDot = document.getElementById('saveDot');
const saveBtnText = document.getElementById('saveBtnText');
const topicEl = document.getElementById('topic');

const btnModeList = document.getElementById('btnModeList');
const btnModeRoll = document.getElementById('btnModeRoll');
const listViewArea = document.getElementById('listViewArea');
const rollCallArea = document.getElementById('rollCallArea');

const rcStudentIndex = document.getElementById('rcStudentIndex');
const rcStudentName = document.getElementById('rcStudentName');
const rcCurrentPill = document.getElementById('rcCurrentPill');
const rollProgressBar = document.getElementById('rollProgressBar');
const rollCounterText = document.getElementById('rollCounterText');
const rollPercentText = document.getElementById('rollPercentText');
const rollCardMain = document.getElementById('rollCardMain');
const rollCardDone = document.getElementById('rollCardDone');
const doneStatsSummary = document.getElementById('doneStatsSummary');

const studentRowEls = [];

students.forEach((s, idx) => {
  if (!s.code) s.code = 'p';

  const card = document.createElement('div');
  card.className = 'student-card';
  card.dataset.name = s.name.toLowerCase();
  card.dataset.index = idx;

  const header = document.createElement('div');
  header.className = 'student-card-head';

  const idName = document.createElement('div');
  idName.className = 'student-id-name';

  const numSpan = document.createElement('span');
  numSpan.className = 'student-num-badge';
  numSpan.textContent = '#' + (idx + 1);

  const nameSpan = document.createElement('span');
  nameSpan.className = 'student-name-text';
  nameSpan.textContent = s.name;

  idName.appendChild(numSpan);
  idName.appendChild(nameSpan);

  const badge = document.createElement('span');
  badge.className = 'student-status-chip';
  badge.textContent = codeNames[s.code] || 'Unmarked';
  if (s.code) badge.classList.add(s.code);
  else badge.classList.add('blank');

  header.appendChild(idName);
  header.appendChild(badge);

  const grid = document.createElement('div');
  grid.className = 'thumb-buttons-grid';

  const buttonMap = {};
  codes.forEach(c => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'cb ' + c;
    btn.dataset.code = c;

    const strong = document.createElement('span');
    strong.textContent = codeLetters[c];
    const sm = document.createElement('small');
    sm.textContent = codeNames[c];

    btn.appendChild(strong);
    btn.appendChild(sm);

    btn.onclick = (e) => {
      e.stopPropagation();
      vibrate(14);
      s.code = c;
      dirty = true;
      paint();
    };

    grid.appendChild(btn);
    buttonMap[c] = btn;
  });

  card.appendChild(header);
  card.appendChild(grid);
  listEl.appendChild(card);

  studentRowEls.push({
    card,
    badge,
    buttons: buttonMap,
    student: s
  });
});

function paint() {
  const counts = { p: 0, x: 0, l: 0, e: 0, r: 0, unmarked: 0 };

  studentRowEls.forEach(item => {
    const code = item.student.code;
    if (code && counts.hasOwnProperty(code)) {
      counts[code]++;
    } else {
      counts.unmarked++;
    }

    codes.forEach(c => {
      item.buttons[c].classList.toggle('on', c === code);
    });

    item.badge.className = 'student-status-chip ' + (code || 'blank');
    item.badge.textContent = codeNames[code] || 'Unmarked';

    const matchesSearch = !searchQuery || item.student.name.toLowerCase().includes(searchQuery);
    let matchesFilter = true;
    if (activeFilter === 'unmarked') {
      matchesFilter = !code;
    } else if (activeFilter !== 'all') {
      matchesFilter = (code === activeFilter);
    }

    const visible = matchesSearch && matchesFilter;
    item.card.style.display = visible ? '' : 'none';
  });

  const visibleCount = studentRowEls.filter(i => i.card.style.display !== 'none').length;
  emptyFilterMsg.style.display = (visibleCount === 0) ? 'block' : 'none';

  const total = students.length;
  document.getElementById('fcount-all').textContent = total;
  document.getElementById('fcount-unmarked').textContent = counts.unmarked;
  document.getElementById('fcount-p').textContent = counts.p;
  document.getElementById('fcount-x').textContent = counts.x;
  document.getElementById('fcount-l').textContent = counts.l;
  document.getElementById('fcount-e').textContent = counts.e;
  document.getElementById('fcount-r').textContent = counts.r;

  document.getElementById('cp').textContent = 'P ' + counts.p;
  document.getElementById('cx').textContent = 'A ' + counts.x;
  document.getElementById('cl').textContent = 'L ' + counts.l;
  document.getElementById('ce').textContent = 'E ' + counts.e;
  document.getElementById('cr').textContent = 'R ' + counts.r;

  if (saveDot) saveDot.classList.toggle('dirty', dirty);
  if (saveBtnText) saveBtnText.textContent = dirty ? 'Save to Excel *' : 'Save to Excel';

  if (rollCallArea.style.display !== 'none') {
    renderRollCall();
  }
}

function setViewMode(mode) {
  if (mode === 'roll') {
    listViewArea.style.display = 'none';
    rollCallArea.style.display = 'block';
    btnModeRoll.classList.add('on');
    btnModeList.classList.remove('on');
    renderRollCall();
  } else {
    listViewArea.style.display = 'block';
    rollCallArea.style.display = 'none';
    btnModeList.classList.add('on');
    btnModeRoll.classList.remove('on');
  }
}

btnModeList.onclick = () => setViewMode('list');
btnModeRoll.onclick = () => setViewMode('roll');

function renderRollCall() {
  const total = students.length;
  if (curRollIndex >= total) {
    rollCardMain.style.display = 'none';
    rollCardDone.style.display = 'block';
    rollProgressBar.style.width = '100%';
    rollCounterText.textContent = 'All ' + total + ' Students Checked';
    rollPercentText.textContent = '100%';

    const counts = { p: 0, x: 0, l: 0, e: 0, r: 0 };
    students.forEach(s => { if (s.code) counts[s.code]++; });
    doneStatsSummary.innerHTML =
      '<span class="dcount s-p">P ' + counts.p + '</span>' +
      '<span class="dcount s-x">A ' + counts.x + '</span>' +
      '<span class="dcount s-l">L ' + counts.l + '</span>' +
      '<span class="dcount s-e">E ' + counts.e + '</span>' +
      '<span class="dcount s-r">R ' + counts.r + '</span>';
    return;
  }

  rollCardMain.style.display = 'block';
  rollCardDone.style.display = 'none';

  const s = students[curRollIndex];
  rcStudentIndex.textContent = 'Student #' + (curRollIndex + 1) + ' of ' + total;
  rcStudentName.textContent = s.name;

  const currentCode = s.code;
  rcCurrentPill.textContent = currentCode ? ('Marked: ' + codeNames[currentCode]) : 'Not marked yet';
  rcCurrentPill.className = 'rc-current-pill ' + (currentCode || 'blank');

  const pct = Math.round((curRollIndex / total) * 100);
  rollProgressBar.style.width = pct + '%';
  rollCounterText.textContent = 'Student ' + (curRollIndex + 1) + ' of ' + total;
  rollPercentText.textContent = pct + '%';
}

function handleRollCallSelect(code) {
  vibrate(16);
  students[curRollIndex].code = code;
  dirty = true;
  curRollIndex++;
  paint();
  renderRollCall();
}

document.querySelectorAll('.rc-big-btn').forEach(btn => {
  btn.onclick = () => handleRollCallSelect(btn.dataset.code);
});

document.getElementById('rcBtnPrev').onclick = () => {
  if (curRollIndex > 0) {
    curRollIndex--;
    renderRollCall();
  }
};

document.getElementById('rcBtnSkip').onclick = () => {
  if (curRollIndex < students.length) {
    curRollIndex++;
    renderRollCall();
  }
};

document.getElementById('rcBtnSwitchList').onclick = () => setViewMode('list');
document.getElementById('doneReviewBtn').onclick = () => {
  curRollIndex = 0;
  setViewMode('list');
};
document.getElementById('doneSaveBtn').onclick = () => saveAttendance();

document.querySelectorAll('.fpill').forEach(pill => {
  pill.onclick = () => {
    vibrate(10);
    document.querySelectorAll('.fpill').forEach(p => p.classList.remove('on'));
    pill.classList.add('on');
    activeFilter = pill.dataset.filter;
    paint();
  };
});

searchEl.oninput = (e) => {
  searchQuery = e.target.value.toLowerCase().trim();
  clearSearchBtn.style.display = searchQuery ? 'flex' : 'none';
  paint();
};

clearSearchBtn.onclick = () => {
  searchEl.value = '';
  searchQuery = '';
  clearSearchBtn.style.display = 'none';
  searchEl.focus();
  paint();
};

document.getElementById('allP').onclick = () => {
  vibrate(20);
  students.forEach(s => s.code = 'p');
  dirty = true;
  paint();
  toast('All marked Present (P)', 'ok');
};

document.getElementById('clearAll').onclick = () => {
  if (confirm('Clear attendance for all students on this date?')) {
    vibrate(15);
    students.forEach(s => s.code = '');
    dirty = true;
    paint();
    toast('Attendance cleared', 'err');
  }
};

document.getElementById('dateIn').onchange = e => {
  if (e.target.value) location.href = baseUrl + '&date=' + e.target.value;
};
if (topicEl) {
  topicEl.oninput = () => { dirty = true; if (saveDot) saveDot.classList.add('dirty'); };
}

window.onbeforeunload = () => dirty ? 'You have unsaved changes.' : undefined;

function toast(msg, type) {
  toastEl.textContent = msg;
  toastEl.className = 'toast ' + (type === 'err' ? 'err' : 'ok');
  toastEl.style.display = 'block';
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => {
    toastEl.style.display = 'none';
  }, type === 'err' ? 5000 : 2400);
}

async function saveAttendance() {
  const blank = students.filter(s => !s.code).length;
  if (blank === students.length && !wasRecorded) {
    toast('Nobody is marked yet. Mark at least one student first.', 'err');
    return;
  }
  if (blank && !confirm(blank + (blank === 1 ? ' student is' : ' students are') + ' not marked and will be left blank. Save anyway?')) {
    return;
  }

  saveBtn.disabled = true;
  if (saveBtnText) saveBtnText.textContent = 'Saving...';

  try {
    const payload = {
      subject,
      date: dateIso,
      topic: topicEl ? topicEl.value : '',
      marks: students.map(s => ({
        row: s.row,
        name: s.name,
        code: s.code,
        clear: !s.code
      }))
    };

    const res = await fetch(saveUrl, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (data.ok) {
      dirty = false;
      wasRecorded = true;
      vibrate(25);
      toast('Saved to Excel ✓', 'ok');
      const badgeSlot = document.querySelector('.date-badge-slot');
      if (badgeSlot) {
        badgeSlot.innerHTML = '<span class="badge done">✓ Saved in Excel</span>';
      }
    } else {
      toast(data.error || 'Could not save.', 'err');
    }
  } catch (err) {
    toast('Could not reach the site. Is the server window running?', 'err');
  } finally {
    saveBtn.disabled = false;
    paint();
  }
}
saveBtn.onclick = saveAttendance;

window.addEventListener('keydown', (e) => {
  if (['INPUT', 'TEXTAREA'].includes(document.activeElement.tagName)) return;
  const key = e.key.toLowerCase();
  if ((e.ctrlKey || e.metaKey) && key === 's') {
    e.preventDefault();
    saveAttendance();
    return;
  }
  if (rollCallArea.style.display !== 'none') {
    if (codes.includes(key)) {
      handleRollCallSelect(key);
    } else if (key === 'arrowleft') {
      document.getElementById('rcBtnPrev').click();
    } else if (key === 'arrowright') {
      document.getElementById('rcBtnSkip').click();
    }
  }
});

paint();
</script>
{% endif %}
{% endif %}
{% endblock %}"""

RECORDS = r"""{% extends "base.html" %}
{% block title %}Records{% endblock %}
{% block body %}
<h1>Records</h1>
<style>
.recgrid .sticky { box-shadow: 2px 0 4px rgba(15, 23, 42, .08); }
@media (max-width: 640px) {
  .scroll { max-height: 78vh; -webkit-overflow-scrolling: touch; }
  .recgrid th, .recgrid td { padding: 6px 7px; font-size: 13px; }
  .recgrid .sticky { white-space: normal; width: 108px; min-width: 108px; max-width: 108px; font-size: 12px; line-height: 1.2; padding: 6px 7px; }
  .recgrid small { max-width: 62px; font-size: 10px; }
  .recgrid .pill { min-width: 38px; padding: 2px 6px; }
}
</style>
{% if not subject %}<div class="card">No subjects yet.</div>
{% elif not rows %}<div class="card">No students in {{ subject }} yet.</div>
{% else %}
{% if role == 'teacher' %}<p><a class="btn small" href="{{ url_for('print_sheet', subject=subject) }}" target="_blank">&#128424; Print sheet</a></p>{% endif %}
{% if role == 'teacher' %}<p class="muted">Same view as the Excel sheet. To change a day, use <a href="{{ url_for('mark', subject=subject) }}">Mark attendance</a> and pick that date.</p>
{% else %}<p class="muted">p = present &middot; x = absent &middot; l = late &middot; e = excused &middot; r = recited. Swipe the table sideways to see every day.</p>{% endif %}
<div class="scroll"><table class="grid recgrid">
<thead><tr><th class="sticky">Student</th><th class="n">P</th><th class="n">A</th><th class="n">L</th><th class="n">E</th><th class="n">R</th><th class="n">Rate</th>
{% for d in dates %}<th class="n">{% if role == 'teacher' %}<a href="{{ url_for('mark', subject=subject, date=d.iso) }}" style="color:inherit;text-decoration:none">{{ d.label }}</a>{% else %}{{ d.label }}{% endif %}{% if role == 'teacher' %}<form method="post" action="{{ url_for('dates_delete') }}" style="display:inline" data-msg="Delete {{ d.label }} from {{ subject }}? Every mark for that day will be removed (a backup copy is saved first)." onsubmit="return confirm(this.dataset.msg)"><input type="hidden" name="subject" value="{{ subject }}"><input type="hidden" name="date" value="{{ d.iso }}"><button type="submit" title="Delete this date" style="border:0;background:none;color:#c0392b;cursor:pointer;font-size:12px;padding:0 0 0 4px">&#10005;</button></form>{% endif %}{% if d.topic %}<small title="{{ d.topic }}">{{ d.topic }}</small>{% endif %}</th>{% endfor %}</tr></thead>
<tbody>
{% for s in rows %}<tr><td class="sticky">{{ s.name }}</td><td class="n">{{ s.p }}</td><td class="n">{{ s.x }}</td><td class="n">{{ s.l }}</td><td class="n">{{ s.e }}</td><td class="n">{{ s.r }}</td>
<td class="n">{% if s.rate is none %}<span class="pill none">–</span>{% else %}<span class="pill {{ 'low' if s.rate < low }}">{{ (s.rate*100)|round|int }}%</span>{% endif %}</td>
{% for c in s.codes %}<td class="c {{ c }}">{{ c }}</td>{% endfor %}</tr>{% endfor %}
</tbody></table></div>
{% if not dates %}<p class="muted">No days recorded yet.</p>{% endif %}
{% endif %}
{% endblock %}"""

STUDENTS = r"""{% extends "base.html" %}
{% block title %}Students &amp; subjects{% endblock %}
{% block body %}
<h1>Students &amp; subjects</h1>
{% if subjects %}
<div class="grid2">
<div class="card">
  <h2>Add students</h2>
  <form method="post" action="{{ url_for('students_add') }}">
    <textarea name="names" rows="5" style="width:100%" placeholder="One name per line" required></textarea>
    <p>{% for s in subjects %}<label class="chk"><input type="checkbox" name="subjects" value="{{ s }}" {{ 'checked' if s==subject or not subject }}> {{ s }}</label>{% endfor %}</p>
    <button class="btn primary" type="submit">Add</button>
  </form>
</div>
<div class="card">
  <h2>Add a subject</h2>
  <form method="post" action="{{ url_for('subjects_add') }}">
    <p><input class="txt" type="text" name="name" placeholder="Subject name" maxlength="31" required style="width:100%"></p>
    <p><select name="copy_from" style="width:100%"><option value="">Start with an empty class list</option>
      {% for s in subjects %}<option value="{{ s }}">Copy the students from {{ s }}</option>{% endfor %}</select></p>
    <button class="btn primary" type="submit">Create subject</button>
  </form>
</div>
</div>
{% else %}
<div class="card"><h2>Add your first subject</h2>
  <form method="post" action="{{ url_for('subjects_add') }}">
    <input class="txt" type="text" name="name" placeholder="Subject name" maxlength="31" required>
    <button class="btn primary" type="submit">Create subject</button>
  </form></div>
{% endif %}
{% if subject %}
<div class="card">
  <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;margin-bottom:14px;padding-bottom:12px;border-bottom:1px solid var(--line)">
    <div style="display:flex;align-items:center;gap:12px">
      {% if subject_img_url %}
      <img src="{{ subject_img_url }}" alt="{{ subject }}" style="width:52px;height:52px;border-radius:12px;object-fit:cover;border:1.5px solid var(--line);box-shadow:0 2px 6px rgba(0,0,0,0.08)">
      {% else %}
      <div style="width:52px;height:52px;border-radius:12px;background:var(--ebg);color:var(--brand);display:flex;align-items:center;justify-content:center;font-size:24px;border:1.5px solid var(--line)">📖</div>
      {% endif %}
      <div>
        <h2 style="margin:0;font-size:19px">{{ subject }}</h2>
        <span class="muted" style="font-size:13px">{{ rows|length }} students enrolled</span>
      </div>
    </div>
    <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
      <form class="inline" method="post" action="{{ url_for('subjects_delete') }}" onsubmit="return confirm('⚠️ DELETE {{ subject|e }}?\n\nThis will permanently delete this subject and all its attendance records from Excel. Are you sure?')">
        <input type="hidden" name="subject" value="{{ subject }}">
        <button class="btn small danger" type="submit">🗑 Delete Subject</button>
      </form>
    </div>
  </div>

  <!-- Custom Subject Picture Uploader -->
  <details style="margin-bottom:16px;background:#f8fafc;padding:12px 14px;border-radius:10px;border:1px solid var(--line)">
    <summary style="font-weight:700;cursor:pointer;color:var(--brand);font-size:14px">📷 Customize Picture for {{ subject }}</summary>
    <div style="margin-top:10px;display:flex;align-items:center;gap:10px;flex-wrap:wrap">
      <form method="post" action="{{ url_for('subjects_upload_image') }}" enctype="multipart/form-data" style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
        <input type="hidden" name="subject" value="{{ subject }}">
        <input type="file" name="image" accept="image/*" required style="font-size:13px">
        <button class="btn small primary" type="submit">Upload Picture</button>
      </form>
      {% if subject_img_url %}
      <form class="inline" method="post" action="{{ url_for('subjects_delete_image') }}" onsubmit="return confirm('Remove custom picture for {{ subject|e }}?')">
        <input type="hidden" name="subject" value="{{ subject }}">
        <button class="btn small danger" type="submit">Remove Picture</button>
      </form>
      {% endif %}
    </div>
  </details>
  {% if not rows %}<p class="muted">No students yet.</p>{% endif %}
  <table>{% for s in rows %}<tr>
    <td class="n" style="width:40px">{{ loop.index }}</td><td>{{ s.name }}</td>
    <td class="n" style="width:90px"><span class="pill {{ 'none' if s.rate is none else ('low' if s.rate < low) }}">{{ '–' if s.rate is none else ((s.rate*100)|round|int ~ '%') }}</span></td>
    <td style="text-align:right;white-space:nowrap">
      <form class="inline" method="post" action="{{ url_for('students_remove') }}" onsubmit="return confirm('Remove {{ s.name|e }} from {{ subject|e }}? Their marks for this subject are deleted.')">
        <input type="hidden" name="subject" value="{{ subject }}"><input type="hidden" name="row" value="{{ s.row }}"><input type="hidden" name="name" value="{{ s.name }}">
        <button class="btn small danger" type="submit">Remove</button></form>
      <form class="inline" method="post" action="{{ url_for('students_remove') }}" onsubmit="return confirm('Remove {{ s.name|e }} from ALL subjects? Their marks are deleted everywhere.')">
        <input type="hidden" name="subject" value="{{ subject }}"><input type="hidden" name="name" value="{{ s.name }}"><input type="hidden" name="everywhere" value="1">
        <button class="btn small danger" type="submit">Remove from all</button></form>
    </td></tr>{% endfor %}</table>
</div>
{% endif %}
{% endblock %}"""

SCAN = r"""{% extends "base.html" %}
{% block title %}Import attendance{% endblock %}
{% block body %}
<h1>Import attendance</h1>
{% if not subject %}
<div class="card">Add a subject first under <a href="{{ url_for('students') }}">Students &amp; subjects</a>.</div>
{% elif not students %}
<div class="card">No students in {{ subject }} yet. <a href="{{ url_for('students', subject=subject) }}">Add the class list</a> first so the sheet can be matched to names.</div>
{% else %}
<style>
.seg { display: flex; gap: 8px; margin: 0 0 12px; flex-wrap: wrap; }
.segbtn { padding: 10px 16px; border: 1px solid var(--line); background: #fff; border-radius: 10px; font: inherit; cursor: pointer; }
.segbtn.on { background: var(--brand); border-color: var(--brand); color: #fff; }
</style>
<p class="muted" style="margin-top:0">Where is today's attendance coming from? Pick one, check the result, then save. <b>Nothing is saved until you confirm.</b></p>
<div class="seg">
  <button type="button" class="segbtn" id="segCsv">&#128196; Google Meet CSV file</button>
  <button type="button" class="segbtn" id="segPhoto">&#128247; Photo or screenshot</button>
</div>
<div class="card" id="csvPanel">
  <p class="muted" style="margin-top:0">Upload the attendance <b>CSV</b> exported from your Google Meet extension. No AI key is needed. Present = in the call for at least <b>{{ pct }}%</b> of the meeting, and your recited (R) marks for that day are kept.</p>
  <form method="post" enctype="multipart/form-data" action="{{ url_for('import_meet') }}">
    <input type="hidden" name="subject" value="{{ subject }}">
    <p><input type="file" name="csv" accept=".csv,text/csv" required></p>
    <div class="toolbar">
      <input type="text" name="topic" class="grow" maxlength="120" placeholder="Topic for this day (optional)">
      <label>Date <input type="date" name="date"></label>
    </div>
    <p class="muted">Leave the date empty to use the date of the meeting.</p>
    <button class="btn primary" type="submit">Read the file</button>
  </form>
</div>
<div id="photoPanel">
{% if not has_key %}
<div class="card" id="keyCard">
  <h2>One-time setup</h2>
  <p>Reading photos needs an API key from either service. Paste whichever you have; the site tells them apart automatically.</p>
  <ul style="margin-top:0">
    <li><b>Google Gemini</b> (key starts with <code>AQ.</code> or <code>AIza</code>): create a key in Google AI Studio. It has a free tier, but Google may use content sent on the free tier to improve its products.</li>
    <li><b>Claude</b> (key starts with <code>sk-ant-</code>): create a key in the Claude Console (docs.claude.com explains how). The account needs a little credit.</li>
  </ul>
  <p>The key is saved only on this computer, in <code>api_key.txt</code> next to <code>app.py</code>.</p>
  <p><input class="txt" type="password" id="keyIn" placeholder="AIza… or sk-ant-…" style="width:100%;max-width:420px" autocomplete="off">
  <button class="btn primary" id="keySave" type="button">Save key</button></p>
  <div id="keyMsg" class="muted"></div>
</div>
{% endif %}
<div class="card" id="step1">
  <p class="muted" style="margin-top:0">Choose a photo of a paper list, or screenshots of an online-meeting attendance report (up to {{ max_images }}, for example when the report is long and you scroll). The AI reads the names and suggests who was present or absent for <b>{{ subject }}</b>. People who are not on this class list (other sections, teachers) are ignored. <b>Nothing is saved to Excel until you confirm.</b> The images, including the names on them, are sent to {{ 'Google' if provider == 'gemini' else 'Anthropic' if provider else 'the AI service you set up' }} to be read.{% if provider == 'gemini' %} On Google's free tier, Google may use it to improve its products; a paid Gemini account does not.{% endif %}</p>
  <input type="file" id="file" accept="image/*" multiple>
  <div id="previews" style="display:flex;gap:8px;flex-wrap:wrap;margin-top:10px"></div>
  <p><button class="btn primary" id="read" type="button" disabled>Read the sheet</button> <span id="busy" class="muted"></span></p>
  <div id="err" class="flash err" style="display:none"></div>
</div>

<div id="review" style="display:none">
  <div class="card">
    <h2>Check and confirm</h2>
    <div class="toolbar">
      <label>Date <input type="date" id="date"></label>
      <input type="text" id="topic" class="grow" placeholder="Topic for this day (optional)" maxlength="120">
    </div>
    <div id="dateNote" class="muted"></div>
    <div class="toolbar" style="margin-top:10px">
      <label>How should I read the sheet?
        <select id="mode" class="slim">
          <option value="list">Names on the sheet were present. Anyone missing is absent.</option>
          <option value="marks">Whole class is listed. A signature or tick means present.</option>
          <option value="percent">Online meeting report. Present if attended enough of the session.</option>
        </select></label>
      <span id="thrWrap" style="display:none">at least <input type="number" id="thr" value="75" min="1" max="100" style="width:70px;font:inherit;padding:8px;border:1px solid var(--line);border-radius:8px"> %</span>
    </div>
    <div id="modeNote" class="muted"></div>
  </div>
  <div class="card" style="padding:6px 12px"><div id="rows"></div></div>
  <div class="card" id="unmatchedCard" style="display:none">
    <details id="unDetails">
      <summary id="unSummary" style="margin:0"></summary>
      <p class="muted">These were ignored (other sections, teachers, or names I couldn't match). If one is really a student on your list, say who below, or add them as a new student.</p>
      <div id="unmatched"></div>
    </details>
  </div>
  <div class="dock">
    <div class="counts"><span class="s-p" id="cp">P 0</span><span class="s-x" id="cx">A 0</span><span class="s-l" id="cl">L 0</span><span class="s-e" id="ce">E 0</span></div>
    <button class="btn" id="cancel" type="button">Cancel</button>
    <button class="btn primary" id="confirm" type="button">Confirm &amp; save to Excel</button>
  </div>
</div>
<div class="card" id="done" style="display:none">
  <h2>Saved to Excel ✓</h2>
  <p id="doneMsg"></p>
  <a class="btn primary" id="doneLink" href="#">View records</a>
  <button class="btn" id="again" type="button">Scan another sheet</button>
</div>
<div class="toast" id="toast"></div>
</div>
<script>
(function () {
  var src = new URLSearchParams(location.search).get('source');
  if (src !== 'photo' && src !== 'csv') { src = 'csv'; try { src = localStorage.getItem('importSource') || 'csv'; } catch (e) {} }
  function show(s, remember) {
    if (s !== 'photo') s = 'csv';
    document.getElementById('csvPanel').style.display = s === 'csv' ? '' : 'none';
    document.getElementById('photoPanel').style.display = s === 'photo' ? '' : 'none';
    document.getElementById('segCsv').className = 'segbtn' + (s === 'csv' ? ' on' : '');
    document.getElementById('segPhoto').className = 'segbtn' + (s === 'photo' ? ' on' : '');
    if (remember) { try { localStorage.setItem('importSource', s); } catch (e) {} }
  }
  document.getElementById('segCsv').onclick = function () { show('csv', true); };
  document.getElementById('segPhoto').onclick = function () { show('photo', true); };
  show(src, false);
})();
</script>

<script>
const students = {{ students|tojson }};
const subject = {{ subject|tojson }};
const recorded = {{ recorded|tojson }};
const today = {{ today|tojson }};
const recordsUrl = {{ records_url|tojson }};
const $ = id => document.getElementById(id);
let entries = [], override = {}, blob = null;

function toast(msg, bad) {
  const t = $('toast'); t.textContent = msg; t.className = 'toast' + (bad ? ' err' : '');
  t.style.display = 'block'; clearTimeout(toast.h); toast.h = setTimeout(() => t.style.display = 'none', bad ? 6000 : 2500);
}
function showErr(msg) { const e = $('err'); e.textContent = msg; e.style.display = msg ? 'block' : 'none'; }

if ($('keySave')) $('keySave').onclick = async () => {
  const r = await fetch({{ key_url|tojson }}, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({key: $('keyIn').value})});
  const j = await r.json();
  if (j.ok) { location.reload(); } else { $('keyMsg').textContent = j.error; }
};

// shrink big phone photos in the browser before uploading
async function shrink(file) {
  const url = URL.createObjectURL(file);
  try {
    const img = new Image(); img.src = url; await img.decode();
    const max = 2000, k = Math.min(1, max / Math.max(img.naturalWidth, img.naturalHeight));
    const c = document.createElement('canvas');
    c.width = Math.round(img.naturalWidth * k); c.height = Math.round(img.naturalHeight * k);
    c.getContext('2d').drawImage(img, 0, 0, c.width, c.height);
    return await new Promise(res => c.toBlob(res, 'image/jpeg', 0.88));
  } finally { URL.revokeObjectURL(url); }
}

const MAX_IMAGES = {{ max_images|tojson }};
let blobs = [];
function showPreviews() {
  const box = $('previews'); box.textContent = '';
  blobs.forEach(b => {
    const im = document.createElement('img'); im.alt = ''; im.src = URL.createObjectURL(b);
    im.style.cssText = 'height:110px;border-radius:8px;border:1px solid var(--line)';
    box.appendChild(im);
  });
  $('read').textContent = blobs.length > 1 ? ('Read these ' + blobs.length + ' images') : 'Read the sheet';
  $('read').disabled = !blobs.length;
}
$('file').onchange = async e => {
  let files = Array.from(e.target.files); blobs = []; showErr(''); showPreviews();
  if (files.length > MAX_IMAGES) { showErr('Please choose at most ' + MAX_IMAGES + ' images. Using the first ' + MAX_IMAGES + '.'); files = files.slice(0, MAX_IMAGES); }
  try {
    for (const f of files) blobs.push(await shrink(f));
    showPreviews();
  } catch (err) { blobs = []; showPreviews(); showErr('One of those files could not be opened as a picture. Try JPG or PNG images.'); }
};

$('read').onclick = async () => {
  if (!blobs.length) return;
  $('read').disabled = true; $('busy').textContent = 'Reading… this can take up to a minute if the AI service is busy.'; showErr('');
  const fd = new FormData(); fd.append('subject', subject);
  blobs.forEach((b, i) => fd.append('image', b, 'sheet' + (i + 1) + '.jpg'));
  try {
    const r = await fetch({{ scan_url|tojson }}, {method: 'POST', body: fd});
    const j = await r.json();
    if (!j.ok) { showErr(j.error || 'Could not read the sheet.'); if (j.code === 'no_key') location.reload(); }
    else startReview(j.result);
  } catch (err) { showErr('Could not reach the site. Is the black window still open?'); }
  $('busy').textContent = ''; $('read').disabled = !blobs.length;
};

function startReview(res) {
  entries = res.entries.map(e => Object.assign({}, e, {orig: e.roster_match, assign: e.roster_match}));
  override = {};
  if (!entries.length) { showErr('I could not find any names on those images. Try clearer, straight-on photos.'); return; }
  const marked = entries.filter(e => e.mark === 'signed' || e.mark === 'checked').length;
  const withPct = entries.filter(e => e.attended_percent >= 0).length;
  $('mode').value = (withPct / entries.length >= 0.5) ? 'percent' : (marked / entries.length >= 0.5) ? 'marks' : 'list';
  $('unDetails').open = entries.filter(e => e.orig === '').length <= 3;
  $('date').value = '';
  $('dateNote').textContent = res.date_text ? ('The sheet says: ' + res.date_text + '. The date is left empty on purpose, so pick it yourself.') : 'No date was found on the sheet. Pick the date yourself.';
  $('step1').style.display = 'none'; $('review').style.display = 'block'; $('done').style.display = 'none';
  render(); window.scrollTo(0, 0);
}

function autoStatus(e) {
  if (e && e.written_status) return e.written_status;
  if (e && e.mark === 'crossed_out') return 'x';
  const m = $('mode').value;
  if (m === 'list') return e ? 'p' : 'x';
  if (m === 'percent') {
    if (!e) return 'x';
    if (e.attended_percent < 0) return 'p';          // listed but no percentage shown
    return e.attended_percent >= (parseFloat($('thr').value) || 0) ? 'p' : 'x';
  }
  return (e && (e.mark === 'signed' || e.mark === 'checked')) ? 'p' : 'x';
}
function rowsData() {
  const out = students.map(s => ({key: s.name, name: s.name, row: s.row, isNew: false, e: entries.find(x => x.assign === s.name)}));
  entries.filter(x => x.assign === '__new__').forEach((e, i) => out.push({key: '__new__' + i, name: e.written_name, row: null, isNew: true, e: e}));
  out.forEach(r => { r.auto = autoStatus(r.e); r.code = override[r.key] || r.auto; });
  return out;
}
const MARKS = {signed: '✍ signed', checked: '✓ ticked', crossed_out: '✗ crossed out', none: 'no mark'};

function render() {
  const rows = rowsData(), box = $('rows'); box.textContent = '';
  const n = {p: 0, x: 0, l: 0, e: 0};
  const md = $('mode').value;
  $('thrWrap').style.display = md === 'percent' ? 'inline' : 'none';
  $('modeNote').textContent = md === 'list'
    ? 'Everyone found on the sheet is Present; everyone else on your class list is Absent.'
    : md === 'percent'
    ? 'Students who attended at least ' + ($('thr').value || 0) + '% are Present; anyone below that, or not in the report, is Absent. Change the number if your rule is different.'
    : 'Only students with a signature or tick are Present; the rest are Absent.';
  rows.forEach(r => {
    n[r.code]++;
    const div = document.createElement('div');
    const doubt = r.e && r.e.confidence !== 'high';
    div.className = 'srow' + (doubt ? ' needs' : '');
    const nm = document.createElement('div'); nm.className = 'sname';
    nm.appendChild(document.createTextNode(r.name));
    if (r.isNew) { const t = document.createElement('span'); t.className = 'tag new'; t.textContent = 'NEW'; nm.appendChild(t); }
    if (doubt) { const t = document.createElement('span'); t.className = 'tag warn'; t.textContent = 'check'; nm.appendChild(t); }
    const sub = document.createElement('div'); sub.className = 'sub';
    sub.textContent = r.e
      ? ('Read as “' + r.e.written_name + '” · ' + (md === 'percent' && r.e.attended_percent >= 0 ? (r.e.attended_percent + '% attended') : (MARKS[r.e.mark] || '')))
      : 'Not found on the sheet';
    nm.appendChild(sub);
    const g = document.createElement('div'); g.className = 'btns';
    ['p', 'x', 'l', 'e'].forEach(c => {
      const b = document.createElement('button'); b.type = 'button'; b.className = 'cb sm ' + c + (r.code === c ? ' on' : '');
      b.textContent = c === 'x' ? 'A' : c.toUpperCase();
      b.onclick = () => { override[r.key] = c; render(); };
      g.appendChild(b);
    });
    div.appendChild(nm); div.appendChild(g); box.appendChild(div);
  });
  $('cp').textContent = 'P ' + n.p; $('cx').textContent = 'A ' + n.x; $('cl').textContent = 'L ' + n.l; $('ce').textContent = 'E ' + n.e;

  // names that could not be matched
  const un = entries.filter(e => e.orig === ''), ub = $('unmatched'); ub.textContent = '';
  $('unmatchedCard').style.display = un.length ? 'block' : 'none';
  $('unSummary').textContent = un.length + (un.length === 1 ? ' name is' : ' names are') + " not on your class list and " + (un.length === 1 ? 'is' : 'are') + ' ignored. Tap to review.';
  un.forEach(e => {
    const row = document.createElement('div'); row.className = 'srow';
    const nm = document.createElement('div'); nm.className = 'sname'; nm.textContent = e.written_name;
    const sel = document.createElement('select'); sel.className = 'slim';
    const add = (v, t) => { const o = document.createElement('option'); o.value = v; o.textContent = t; sel.appendChild(o); };
    add('', 'Ignore this name'); add('__new__', 'Add as a new student');
    students.forEach(s => add(s.name, 'Same person as: ' + s.name));
    sel.value = e.assign;
    sel.onchange = () => { e.assign = sel.value; render(); };
    row.appendChild(nm); row.appendChild(sel); ub.appendChild(row);
  });
}
$('mode').onchange = render;
$('thr').oninput = render;

function reset() {
  $('review').style.display = 'none'; $('done').style.display = 'none'; $('step1').style.display = 'block';
  $('file').value = ''; blobs = []; showPreviews(); showErr('');
}
$('cancel').onclick = () => { if (confirm('Discard this scan? Nothing has been saved to Excel.')) reset(); };
$('again').onclick = reset;

$('confirm').onclick = async () => {
  const d = $('date').value;
  if (!d) { toast('Pick a date first.', true); $('date').focus(); return; }
  if (recorded.includes(d) && !confirm('Attendance for ' + d + ' is already recorded. Replace it with this scan?')) return;
  const rows = rowsData(), btn = $('confirm'); btn.disabled = true;
  try {
    const r = await fetch({{ save_url|tojson }}, {method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({subject, date: d, topic: $('topic').value, source: 'scan',
        new_students: rows.filter(x => x.isNew).map(x => x.name),
        marks: rows.map(x => ({row: x.row, name: x.name, code: x.code}))})});
    const j = await r.json();
    if (j.ok) {
      if (!recorded.includes(d)) recorded.push(d);
      const c = {p: 0, x: 0, l: 0, e: 0}; rows.forEach(x => c[x.code]++);
      $('doneMsg').textContent = d + ': ' + c.p + ' present, ' + c.x + ' absent, ' + c.l + ' late, ' + c.e + ' excused.';
      $('doneLink').href = recordsUrl;
      $('review').style.display = 'none'; $('done').style.display = 'block'; window.scrollTo(0, 0);
    } else { toast(j.error || 'Could not save.', true); }
  } catch (err) { toast('Could not reach the site. Is the black window still open?', true); }
  btn.disabled = false;
};
</script>
{% endif %}
{% endblock %}"""

LOG = r"""{% extends "base.html" %}
{% block title %}Changes log{% endblock %}
{% block body %}
<h1>Changes log</h1>
<p class="muted">Every change made from this website: who, when, and what. Changes you make directly in Excel are not recorded here.{% if total > shown|length %} Showing the latest {{ shown|length }} of {{ total }}.{% endif %}</p>
{% if not shown %}
<div class="card">Nothing yet. Changes will appear here from now on.</div>
{% else %}
<div class="toolbar"><input type="text" id="q" class="grow" placeholder="Search the log (name, subject, date…)"></div>
<div class="card" style="padding:6px 12px;overflow:auto">
<table id="logt">
<thead><tr><th>When</th><th>What</th><th>Subject</th><th>Details</th><th>From</th></tr></thead>
<tbody>
{% for e in shown %}<tr><td style="white-space:nowrap">{{ e.when }}</td><td style="white-space:nowrap"><b>{{ e.action }}</b></td><td>{{ e.subject }}</td><td>{{ e.detail }}</td><td style="white-space:nowrap">{{ e.who }}</td></tr>{% endfor %}
</tbody></table></div>
<script>
document.getElementById('q').oninput = e => {
  const q = e.target.value.trim().toLowerCase();
  document.querySelectorAll('#logt tbody tr').forEach(r => r.style.display = r.textContent.toLowerCase().includes(q) ? '' : 'none');
};
</script>
{% endif %}
{% endblock %}"""

LOGIN = r"""{% extends "base.html" %}
{% block title %}Sign In{% endblock %}
{% block body %}
<div class="card" style="max-width:400px;margin:30px auto;padding:24px 20px;text-align:center">
  <div style="font-size:38px;margin-bottom:8px">🔒</div>
  <h1 style="font-size:22px;margin:0 0 6px">Attendance Sign In</h1>
  <p class="muted" style="margin:0 0 16px;font-size:14px">Enter teacher password to manage attendance, or student password to view records.</p>
  {% if error %}<div class="flash err" style="text-align:left">{{ error }}</div>{% endif %}
  <form method="post" action="{{ url_for('login') }}">
    <input type="password" name="password" autofocus autocomplete="current-password" placeholder="Enter password..." required style="width:100%;margin-bottom:14px;padding:12px;font-size:15px;border:1.5px solid var(--line);border-radius:10px;background:#fff;outline:none">
    <button class="btn primary" type="submit" style="width:100%;padding:12px;font-size:16px;border-radius:10px">Sign In</button>
  </form>
</div>
{% endblock %}"""

FILES = r"""{% extends "base.html" %}
{% block title %}Excel file{% endblock %}
{% block body %}
<h1>Where your Excel file is saved</h1>
<div class="card">
  <h2>attendance_records.xlsx</h2>
  <p class="muted" style="margin:0 0 4px">Full location on the computer that runs this site:</p>
  <p style="margin:0 0 10px"><code id="fpath" style="display:block;padding:10px 12px;background:#f0f3f9;border-radius:8px;word-break:break-all;font-size:14px">{{ xlsx_path }}</code></p>
  <p class="muted" style="margin:0 0 4px">Folder:</p>
  <p style="margin:0 0 12px"><code id="fdir" style="display:block;padding:10px 12px;background:#f0f3f9;border-radius:8px;word-break:break-all;font-size:14px">{{ folder }}</code></p>
  <p style="margin:0 0 12px">
    {% if exists %}<span class="badge done">File exists</span> {{ size }} · last saved {{ modified }}
    {% else %}<span class="badge todo">Not created yet</span> It is created when you first mark attendance or open the site.{% endif %}
  </p>
  <div class="toolbar">
    <a class="btn primary" href="{{ url_for('download') }}">⬇ Download a copy</a>
    <button class="btn" type="button" id="copyPath">Copy file path</button>
    {% if is_local %}
    <button class="btn" type="button" id="openFolder">Open folder on this PC</button>
    <button class="btn" type="button" id="openFile">Open in Excel on this PC</button>
    {% endif %}
  </div>
  <div id="msg" class="muted"></div>
</div>
<div class="card">
  <h2>How saving works</h2>
  <ul style="margin:0;padding-left:20px">
    <li>Every time you press <b>Save to Excel</b> or confirm a scan, the change is written straight into the file above.</li>
    <li>The file always stays on the computer that runs <code>start.bat</code>, even when you use the site from your phone.</li>
    <li><b>Download a copy</b> sends a copy to the device you are using now. From a phone it goes to the phone's Downloads. The copy does not update later, so download again for the latest.</li>
    <li>If Excel has the file open, saving from the website is blocked until you close Excel.</li>
    <li>To move the file, stop the site, move <code>attendance_records.xlsx</code> to another folder, then edit <code>XLSX</code> near the top of <code>app.py</code>.</li>
    <li>The changes log is a separate file in the same folder: <code>{{ log_name }}</code>.</li>
  </ul>
</div>
<script>
const $ = id => document.getElementById(id);
function say(t, bad) { $('msg').textContent = t; $('msg').style.color = bad ? 'var(--x)' : 'var(--p)'; }
$('copyPath').onclick = async () => {
  const t = $('fpath').textContent;
  try { await navigator.clipboard.writeText(t); say('Path copied.'); }
  catch (e) { const r = document.createRange(); r.selectNodeContents($('fpath')); const s = getSelection(); s.removeAllRanges(); s.addRange(r); say('Press Ctrl+C to copy the selected path.'); }
};
async function openIt(what) {
  try {
    const r = await fetch({{ open_url|tojson }}, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({what})});
    const j = await r.json(); say(j.ok ? j.message : (j.error || 'Could not open it.'), !j.ok);
  } catch (e) { say('Could not reach the site. Is the black window still open?', true); }
}
if ($('openFolder')) { $('openFolder').onclick = () => openIt('folder'); $('openFile').onclick = () => openIt('file'); }
</script>
{% endblock %}"""

PRINT = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Print sheet - {{ subject }}</title>
<style>
@page { size: A4 landscape; margin: 8mm; }
* { box-sizing: border-box; }
body { --sw: 281mm; --dc: calc((var(--sw) - 85mm) / 25); margin: 0; background: #e9edf3; color: #111; font-family: Arial, Helvetica, sans-serif; }
.bar { max-width: var(--sw); margin: 12px auto; padding: 10px 14px; background: #fff; border: 1px solid #cfd6e2; border-radius: 10px; font-size: 14px; }
.bar label { display: inline-block; margin: 4px 10px 4px 0; }
.bar input { padding: 6px 8px; border: 1px solid #b9c2d3; border-radius: 6px; font-size: 14px; }
.bar button { padding: 8px 16px; border: 0; border-radius: 8px; background: #2f5fb3; color: #fff; font-size: 15px; cursor: pointer; }
.bar .subj a { margin-right: 10px; }
.bar .subj a.on { font-weight: bold; text-decoration: none; color: #111; }
.warn { margin-top: 8px; padding: 8px 10px; background: #fff4d6; border: 1px solid #f0cf7a; border-radius: 8px; }
.note { margin-top: 8px; color: #444; }
.sheet { width: var(--sw); margin: 12px auto; background: #fff; padding: 0; box-shadow: 0 1px 6px rgba(0,0,0,.18); page-break-after: always; }
.sheet:last-of-type { page-break-after: auto; }
.blue { background: #9cc2e5; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
.stripe { background: #6fa0d2; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
.head { display: flex; align-items: stretch; border: 1px solid #333; border-bottom: 0; min-height: 16mm; }
.head .left { width: 80mm; padding: 3mm; border-right: 1px solid #333; display: flex; flex-direction: column; justify-content: center; }
.head .title { font-weight: bold; font-size: 10pt; letter-spacing: .3px; }
.head .school { margin-top: 2mm; font-size: 9pt; font-weight: bold; color: #1d3f78; }
.head .right { flex: 1; padding: 2mm 4mm; display: flex; flex-direction: column; justify-content: center; }
.head .section { font-size: 18pt; font-weight: bold; min-height: 8mm; }
.head .sem { font-size: 11pt; font-weight: bold; color: #1d3f78; }
.head .subj { font-size: 9pt; }
.head .line { display: flex; gap: 4mm; align-items: baseline; }
table { width: 100%; border-collapse: collapse; table-layout: fixed; border: 1px solid #333; }
th, td { border: 1px solid #555; padding: 0; text-align: center; overflow: hidden; white-space: nowrap; }
th.namehead { font-size: 12pt; font-weight: bold; }
th.lab { font-size: 5.5pt; font-weight: bold; }
th.date { height: 5.5mm; }
th.topic { padding: 0 .3mm; }
td { height: 4.7mm; font-size: 9.5pt; font-weight: bold; line-height: 1; }
td.nn { font-size: 6.5pt; font-weight: normal; }
td.nm { text-align: left; padding-left: 1.5mm; font-size: 8.5pt; font-weight: normal; text-overflow: ellipsis; }
tr { page-break-inside: avoid; }
.tot { display: none; }
body.showtotals th.tot, body.showtotals td.tot { display: table-cell; }
body.showtotals col.tot { display: table-column; }
body.showtotals .padtot { display: none; }
col.dc { width: var(--dc); }
col.t1 { width: calc(var(--dc) * 1.2); }
col.t2 { width: calc(var(--dc) * 0.8); }
.fit { display: block; width: 100%; overflow: hidden; text-align: center; overflow-wrap: anywhere; line-height: 1.05; }
th.date .fit { height: 5.5mm; line-height: 5.5mm; font-size: 7pt; white-space: nowrap; font-weight: bold; }
th.topic .tc { height: 25mm; display: flex; align-items: center; justify-content: center; overflow: hidden; }
th.topic .fit { display: block; white-space: normal; width: auto; height: 24.5mm; max-width: 7.5mm; overflow: hidden; writing-mode: vertical-rl; transform: rotate(180deg); text-align: center; font-size: 6.5pt; font-weight: normal; line-height: 1.1; }
th.tot { font-size: 6.5pt; font-weight: bold; }
td.tot { font-size: 9pt; font-weight: bold; }
.totn { display: none; }
body.showtotals .totn { display: inline; }
.legend { margin-top: 2mm; font-size: 7.5pt; color: #333; }
@media print {
  body { background: #fff; }
  .bar { display: none; }
  .sheet { margin: 0; box-shadow: none; width: auto; }
}
</style>
<style id="pageStyle"></style></head><body>
<div class="bar">
  <button type="button" onclick="window.print()">&#128424; Print</button>
  <a href="{{ url_for('records', subject=subject) }}" style="margin-left:12px">&larr; Back to records</a>
  <div class="subj" style="margin-top:8px">Subject:
    {% for s in subjects %}<a class="{{ 'on' if s == subject }}" href="{{ url_for('print_sheet', subject=s) }}">{{ s }}</a>{% endfor %}
  </div>
  <div style="margin-top:6px">
    <label>Paper <select id="inPaper"><option value="a4">A4 landscape</option><option value="long">Long bond 8.5 x 13 in, landscape</option><option value="letter">Letter (short) 8.5 x 11 in, landscape</option></select></label>
    <label>School <input id="inSchool" size="26"></label>
    <label>Section <input id="inSection" size="12" placeholder="e.g. BS CS 1-A"></label>
    <label>Semester <input id="inSem" size="16" placeholder="e.g. 1st Sem 2026"></label>
  </div>
  <div style="margin-top:8px"><label><input type="checkbox" id="chkTot"> <b>Show TOTAL and REC columns</b> (use this for the final copy you hand in)</label>
    <span class="note">Classes held so far: <b>{{ held }}</b>.{% if skipped %} Not counted (no marks at all): {{ skipped|join(', ') }}.{% endif %}</span></div>
  {% if unmarked %}<div class="warn"><b>Check before printing:</b> some cells have no mark, and the teacher's sheet reads a blank as <b>present</b>.
    {% for u in unmarked %}<span style="white-space:nowrap">{{ u.label }}: {{ u.n }}{{ ',' if not loop.last }}</span> {% endfor %}</div>{% endif %}
  {% if extra_l or extra_e %}<div class="note">{% if extra_l %}{{ extra_l }} late mark(s) print as blank (present). {% endif %}{% if extra_e %}{{ extra_e }} excused mark(s) print as E. {% endif %}</div>{% endif %}
  <div class="note">Tip: pick the paper above first. In the print window the paper and landscape are already set; keep margins <b>Default</b> and turn on <b>Background graphics</b> so the blue shows. To make a PDF, choose <b>Save as PDF</b> as the printer.</div>
</div>
{% for pg in pages %}
<div class="sheet">
  <div class="head blue">
    <div class="left"><div class="title">CLASS ATTENDANCE MONITORING</div><div class="school o-school"></div></div>
    <div class="right"><div class="section o-section"></div><div class="line"><div class="sem o-sem"></div><div class="subj">{{ subject }}{% if pages|length > 1 %} &middot; page {{ loop.index }} of {{ pages|length }}{% endif %}</div></div></div>
  </div>
  <table>
    <colgroup><col style="width:7mm"><col style="width:70mm"><col style="width:8mm">{% for c in pg.cols %}<col class="dc">{% endfor %}<col class="tot t1"><col class="tot t2">{% for i in range(pg.pad) %}<col class="dc{{ ' padtot' if i < 2 }}">{% endfor %}</colgroup>
    <thead>
      <tr class="blue"><th class="namehead" rowspan="2" colspan="2">NAME</th><th class="lab">DATE</th>
        {% for c in pg.cols %}<th class="date"><div class="fit">{{ c.label }}</div></th>{% endfor %}<th class="tot" rowspan="2">TOTAL</th><th class="tot" rowspan="2">REC</th>{% for i in range(pg.pad) %}<th class="date{{ ' padtot' if i < 2 }}"></th>{% endfor %}</tr>
      <tr class="blue"><th class="lab">TOPIC</th>
        {% for c in pg.cols %}<th class="topic" title="{{ c.topic }}"><div class="tc"><span class="fit">{{ c.topic }}</span></div></th>{% endfor %}{% for i in range(pg.pad) %}<th class="topic{{ ' padtot' if i < 2 }}"></th>{% endfor %}</tr>
    </thead>
    <tbody>
    {% for r in pg.rows %}<tr><td class="nn">{{ r.n }}</td><td class="nm">{{ r.name }}</td><td class="stripe"></td>
      {% for m in r.marks %}<td>{{ m }}</td>{% endfor %}<td class="tot">{{ r.total }}</td><td class="tot">{{ r.rec }}</td>{% for i in range(pg.pad) %}<td class="{{ 'padtot' if i < 2 }}"></td>{% endfor %}</tr>{% endfor %}
    </tbody>
  </table>
  <div class="legend">Blank = present &nbsp;&middot;&nbsp; X = absent &nbsp;&middot;&nbsp; R = recited<span class="totn"> &nbsp;&middot;&nbsp; TOTAL = days present / classes held (R counts as present) &nbsp;&middot;&nbsp; REC = times recited</span></div>
</div>
{% endfor %}
{% if not pages %}<div class="bar">No students or days recorded yet.</div>{% endif %}
<script>
(function () {
  var K = {school: "sheet_school", section: "sheet_section", sem: "sheet_semester"};
  var D = {school: "ECLARO ACADEMY, INC.", section: "", sem: ""};
  function get(k) { try { var v = localStorage.getItem(K[k]); return v === null ? D[k] : v; } catch (e) { return D[k]; } }
  function put(k, v) { try { localStorage.setItem(K[k], v); } catch (e) {} }
  function paint(k, cls) { var v = get(k); document.querySelectorAll(cls).forEach(function (n) { n.textContent = v; }); }
  function fit() {
    document.querySelectorAll(".fit").forEach(function (el) {
      el.style.fontSize = "";
      var s = parseFloat(getComputedStyle(el).fontSize) * 0.75;
      while ((el.scrollWidth > el.clientWidth + 0.5 || el.scrollHeight > el.clientHeight + 0.5) && s > 3.5) {
        s -= 0.25; el.style.fontSize = s + "pt";
      }
    });
  }
  fit(); window.addEventListener("beforeprint", fit);
  var PAPER = {a4: [297, 210], long: [330.2, 215.9], letter: [279.4, 215.9]};
  var paperSel = document.getElementById("inPaper");
  function setPaper(k) {
    var p = PAPER[k] || PAPER.a4;
    document.getElementById("pageStyle").textContent = "@page { size: " + p[0] + "mm " + p[1] + "mm; margin: 8mm; }";
    document.body.style.setProperty("--sw", (p[0] - 16) + "mm");
    fit();
  }
  try { paperSel.value = localStorage.getItem("sheet_paper") || "a4"; } catch (e) {}
  if (!paperSel.value) paperSel.value = "a4";
  setPaper(paperSel.value);
  paperSel.addEventListener("change", function () { setPaper(paperSel.value); try { localStorage.setItem("sheet_paper", paperSel.value); } catch (e) {} });
  var chk = document.getElementById("chkTot");
  function setTot(on) { document.body.classList.toggle("showtotals", on); }
  try { chk.checked = localStorage.getItem("sheet_totals") === "1"; } catch (e) {}
  setTot(chk.checked);
  chk.addEventListener("change", function () { setTot(chk.checked); try { localStorage.setItem("sheet_totals", chk.checked ? "1" : "0"); } catch (e) {} });
  [["school", "inSchool", ".o-school"], ["section", "inSection", ".o-section"], ["sem", "inSem", ".o-sem"]].forEach(function (t) {
    var inp = document.getElementById(t[1]);
    inp.value = get(t[0]); paint(t[0], t[2]);
    inp.addEventListener("input", function () { put(t[0], inp.value); paint(t[0], t[2]); });
  });
})();
</script>
</body></html>"""


MEET_IMPORT = r"""{% extends "base.html" %}
{% block title %}Import Meet CSV{% endblock %}
{% block body %}
<h1>Import attendance</h1>
<p class="muted" style="margin-top:0">Reading a <b>Google Meet CSV</b>. &nbsp;<a href="{{ url_for('scan', subject=subject) }}">&larr; Choose another file</a> &middot; <a href="{{ url_for('scan', subject=subject, source='photo') }}">Use a photo instead</a></p>
{% if not subject %}<div class="card">Add a subject first.</div>
{% else %}
<style>
.mi td, .mi th { padding: 6px 10px; text-align: left; border-bottom: 1px solid #e5e9f2; }
.mi select { padding: 5px; font-size: 14px; }
.mi tr.partial td { background: #fff4d6; }
.mi tr.gone td.nm { color: #8a1c1c; }
.mi .muted { color: #667; font-size: 13px; }
</style>
<div class="card">
  <p><b>{{ review.subject }}</b> · {{ review.date_label }}{% if review.when %} · meeting {{ review.when }}{% endif %}<br>
  <span class="muted">Present = in the call at least {{ review.pct }}% of the meeting (<span id="thr"></span>). Meeting length: <span id="len"></span>.</span></p>
  {% if review.topic %}<p class="muted">Topic: {{ review.topic }}</p>{% endif %}
  {% if review.existing_date %}<p style="background:#fff4d6;padding:8px;border-radius:8px">This day is already recorded. Saving will replace those marks (R, L and E marks are kept where they still make sense).</p>{% endif %}
  <p id="summary"><b></b></p>
</div>
<div class="card" style="overflow-x:auto">
  <table class="mi" style="width:100%;border-collapse:collapse"><thead><tr><th>#</th><th>Student</th><th>Meet name</th><th>In call</th><th>Mark</th></tr></thead><tbody id="rows"></tbody></table>
</div>
<div class="card" id="ucard" style="overflow-x:auto">
  <p><b>Names in the file that I could not match</b><br><span class="muted">If one of these is a student on your list (for example a nickname or a shared account), pick them. I will remember it for next time. Leave the rest as they are.</span></p>
  <table class="mi" style="width:100%;border-collapse:collapse"><tbody id="urows"></tbody></table>
</div>
<p><button class="btn primary" type="button" id="saveBtn">Save attendance</button>
<a class="btn" href="{{ url_for('scan', subject=review.subject) }}">Start over</a>
<span id="msg" class="muted" style="margin-left:10px"></span></p>
<script type="application/json" id="meetData">{{ review|tojson }}</script>
<script>
(function () {
  var D = JSON.parse(document.getElementById('meetData').textContent);
  var S = D.students, U = D.unmatched;
  var assign = U.map(function () { return -1; });
  var touched = S.map(function () { return false; });
  var LABEL = {p: 'Present', x: 'Absent', l: 'Late', e: 'Excused', r: 'Recited'};
  var rows = document.getElementById('rows'), urows = document.getElementById('urows');
  function z(n) { return (n < 10 ? '0' : '') + n; }
  function fmt(s) { var h = Math.floor(s / 3600), m = Math.floor(s % 3600 / 60); return h ? h + ':' + z(m) + ':' + z(s % 60) : m + ':' + z(s % 60); }
  function secsOf(i) { var t = S[i].secs; U.forEach(function (u, k) { if (assign[k] === i) t += u.secs; }); return t; }
  function nameOf(i) { var n = S[i].meet ? [S[i].meet] : []; U.forEach(function (u, k) { if (assign[k] === i) n.push(u.meet); }); return n.join(', '); }
  function auto(i) {
    var t = secsOf(i), old = S[i].old;
    if (t >= D.threshold) return (old === 'r' || old === 'l') ? old : 'p';
    return old === 'e' ? 'e' : 'x';
  }
  function cell(tr, text, cls) { var td = document.createElement('td'); td.textContent = text; if (cls) td.className = cls; tr.appendChild(td); return td; }
  document.getElementById('thr').textContent = fmt(D.threshold);
  document.getElementById('len').textContent = fmt(D.length);
  var sels = [], metaCells = [], timeCells = [], trs = [];
  S.forEach(function (s, i) {
    var tr = document.createElement('tr');
    cell(tr, String(i + 1)); cell(tr, s.name, 'nm');
    metaCells[i] = cell(tr, ''); timeCells[i] = cell(tr, '');
    var td = document.createElement('td'), sel = document.createElement('select');
    Object.keys(LABEL).forEach(function (c) { var o = document.createElement('option'); o.value = c; o.textContent = LABEL[c]; sel.appendChild(o); });
    sel.addEventListener('change', function () { touched[i] = true; summary(); });
    td.appendChild(sel); tr.appendChild(td); rows.appendChild(tr);
    sels[i] = sel; trs[i] = tr;
  });
  U.forEach(function (u, k) {
    var tr = document.createElement('tr');
    cell(tr, u.meet); cell(tr, fmt(u.secs));
    var td = document.createElement('td'), sel = document.createElement('select');
    var o0 = document.createElement('option'); o0.value = '-1'; o0.textContent = 'Not a student on my list'; sel.appendChild(o0);
    S.forEach(function (s, i) { var o = document.createElement('option'); o.value = String(i); o.textContent = s.name; sel.appendChild(o); });
    sel.addEventListener('change', function () { assign[k] = parseInt(sel.value, 10); refresh(); });
    td.appendChild(sel); tr.appendChild(td); urows.appendChild(tr);
  });
  if (!U.length) document.getElementById('ucard').style.display = 'none';
  function summary() {
    var n = {p: 0, x: 0, l: 0, e: 0, r: 0};
    sels.forEach(function (s) { n[s.value]++; });
    document.querySelector('#summary b').textContent = 'Present ' + n.p + ' · Absent ' + n.x + ' · Late ' + n.l + ' · Excused ' + n.e + ' · Recited ' + n.r;
  }
  function refresh() {
    S.forEach(function (s, i) {
      var t = secsOf(i);
      metaCells[i].textContent = nameOf(i) || '—';
      timeCells[i].textContent = t ? fmt(t) + ' (' + Math.round(Math.min(1, t / D.length) * 100) + '%)' : '—';
      if (!touched[i]) sels[i].value = auto(i);
      trs[i].className = (t > 0 && t < D.threshold) ? 'partial' : (t === 0 ? 'gone' : '');
      if (t > 0 && t < D.threshold) timeCells[i].textContent += ' · left early';
    });
    summary();
  }
  refresh();
  var btn = document.getElementById('saveBtn'), msg = document.getElementById('msg');
  function post(url, body) {
    return fetch(url, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)})
      .then(function (r) { return r.json().catch(function () { return {ok: false, error: 'Unexpected reply from the site.'}; }); });
  }
  btn.addEventListener('click', function () {
    btn.disabled = true; msg.textContent = 'Saving…';
    var aliases = [];
    U.forEach(function (u, k) { if (assign[k] >= 0) aliases.push({meet: u.meet, student: S[assign[k]].name}); });
    var marks = S.map(function (s, i) { return {row: s.row, name: s.name, code: sels[i].value}; });
    (aliases.length ? post(D.alias_url, {aliases: aliases}) : Promise.resolve({ok: true}))
      .then(function () { return post(D.save_url, {subject: D.subject, date: D.date_iso, topic: D.topic, marks: marks, source: 'meet'}); })
      .then(function (r) { if (r.ok) { location.href = D.records_url; } else { msg.textContent = r.error || 'Could not save.'; btn.disabled = false; } })
      .catch(function () { msg.textContent = 'Could not reach the site.'; btn.disabled = false; });
  });
})();
</script>
{% endif %}
{% endblock %}"""


app.jinja_env.loader = DictLoader({
    "base.html": BASE, "dashboard.html": DASHBOARD, "mark.html": MARK,
    "print.html": PRINT, "import.html": MEET_IMPORT, "records.html": RECORDS, "students.html": STUDENTS, "scan.html": SCAN, "log.html": LOG, "files.html": FILES, "login.html": LOGIN,
})


# -------------------------------------------------------------------- routes
LOCKED_MSG = ("Excel has attendance_records.xlsx open, so it can't be changed right now. "
              "Save and close it in Excel, then try again.")


def make_tabs(subjects, current, endpoint, **extra):
    return [{"name": s, "active": s == current, "url": url_for(endpoint, subject=s, **extra)} for s in subjects]


def pick_subject(data):
    subjects = list(data.keys())
    wanted = request.args.get("subject") or request.form.get("subject")
    return subjects, (wanted if wanted in data else (subjects[0] if subjects else None))


@app.errorhandler(FileLocked)
def handle_locked(_e):
    if request.path.startswith("/api/"):
        return jsonify(ok=False, error=LOCKED_MSG), 423
    flash(LOCKED_MSG, "err")
    return redirect(request.referrer or url_for("dashboard"))


def read_passwords():
    out = {"teacher": [], "student": []}
    env_t = os.environ.get("ATTENDANCE_TEACHER_PASSWORD", "").strip()
    if env_t:
        out["teacher"].extend([p.strip() for p in env_t.split(",") if p.strip()])
    env_s = os.environ.get("ATTENDANCE_STUDENT_PASSWORD", "").strip()
    if env_s:
        out["student"].extend([p.strip() for p in env_s.split(",") if p.strip()])
    try:
        with open(PASSWORD_FILE, encoding="utf-8-sig") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip().lower()
                if k in ("teacher", "student"):
                    for p in v.split(","):
                        cleaned = p.strip().strip("'\"")
                        if cleaned and cleaned not in out[k]:
                            out[k].append(cleaned)
    except OSError:
        pass
    return out


def password_problem(cfg):
    """None when the passwords are usable, otherwise a short explanation."""
    t, s = cfg["teacher"], cfg["student"]
    if not t:
        return "No teacher password is set yet in passwords.txt."
    for p in t:
        if len(p) < MIN_PASSWORD:
            return f"A teacher password is too short (use at least {MIN_PASSWORD} characters)."
    for p in s:
        if len(p) < MIN_PASSWORD:
            return f"A student password is too short (use at least {MIN_PASSWORD} characters)."
    if any(p in t for p in s):
        return "Student passwords must be different from teacher passwords."
    return None


def pw_version(role, cfg):
    pws = ",".join(sorted(cfg[role]))
    return hmac.new(app.secret_key.encode(), f"{role}:{pws}".encode(), hashlib.sha256).hexdigest()[:20]


def current_role():
    cfg = read_passwords()
    role = session.get("role")
    if role in ("teacher", "student") and cfg.get(role) and hmac.compare_digest(
            str(session.get("pv", "")), pw_version(role, cfg)):
        return role
    return None


def locked_page(problem):
    path = escape(PASSWORD_FILE)
    html = (
        "<!doctype html><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<title>Site locked</title><body style=\"font:16px/1.5 system-ui,Segoe UI,Arial;max-width:640px;margin:40px auto;padding:0 16px;background:#f8fafc;color:#0f172a\">"
        "<div style='background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:24px;box-shadow:0 2px 8px rgba(0,0,0,0.05)'>"
        "<h1 style='margin-top:0;font-size:22px'>🔒 This site is locked</h1>"
        f"<p style='color:#dc2626;font-weight:700'>{escape(problem)}</p>"
        "<p>To protect student names on PythonAnywhere, a teacher password must be set before opening the site.</p>"
        "<p>Open or create a plain text file at this location:</p>"
        f"<pre style='background:#f1f5f9;padding:12px;border-radius:8px;white-space:pre-wrap;word-break:break-all;font-size:14px'>{path}</pre>"
        "<p>and add these lines (at least " + str(MIN_PASSWORD) + " characters for security):</p>"
        "<pre style='background:#f1f5f9;padding:12px;border-radius:8px;font-size:14px'>teacher=your-teacher-password\nstudent=your-student-password</pre>"
        "<p>You can also add multiple teacher passwords separated by commas.</p>"
        "<p>Then refresh this page.</p></div></body>")
    return html, 503


_fails = {}


def fail_key():
    return (request.remote_addr or "") + "|" + request.headers.get("X-Forwarded-For", "").split(",")[0].strip()


PUBLIC_ENDPOINTS = {"login", "logout", "static", "subject_image"}
STUDENT_ENDPOINTS = {"records"}


@app.context_processor
def inject_auth():
    return {"role": getattr(g, "role", None), "auth_on": bool(read_passwords()["teacher"])}


@app.before_request
def gate():
    g.role = None
    if request.method == "POST":
        origin = request.headers.get("Origin")
        if origin and urllib.parse.urlparse(origin).netloc != request.host:
            msg = "That request came from another site and was blocked."
            return (jsonify(ok=False, error=msg), 403) if request.path.startswith("/api/") else (msg, 403)
    if request.endpoint is None:
        return None
    cfg = read_passwords()
    if OPEN_MODE and not cfg["teacher"]:
        g.role = "teacher"
        return None
    problem = password_problem(cfg)
    if problem:
        return locked_page(problem)
    if request.endpoint in PUBLIC_ENDPOINTS:
        g.role = current_role()
        return None
    role = current_role()
    g.role = role
    if role == "teacher" or (role == "student" and request.endpoint in STUDENT_ENDPOINTS):
        return None
    if request.path.startswith("/api/"):
        if role:
            return jsonify(ok=False, error="Your sign-in does not allow that."), 403
        return jsonify(ok=False, error="Please sign in again."), 401
    return redirect(url_for("records") if role == "student" else url_for("login"))


@app.after_request
def secure_headers(resp):
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "same-origin")
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.route("/login", methods=["GET", "POST"])
def login():
    cfg = read_passwords()
    if OPEN_MODE and not cfg["teacher"]:
        return redirect(url_for("dashboard"))
    error = ""
    if request.method == "POST":
        key, now = fail_key(), time.time()
        count, until = _fails.get(key, (0, 0))
        if until > now:
            error = f"Too many wrong passwords. Wait {int((until - now) // 60) + 1} minute(s) and try again."
        else:
            pw = request.form.get("password", "").strip()
            role = None
            if any(hmac.compare_digest(pw.encode(), t_pw.encode()) for t_pw in cfg["teacher"]):
                role = "teacher"
            elif any(hmac.compare_digest(pw.encode(), s_pw.encode()) for s_pw in cfg["student"]):
                role = "student"
            if role:
                session.clear()
                session.update(role=role, pv=pw_version(role, cfg))
                session.permanent = True
                _fails.pop(key, None)
                log_change("Sign-in", "", f"{role.capitalize()} signed in")
                return redirect(url_for("dashboard") if role == "teacher" else url_for("records"))
            time.sleep(0.5)
            count += 1
            _fails[key] = (0, now + 300) if count >= 5 else (count, 0)
            log_change("Failed sign-in", "", "Wrong password" + (" (locked for 5 minutes)" if count >= 5 else ""))
            error = "Wrong password."
    return render_template("login.html", page="login", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/")
def dashboard():
    data = load_data()
    today = date.today()
    cards = []
    for name, sd in data.items():
        stats = student_stats(sd)
        rated = [s for s in stats if s["rate"] is not None]
        avg = sum(s["rate"] for s in rated) / len(rated) if rated else None
        today_counts, absent = None, []
        tcol = next((d["col"] for d in sd["dates"] if d["date"] == today), None)
        if tcol is not None:
            today_counts = {"p": 0, "x": 0, "l": 0, "e": 0, "r": 0}
            for s in sd["students"]:
                code = sd["cells"].get((s["row"], tcol), "")
                if code and code in today_counts:
                    today_counts[code] += 1
                if code == "x":
                    absent.append(s["name"])
        watch = sorted([s for s in rated if s["rate"] < LOW_RATE], key=lambda s: s["rate"])
        cards.append({"name": name, "n_students": len(stats), "held": len(sd["dates"]), "avg": avg,
                      "today": today_counts, "absent_today": absent, "watch": watch,
                      "image_url": subject_image_url(name)})
    return render_template("dashboard.html", page="dashboard", cards=cards, low=LOW_RATE, today_iso=today.isoformat(),
                           today_label=today.strftime("%A, %B %d, %Y").replace(" 0", " "))


@app.route("/mark")
def mark():
    data = load_data()
    subjects, subject = pick_subject(data)
    d = parse_iso(request.args.get("date"))          # no date unless you pick one
    today = date.today()
    extra = {"date": d.isoformat()} if d else {}
    today_url = url_for("mark", subject=subject, date=today.isoformat()) if subject else ""
    ctx = dict(page="mark", subject=subject, tabs=make_tabs(subjects, subject, "mark", **extra),
               students=[], date_iso=d.isoformat() if d else "", recorded=False, topic="", today_url=today_url)
    if subject:
        sd = data[subject]
        col = next((x["col"] for x in sd["dates"] if x["date"] == d), None) if d else None
        topic = next((x["topic"] for x in sd["dates"] if x["date"] == d), "") if d else ""
        ctx["students"] = [{"row": s["row"], "name": s["name"],
                            "code": (sd["cells"].get((s["row"], col), "") if col else "") or "p"}
                           for s in sd["students"]]
        ctx.update(recorded=col is not None, topic=topic, subject_img_url=subject_image_url(subject),
                   base_url=url_for("mark", subject=subject), save_url=url_for("api_save"),
                   prev_url=url_for("mark", subject=subject, date=(d - timedelta(days=1)).isoformat()) if d else "",
                   next_url=url_for("mark", subject=subject, date=(d + timedelta(days=1)).isoformat()) if d else "",
                   date_label=d.strftime("%A, %B %d, %Y").replace(" 0", " ") if d else "")
    return render_template("mark.html", **ctx)


@app.route("/api/save", methods=["POST"])
def api_save():
    body = request.get_json(silent=True) or {}
    d = parse_iso(body.get("date"))
    items = body.get("marks")
    if not d or not isinstance(items, list) or len(items) > 1000:
        return jsonify(ok=False, error="That request was not understood."), 400
    clean = [{"row": it.get("row"), "name": it.get("name"), "code": it.get("code"), "clear": bool(it.get("clear"))}
             for it in items if isinstance(it, dict)]
    new_raw = body.get("new_students")
    new_names = [str(n)[:80] for n in new_raw[:100]] if isinstance(new_raw, list) else []
    try:
        res = apply_marks(str(body.get("subject", "")), d, str(body.get("topic", ""))[:120], clean, new_names)
    except ValueError as err:
        return jsonify(ok=False, error=str(err)), 400
    subject = str(body.get("subject", ""))
    counts = {"p": 0, "x": 0, "l": 0, "e": 0, "r": 0, "": 0}
    for name, old, new in res["changes"]:
        if new in counts:
            counts[new] += 1
        elif new:
            counts["p"] += 1
    kind = {"scan": "Scan", "meet": "Meet import"}.get(body.get("source"), "Attendance")
    action = f"{kind} {'saved' if res['created'] else 'updated'}"
    detail = (f"{d.isoformat()}: Present {counts['p']} · Absent {counts['x']} · Late {counts['l']} · Excused {counts['e']} · Recited {counts['r']}"
              + (f" · Blank {counts['']}" if counts[""] else ""))
    topic = safe_text(str(body.get("topic", ""))[:120])
    if topic:
        detail += f" · Topic: {topic}"
    if res["created"]:
        absent = [n for n, o, c in res["changes"] if c == "x"]
        if absent:
            detail += " · Absent: " + short_list(absent, 15)
    else:
        diffs = [f"{n} {LETTER[o]}→{LETTER[c]}" for n, o, c in res["changes"] if o != c]
        detail += " · Changed: " + (short_list(diffs, 25) if diffs else "nothing (same as before)")
    if res["added"]:
        detail += " · New students added: " + short_list(res["added"], 15)
    log_change(action, subject, detail)
    return jsonify(ok=True, saved=res["saved"])


@app.errorhandler(413)
def too_big(_e):
    return jsonify(ok=False, error="That photo is too large. Try a smaller one."), 413


@app.route("/scan")
def scan():
    data = load_data()
    subjects, subject = pick_subject(data)
    sd = data[subject] if subject else {"students": [], "dates": []}
    return render_template(
        "scan.html", page="scan", subject=subject, tabs=make_tabs(subjects, subject, "scan"),
        students=[{"name": s["name"], "row": s["row"]} for s in sd["students"]],
        recorded=[x["date"].isoformat() for x in sd["dates"]], today=date.today().isoformat(),
        has_key=bool(get_api_key()), provider=provider_of(get_api_key()) if get_api_key() else "",
        records_url=url_for("records", subject=subject) if subject else "",
        scan_url=url_for("api_scan"), save_url=url_for("api_save"), key_url=url_for("api_set_key"),
        max_images=MAX_IMAGES, pct=int(MEET_PRESENT_PCT * 100))


@app.route("/api/scan", methods=["POST"])
def api_scan():
    """Read photos/screenshots of an attendance record. This only READS: nothing is written to Excel here."""
    data = load_data()
    subject = request.form.get("subject", "")
    files = [f for f in request.files.getlist("image") if f]
    if subject not in data or not files:
        return jsonify(ok=False, error="Choose a subject and at least one photo first."), 400
    if len(files) > MAX_IMAGES:
        return jsonify(ok=False, error=f"Please use at most {MAX_IMAGES} photos at a time."), 400
    images = []
    for f in files:
        raw = f.read(MAX_UPLOAD + 1)
        if not raw or len(raw) > MAX_UPLOAD:
            return jsonify(ok=False, error="One of the photos is empty or too large."), 400
        media = f.mimetype if f.mimetype in ("image/jpeg", "image/png", "image/webp", "image/gif") else "image/jpeg"
        images.append((base64.b64encode(raw).decode("ascii"), media))
    roster = [s["name"] for s in data[subject]["students"]]
    try:
        result = call_ai(images, roster)
    except AIError as err:
        return jsonify(ok=False, code=err.code, error=err.message), (400 if err.code in ("no_key", "bad_key") else 502)
    return jsonify(ok=True, result=normalize_scan(result, roster))


@app.route("/api/set_key", methods=["POST"])
def api_set_key():
    # Only the computer running the site may save the key (the site may be open to the network).
    if request.remote_addr not in ("127.0.0.1", "::1"):
        return jsonify(ok=False, error="For safety, the key can only be saved from the computer that runs the site. "
                                       "Or create a file named api_key.txt next to app.py containing the key."), 403
    key = str((request.get_json(silent=True) or {}).get("key", "")).strip().strip("\"'").strip()
    if not re.fullmatch(r"[A-Za-z0-9_.\-]{30,}", key):
        return jsonify(ok=False, error="That doesn't look like an API key. Paste only the key itself, with no spaces or quotes. "
                                       "A Claude key starts with sk-ant- and a Gemini key starts with AIza or AQ."), 400
    try:
        with open(API_KEY_FILE, "w", encoding="utf-8") as fh:
            fh.write(key)
    except OSError:
        return jsonify(ok=False, error="Could not save the key file in this folder."), 500
    return jsonify(ok=True)


@app.route("/records")
def records():
    data = load_data()
    subjects, subject = pick_subject(data)
    rows, dates = [], []
    if subject:
        sd = data[subject]
        dates = [{"label": x["date"].strftime("%b %d").replace(" 0", " "), "iso": x["date"].isoformat(),
                  "topic": x["topic"]} for x in sd["dates"]]
        for s in student_stats(sd):
            s["codes"] = [sd["cells"].get((s["row"], x["col"]), "") for x in sd["dates"]]
            rows.append(s)
    return render_template("records.html", page="records", subject=subject, rows=rows, dates=dates,
                           low=LOW_RATE, tabs=make_tabs(subjects, subject, "records"))


GRID_COLS = 25               # date columns in the printed grid (blank ones are left for future days)
DATES_PER_PAGE = 23         # date columns on one printed page (more days continue on the next page)
FORM_ROWS = 30              # numbered rows on the printed sheet, like the teacher's form
PRINT_MARK = {"x": "X", "r": "R", "e": "E"}   # everything else (p, l, unmarked) prints blank = present


@app.route("/print")
def print_sheet():
    """A printable copy of the attendance in the teacher's paper-form layout."""
    data = load_data()
    subjects, subject = pick_subject(data)
    if not subject:
        flash("Add a subject first.", "err")
        return redirect(url_for("dashboard"))
    sd = data[subject]
    dates, students, cells = sd["dates"], sd["students"], sd["cells"]
    unmarked = []
    for dd in dates:
        n = sum(1 for s in students if not cells.get((s["row"], dd["col"])))
        if n:
            unmarked.append({"label": f"{dd['date'].month}/{dd['date'].day}", "n": n})
    codes = [cells.get((s["row"], dd["col"]), "") for s in students for dd in dates]
    # Totals only count days that have at least one mark. Like the paper, a blank counts as present.
    held_dates = [dd for dd in dates if any(cells.get((s["row"], dd["col"])) for s in students)]
    skipped = [f"{dd['date'].month}/{dd['date'].day}" for dd in dates if dd not in held_dates]
    held = len(held_dates)
    totals = {}
    for s in students:
        got = [cells.get((s["row"], dd["col"]), "") for dd in held_dates]
        totals[s["row"]] = (f"{held - got.count('x') - got.count('e')}/{held}", got.count("r"))
    pages = []
    if students:
        for i in range(0, max(len(dates), 1), DATES_PER_PAGE):
            chunk = dates[i:i + DATES_PER_PAGE]
            rows = [{"n": n, "name": s["name"], "total": totals[s["row"]][0], "rec": totals[s["row"]][1],
                     "marks": [PRINT_MARK.get(cells.get((s["row"], d["col"]), ""), "") for d in chunk]}
                    for n, s in enumerate(students, 1)]
            for n in range(len(students) + 1, max(FORM_ROWS, len(students)) + 1):
                rows.append({"n": n, "name": "", "total": "", "rec": "", "marks": [""] * len(chunk)})
            pages.append({"rows": rows, "pad": GRID_COLS - len(chunk),
                          "cols": [{"label": f"{d['date'].month}/{d['date'].day}", "topic": d["topic"]} for d in chunk]})
    return render_template("print.html", subject=subject, subjects=subjects, pages=pages,
                           unmarked=unmarked, held=held, skipped=skipped,
                           extra_l=codes.count("l"), extra_e=codes.count("e"))


@app.route("/dates/delete", methods=["POST"])
def dates_delete():
    subject = request.form.get("subject", "")
    d = parse_iso(request.form.get("date", ""))
    if not d:
        flash("That date was not understood.", "err")
        return redirect(url_for("records", subject=subject))
    try:
        ensure_workbook()
        backup_workbook("before_delete_date")
        marks, topic = delete_date(subject, d)
    except ValueError as err:
        flash(str(err), "err")
        return redirect(url_for("records", subject=subject))
    log_change("Date deleted", subject, f"{d.isoformat()}" + (f" ({topic})" if topic else "")
               + f" · {marks} mark(s) removed")
    flash(f"Deleted {d.strftime('%b')} {d.day} from {subject}. A backup copy was saved in the backups folder.", "ok")
    return redirect(url_for("records", subject=subject))


@app.route("/import", methods=["GET", "POST"])
def import_meet():
    data = load_data()
    subjects, subject = pick_subject(data)
    if request.method == "GET" or not subject:       # the upload form lives on the Import (scan) page
        if subject:
            return redirect(url_for("scan", subject=subject))
        return render_template("import.html", page="scan", subject=None, review=None, tabs=None)
    f = request.files.get("csv")
    raw = f.read(MAX_CSV + 1) if f and f.filename else b""
    if not raw:
        flash("Choose the Meet CSV file first.", "err")
        return redirect(url_for("scan", subject=subject))
    if len(raw) > MAX_CSV:
        flash("That file is too big to be a Meet attendance list.", "err")
        return redirect(url_for("scan", subject=subject))
    try:
        meet = parse_meet_csv(raw)
    except ValueError as err:
        flash(str(err), "err")
        return redirect(url_for("scan", subject=subject))
    sd = data[subject]
    roster = [s["name"] for s in sd["students"]]
    tokens = {n: name_tokens(n) for n in roster}
    aliases = read_aliases()
    mapped, unmatched = {}, []
    for name, secs in meet["people"]:
        who = match_roster(name, roster, tokens, aliases)
        if who:
            m = mapped.setdefault(who, {"meet": [], "secs": 0})
            m["meet"].append(name)
            m["secs"] += secs
        else:
            unmatched.append({"meet": name, "secs": secs})
    d = parse_iso(request.form.get("date")) or (meet["created"].date() if meet["created"] else date.today())
    col = next((x["col"] for x in sd["dates"] if x["date"] == d), None)
    students = []
    for s in sd["students"]:
        m = mapped.get(s["name"], {"meet": [], "secs": 0})
        students.append({"row": s["row"], "name": s["name"], "meet": ", ".join(m["meet"]), "secs": m["secs"],
                         "old": sd["cells"].get((s["row"], col), "") if col else ""})
    when = ""
    if meet["created"] and meet["ended"]:
        when = f"{meet['created'].strftime('%I:%M %p').lstrip('0')} to {meet['ended'].strftime('%I:%M %p').lstrip('0')}"
    review = {"subject": subject, "date_iso": d.isoformat(), "date_label": d.strftime("%A, %B ") + str(d.day) + d.strftime(", %Y"),
              "topic": safe_text(request.form.get("topic", ""))[:120], "length": meet["length"],
              "threshold": int(meet["length"] * MEET_PRESENT_PCT), "pct": int(MEET_PRESENT_PCT * 100), "when": when,
              "students": students, "unmatched": unmatched, "existing_date": col is not None,
              "save_url": url_for("api_save"), "alias_url": url_for("api_meet_alias"),
              "records_url": url_for("records", subject=subject)}
    return render_template("import.html", page="scan", subject=subject, review=review, tabs=None)


@app.route("/api/meet_alias", methods=["POST"])
def api_meet_alias():
    body = request.get_json(silent=True) or {}
    items = body.get("aliases")
    if not isinstance(items, list) or len(items) > 200:
        return jsonify(ok=False, error="That request was not understood."), 400
    allnames = {s["name"].lower(): s["name"] for sd in load_data().values() for s in sd["students"]}
    aliases = read_aliases()
    for it in items:
        if not isinstance(it, dict):
            continue
        meet = clean_name(str(it.get("meet", ""))).lower()[:120]
        stu = allnames.get(clean_name(str(it.get("student", ""))).lower())
        if meet and stu:
            aliases[meet] = stu
    write_aliases(aliases)
    return jsonify(ok=True)


@app.route("/students")
def students():
    data = load_data()
    subjects, subject = pick_subject(data)
    rows = student_stats(data[subject]) if subject else []
    subj_img = subject_image_url(subject) if subject else None
    return render_template("students.html", page="students", subjects=subjects, subject=subject,
                           rows=rows, low=LOW_RATE, tabs=make_tabs(subjects, subject, "students"),
                           subject_img_url=subj_img)


@app.route("/students/add", methods=["POST"])
def students_add():
    names = []
    for line in request.form.get("names", "").splitlines():
        n = safe_text(line)
        if n and n.lower() not in [x.lower() for x in names]:
            names.append(n)
    subs = request.form.getlist("subjects")
    if not names or not subs:
        flash("Enter at least one name and tick at least one subject.", "err")
        return redirect(url_for("students", subject=subs[0] if subs else None))
    try:
        added, skipped = add_students(subs, names)
    except ValueError as err:
        flash(str(err), "err")
        return redirect(url_for("students"))
    if added:
        log_change("Students added", ", ".join(subs), short_list(names, 30)
                   + (" · Already on the list: " + short_list(skipped, 10) if skipped else ""))
    msg = f"Added {added} student entr{'y' if added == 1 else 'ies'}."
    if skipped:
        msg += " Already on the list: " + ", ".join(skipped) + "."
    flash(msg, "ok")
    return redirect(url_for("students", subject=subs[0]))


@app.route("/students/remove", methods=["POST"])
def students_remove():
    subject = request.form.get("subject", "")
    name = clean_name(request.form.get("name", ""))
    try:
        row = int(request.form.get("row", ""))
    except ValueError:
        row = None
    everywhere = request.form.get("everywhere") == "1"
    try:
        removed = remove_student(subject, row, name, everywhere)
    except ValueError as err:
        flash(str(err), "err")
        return redirect(url_for("students"))
    if removed:
        log_change("Student removed", "All subjects" if everywhere else subject, name)
    flash(f"Removed {name}." if removed else f"{name} was not found.", "ok" if removed else "err")
    return redirect(url_for("students", subject=subject))



@app.route("/subject_image/<path:subject>")
def subject_image(subject):
    fn = get_subject_image_file(subject)
    if fn:
        return send_file(os.path.join(SUBJECT_IMG_DIR, fn))
    return "Not found", 404


@app.route("/subjects/delete", methods=["POST"])
def subjects_delete():
    name = request.form.get("subject", "").strip()
    try:
        delete_subject(name)
        log_change("Subject deleted", name, "Subject and records removed from Excel")
        flash(f"Deleted subject '{name}'.", "ok")
    except Exception as err:
        flash(str(err), "err")
    return redirect(url_for("students"))


@app.route("/subjects/upload_image", methods=["POST"])
def subjects_upload_image():
    subject = request.form.get("subject", "").strip()
    if not subject:
        flash("No subject selected.", "err")
        return redirect(url_for("students"))
    f = request.files.get("image")
    if not f or not f.filename:
        flash("Please select an image file to upload.", "err")
        return redirect(url_for("students", subject=subject))
    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        flash("Supported formats: JPG, PNG, WebP, GIF.", "err")
        return redirect(url_for("students", subject=subject))
    os.makedirs(SUBJECT_IMG_DIR, exist_ok=True)
    remove_subject_image(subject)
    safe = re.sub(r'[^a-zA-Z0-9_\-]', '_', clean_sheet_name(subject).lower())
    target = os.path.join(SUBJECT_IMG_DIR, f"{safe}{ext}")
    f.save(target)
    log_change("Subject image uploaded", subject, f"Updated image: {safe}{ext}")
    flash(f"Custom picture updated for {subject}!", "ok")
    return redirect(url_for("students", subject=subject))


@app.route("/subjects/delete_image", methods=["POST"])
def subjects_delete_image():
    subject = request.form.get("subject", "").strip()
    remove_subject_image(subject)
    log_change("Subject image removed", subject, "Reset to default")
    flash(f"Custom picture removed for {subject}.", "ok")
    return redirect(url_for("students", subject=subject))


@app.route("/subjects/add", methods=["POST"])
def subjects_add():
    name = clean_sheet_name(request.form.get("name", ""))
    if not name or name.lower() == "guide":
        flash("Please enter a different subject name.", "err")
        return redirect(url_for("students"))
    try:
        n = add_subject(name, request.form.get("copy_from", ""))
    except ValueError as err:
        flash(str(err), "err")
        return redirect(url_for("students"))
    log_change("Subject added", name, f"Copied {n} students from {request.form.get('copy_from')}" if n else "New empty subject")
    flash(f"Created {name}" + (f" with {n} students." if n else "."), "ok")
    return redirect(url_for("students", subject=name))


@app.route("/log")
def log_page():
    shown, total = read_log()
    return render_template("log.html", page="log", shown=shown, total=total)


def human_size(n):
    return f"{n / 1024:.0f} KB" if n < 1024 * 1024 else f"{n / 1024 / 1024:.1f} MB"


@app.route("/files")
def files_page():
    exists = os.path.exists(XLSX)
    size = modified = ""
    if exists:
        st = os.stat(XLSX)
        size = human_size(st.st_size)
        modified = datetime.fromtimestamp(st.st_mtime).strftime("%b %d, %Y %I:%M %p").replace(" 0", " ")
    return render_template("files.html", page="files", xlsx_path=XLSX, folder=os.path.dirname(XLSX),
                           exists=exists, size=size, modified=modified, log_name=os.path.basename(LOG_FILE),
                           is_local=request.remote_addr in ("127.0.0.1", "::1"), open_url=url_for("api_open"))


@app.route("/api/open", methods=["POST"])
def api_open():
    """Open the folder or the file on the PC that runs the site (only when asked from that PC)."""
    if request.remote_addr not in ("127.0.0.1", "::1"):
        return jsonify(ok=False, error="This only works from the computer that runs the site."), 403
    what = (request.get_json(silent=True) or {}).get("what")
    if what not in ("folder", "file"):
        return jsonify(ok=False, error="That request was not understood."), 400
    ensure_workbook()
    target = os.path.dirname(XLSX) if what == "folder" else XLSX
    try:
        if sys.platform.startswith("win"):
            os.startfile(target)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", target])
        else:
            subprocess.Popen(["xdg-open", target])
    except Exception:
        return jsonify(ok=False, error="Windows could not open it. Copy the path and paste it in File Explorer."), 500
    return jsonify(ok=True, message="Opened on this PC." if what == "folder" else "Opening in Excel on this PC…")


@app.route("/download")
def download():
    ensure_workbook()
    return send_file(XLSX, as_attachment=True, download_name="attendance_records.xlsx")


# ---------------------------------------------------------------------- main
def free_port(start):
    for p in range(start, start + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", p)) != 0:
                return p
    return start


def get_local_ip():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"


if __name__ == "__main__":
    ensure_workbook()
    port = free_port(START_PORT)
    lip = get_local_ip()
    local_url = f"http://localhost:{port}"
    mobile_url = f"http://{lip}:{port}"
    print("=" * 60)
    print(" Attendance site is running")
    print(f" Open on this PC:    {local_url}")
    print(f" Open on your phone: {mobile_url}  (connected to same Wi-Fi)")
    print(f" Excel database:     {XLSX}")
    print(" Close this window (or press Ctrl+C) to stop the site.")
    print("=" * 60)
    if "--no-browser" not in sys.argv:
        threading.Timer(1.2, lambda: webbrowser.open(local_url)).start()
    app.run(host=HOST, port=port, debug=False)