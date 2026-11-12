"""
Small text/date helpers and the JSONL changes log.
"""
import json
import re
import threading
from datetime import date, datetime

from flask import request

from config import CODES, LOG_FILE, LOG_MAX_SHOWN

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
    from flask import g, has_request_context
    ip = (request.remote_addr or "") if has_request_context() else ""
    base = "This PC" if ip in ("127.0.0.1", "::1") else (ip or "unknown")
    if has_request_context() and getattr(g, "teacher_name", None):
        return f"{g.teacher_name} ({base})"
    return base


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
