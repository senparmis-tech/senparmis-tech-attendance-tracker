"""
Google Meet attendance CSV parser and class-list name matcher.
"""
import csv
import difflib
import io
import json
import re
import unicodedata
from datetime import datetime

from config import MEET_ALIAS_FILE
from excel_store import write_lock
from helpers import clean_name

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
