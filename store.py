"""
Attendance data access on top of SQLite. Replaces the old Excel-backed excel_store.

``load_data()`` returns the same shape the pages already use:
    {subject: {"students": [{"row", "name"}], "dates": [{"col", "date", "topic"}],
               "cells": {(row, col): code}}}
where ``row`` is an enrollment id and ``col`` is a class-session id.
"""
import os
import re
import sqlite3
import threading
import time
from datetime import date, datetime

from flask import g, has_request_context, url_for
from werkzeug.security import check_password_hash, generate_password_hash

import db
from config import (BACKUP_DIR, BACKUP_EVERY_MIN, BACKUP_KEEP, DB_FILE,
                    MIN_PASSWORD, SAMPLE_STUDENTS, SAMPLE_SUBJECTS,
                    SUBJECT_IMG_DIR, XLSX)
from helpers import clean_name, clean_sheet_name, norm_code, safe_text

write_lock = threading.RLock()
_init_lock = threading.Lock()


class FileLocked(Exception):
    """The database is busy (another program is writing to it)."""


def key_of(name):
    return clean_name(name).casefold()


# ------------------------------------------------------------------ set-up
def _current_teacher_filter():
    """Return (teacher_id, is_admin) from Flask request context if a non-admin teacher is logged in."""
    if has_request_context():
        tid = getattr(g, "teacher_id", None)
        is_adm = getattr(g, "is_admin", True)
        return tid, bool(is_adm)
    return None, True


def _insert_subject(conn, name, teacher_id=None):
    pos = conn.execute("SELECT COALESCE(MAX(position), 0) + 1 FROM subjects").fetchone()[0]
    sid = conn.execute("INSERT INTO subjects (name, position, teacher_id) VALUES (?, ?, ?)",
                       (name, pos, teacher_id)).lastrowid
    return conn.execute("INSERT INTO sections (subject_id, name) VALUES (?, 'Main')", (sid,)).lastrowid


def _student_id(conn, name):
    """Find a student by name (case-insensitive) or create them."""
    k = key_of(name)
    row = conn.execute("SELECT id FROM students WHERE name_key = ?", (k,)).fetchone()
    if row:
        return row["id"]
    return conn.execute("INSERT INTO students (name, name_key) VALUES (?, ?)", (clean_name(name), k)).lastrowid


def _enroll(conn, student_id, section_id):
    """Enroll a student; returns the enrollment id, or None if they were already enrolled."""
    cur = conn.execute("INSERT OR IGNORE INTO enrollments (student_id, section_id) VALUES (?, ?)",
                       (student_id, section_id))
    return cur.lastrowid if cur.rowcount else None


def import_data(conn, data):
    """Load {subject: {students, dates, cells}} (as read from Excel) into an empty database."""
    for subject, sd in data.items():
        section = _insert_subject(conn, subject)
        enr = {}
        for s in sd["students"]:
            eid = _enroll(conn, _student_id(conn, s["name"]), section)
            if eid:
                enr[s["row"]] = eid
        for dd in sd["dates"]:
            iso = dd["date"].isoformat()
            if conn.execute("SELECT 1 FROM sessions WHERE section_id = ? AND date = ?", (section, iso)).fetchone():
                continue
            sess = conn.execute("INSERT INTO sessions (section_id, date, topic) VALUES (?, ?, ?)",
                                (section, iso, dd["topic"] or None)).lastrowid
            for row, eid in enr.items():
                code = sd["cells"].get((row, dd["col"]))
                if code:
                    conn.execute("INSERT INTO attendance (enrollment_id, session_id, code) VALUES (?, ?, ?)",
                                 (eid, sess, code))


def _seed_samples(conn):
    for subject in SAMPLE_SUBJECTS:
        section = _insert_subject(conn, subject)
        for name in SAMPLE_STUDENTS:
            _enroll(conn, _student_id(conn, name), section)


def ensure_db():
    """Create the database on first run. If an old Excel workbook exists, import it (it is never changed)."""
    if os.path.exists(DB_FILE):
        conn = db.connect()
        try:
            db.migrate(conn)
        finally:
            conn.close()
        return
    with _init_lock:
        if os.path.exists(DB_FILE):
            return
        tmp = DB_FILE + ".new"
        if os.path.exists(tmp):
            os.remove(tmp)
        conn = db.connect(tmp)
        try:
            db.migrate(conn)
            if os.path.exists(XLSX):
                from excel_io import read_workbook
                import_data(conn, read_workbook(XLSX))
            else:
                _seed_samples(conn)
            conn.commit()
        finally:
            conn.close()
        os.replace(tmp, DB_FILE)


class _Tx:
    def __init__(self):
        ensure_db()
        self.conn = db.connect()

    def __enter__(self):
        return self.conn

    def __exit__(self, exc_type, exc, tb):
        try:
            if exc_type is None:
                self.conn.commit()
            else:
                self.conn.rollback()
        finally:
            self.conn.close()
        if exc_type is sqlite3.OperationalError and "locked" in str(exc).lower():
            raise FileLocked() from exc
        return False


# ------------------------------------------------------------ reading data
def _section_of(conn, subject):
    tid, is_adm = _current_teacher_filter()
    row = conn.execute(
        "SELECT sec.id, s.teacher_id FROM sections sec JOIN subjects s ON s.id = sec.subject_id "
        "WHERE s.name = ? ORDER BY sec.id LIMIT 1", (subject,)).fetchone()
    if not row:
        raise ValueError("That subject was not found.")
    if not is_adm and tid is not None and row["teacher_id"] != tid:
        raise ValueError("You do not have permission to modify that subject.")
    return row["id"]


def load_data(teacher_id=None, is_admin=None):
    if teacher_id is None and is_admin is None:
        teacher_id, is_admin = _current_teacher_filter()
    with _Tx() as conn:
        out = {}
        if not is_admin and teacher_id is not None:
            subjects = conn.execute(
                "SELECT s.name, (SELECT MIN(id) FROM sections WHERE subject_id = s.id) AS section_id "
                "FROM subjects s WHERE s.teacher_id = ? ORDER BY s.position, s.id", (teacher_id,)).fetchall()
        else:
            subjects = conn.execute(
                "SELECT s.name, (SELECT MIN(id) FROM sections WHERE subject_id = s.id) AS section_id "
                "FROM subjects s ORDER BY s.position, s.id").fetchall()
        for sub in subjects:
            sec = sub["section_id"]
            students = [{"row": r["id"], "name": r["name"]} for r in conn.execute(
                "SELECT e.id, st.name FROM enrollments e JOIN students st ON st.id = e.student_id "
                "WHERE e.section_id = ? ORDER BY e.id", (sec,))]
            dates = [{"col": r["id"], "date": date.fromisoformat(r["date"]), "topic": r["topic"] or ""}
                     for r in conn.execute("SELECT id, date, topic FROM sessions WHERE section_id = ? ORDER BY date", (sec,))]
            cells = {(r["enrollment_id"], r["session_id"]): r["code"] for r in conn.execute(
                "SELECT a.enrollment_id, a.session_id, a.code FROM attendance a "
                "JOIN sessions se ON se.id = a.session_id WHERE se.section_id = ?", (sec,))}
            out[sub["name"]] = {"students": students, "dates": dates, "cells": cells}
        return out


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


# ------------------------------------------------------------ backups
def backup_workbook(tag, min_gap_min=0):
    """Save a timestamped copy of the database in the backups folder. Never blocks the action."""
    try:
        if not os.path.exists(DB_FILE):
            return
        os.makedirs(BACKUP_DIR, exist_ok=True)
        prefix = f"attendance_{tag}_"
        mine = sorted(f for f in os.listdir(BACKUP_DIR) if f.startswith(prefix) and f.endswith(".db"))
        if min_gap_min and mine:
            if time.time() - os.path.getmtime(os.path.join(BACKUP_DIR, mine[-1])) < min_gap_min * 60:
                return
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        _copy_db(os.path.join(BACKUP_DIR, f"{prefix}{stamp}.db"))
        mine = sorted(f for f in os.listdir(BACKUP_DIR) if f.startswith(prefix) and f.endswith(".db"))
        for old in mine[:-BACKUP_KEEP.get(tag, 30)]:
            os.remove(os.path.join(BACKUP_DIR, old))
    except (OSError, sqlite3.Error):
        pass


def backup_latest():
    """Keep one always-up-to-date copy (attendance_LATEST.db) next to the history copies."""
    try:
        os.makedirs(BACKUP_DIR, exist_ok=True)
        _copy_db(os.path.join(BACKUP_DIR, "attendance_LATEST.db"))
    except (OSError, sqlite3.Error):
        pass


def _copy_db(target):
    src = sqlite3.connect(DB_FILE)
    dst = sqlite3.connect(target)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()


def mutate(fn):
    """Run ``fn(conn)`` as one all-or-nothing change, with backups around it."""
    ensure_db()
    with write_lock:
        backup_workbook("auto", BACKUP_EVERY_MIN)
        with _Tx() as conn:
            result = fn(conn)
        backup_latest()
        return result


# ------------------------------------------------------------ writing data
def apply_marks(subject, d, topic, items, new_names=()):
    def run(conn):
        sec = _section_of(conn, subject)
        iso = d.isoformat()
        row = conn.execute("SELECT id FROM sessions WHERE section_id = ? AND date = ?", (sec, iso)).fetchone()
        created = row is None
        topic_clean = safe_text(topic) or None
        if created:
            sess = conn.execute("INSERT INTO sessions (section_id, date, topic) VALUES (?, ?, ?)",
                                (sec, iso, topic_clean)).lastrowid
        else:
            sess = row["id"]
            conn.execute("UPDATE sessions SET topic = ? WHERE id = ?", (topic_clean, sess))
        names = {}                                   # lowercase name -> enrollment id
        for r in conn.execute("SELECT e.id, st.name FROM enrollments e JOIN students st ON st.id = e.student_id "
                              "WHERE e.section_id = ?", (sec,)):
            names[key_of(r["name"])] = r["id"]
        added = []
        for n in new_names:                          # students added from a scanned sheet
            n = safe_text(n)
            if n and key_of(n) not in names:
                names[key_of(n)] = _enroll(conn, _student_id(conn, n), sec)
                added.append(n)
        saved, changes = 0, []
        for it in items:
            name = clean_name(str(it.get("name", "")))
            raw_code = it.get("code")
            code = norm_code(raw_code)
            clearing = (not code) and raw_code in ("", None) and bool(it.get("clear"))
            if not name or (not code and not clearing):
                continue
            eid = None
            rid = it.get("row")
            if isinstance(rid, int):                 # trust the row only if it is this student in this subject
                hit = conn.execute("SELECT st.name FROM enrollments e JOIN students st ON st.id = e.student_id "
                                   "WHERE e.id = ? AND e.section_id = ?", (rid, sec)).fetchone()
                if hit and key_of(hit["name"]) == key_of(name):
                    eid = rid
            if eid is None:
                eid = names.get(key_of(name))
            if not eid:
                continue
            old_row = conn.execute("SELECT code FROM attendance WHERE enrollment_id = ? AND session_id = ?",
                                   (eid, sess)).fetchone()
            old = old_row["code"] if old_row else ""
            if code:
                conn.execute("INSERT INTO attendance (enrollment_id, session_id, code) VALUES (?, ?, ?) "
                             "ON CONFLICT (enrollment_id, session_id) DO UPDATE SET code = excluded.code",
                             (eid, sess, code))
            else:
                conn.execute("DELETE FROM attendance WHERE enrollment_id = ? AND session_id = ?", (eid, sess))
            changes.append((name, old, code))
            saved += 1
        return {"saved": saved, "created": created, "changes": changes, "added": added}
    return mutate(run)


def delete_date(subject, d):
    """Remove one class date (topic and every mark) from a subject."""
    def run(conn):
        sec = _section_of(conn, subject)
        row = conn.execute("SELECT id, topic FROM sessions WHERE section_id = ? AND date = ?",
                           (sec, d.isoformat())).fetchone()
        if not row:
            raise ValueError("That date was not found.")
        marks = conn.execute("SELECT COUNT(*) FROM attendance WHERE session_id = ?", (row["id"],)).fetchone()[0]
        conn.execute("DELETE FROM sessions WHERE id = ?", (row["id"],))
        return marks, clean_name(row["topic"] or "")
    return mutate(run)


def add_students(subjects, names):
    def run(conn):
        added, skipped = 0, []
        for sub in subjects:
            sec = _section_of(conn, sub)
            for n in names:
                if _enroll(conn, _student_id(conn, n), sec):
                    added += 1
                else:
                    skipped.append(f"{n} ({sub})")
        return added, skipped
    return mutate(run)


def remove_student(subject, row, name, everywhere):
    def run(conn):
        targets = [r["name"] for r in conn.execute("SELECT name FROM subjects")] if everywhere else [subject]
        removed = 0
        for sub in targets:
            sec = _section_of(conn, sub)
            hit = None
            if not everywhere and isinstance(row, int):
                r = conn.execute("SELECT e.id, st.name FROM enrollments e JOIN students st ON st.id = e.student_id "
                                 "WHERE e.id = ? AND e.section_id = ?", (row, sec)).fetchone()
                if r and key_of(r["name"]) == key_of(name):
                    hit = r["id"]
            if hit is None:
                r = conn.execute("SELECT e.id FROM enrollments e JOIN students st ON st.id = e.student_id "
                                 "WHERE e.section_id = ? AND st.name_key = ?", (sec, key_of(name))).fetchone()
                hit = r["id"] if r else None
            if hit:
                conn.execute("DELETE FROM enrollments WHERE id = ?", (hit,))
                removed += 1
        conn.execute("DELETE FROM students WHERE id NOT IN (SELECT student_id FROM enrollments)")
        return removed
    return mutate(run)


# -------------------------------------------------------- subject customization
def _img_stem(subject):
    return re.sub(r'[^a-zA-Z0-9_\-]', '_', clean_sheet_name(subject).lower())


def get_subject_image_file(subject):
    if not os.path.exists(SUBJECT_IMG_DIR):
        return None
    for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        fn = f"{_img_stem(subject)}{ext}"
        if os.path.isfile(os.path.join(SUBJECT_IMG_DIR, fn)):
            return fn
    return None


def subject_image_url(subject):
    img = get_subject_image_file(subject)
    return url_for("subject_image", subject=subject) if img else None


def remove_subject_image(subject):
    if not os.path.exists(SUBJECT_IMG_DIR):
        return
    for ext in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        p = os.path.join(SUBJECT_IMG_DIR, f"{_img_stem(subject)}{ext}")
        if os.path.isfile(p):
            try:
                os.remove(p)
            except OSError:
                pass


def delete_subject(name):
    def run(conn):
        tid, is_adm = _current_teacher_filter()
        row = conn.execute("SELECT id, teacher_id FROM subjects WHERE name = ?", (name,)).fetchone()
        if not row:
            raise ValueError("That subject was not found.")
        if not is_adm and tid is not None and row["teacher_id"] != tid:
            raise ValueError("You do not have permission to delete that subject.")
        conn.execute("DELETE FROM subjects WHERE id = ?", (row["id"],))
        conn.execute("DELETE FROM students WHERE id NOT IN (SELECT student_id FROM enrollments)")
    mutate(run)
    remove_subject_image(name)


def add_subject(name, copy_from, teacher_id=None):
    def run(conn):
        tid, is_adm = _current_teacher_filter()
        owner = teacher_id if is_adm else (tid or teacher_id)
        if conn.execute("SELECT 1 FROM subjects WHERE name = ?", (name,)).fetchone():
            raise ValueError("A subject with that name already exists.")
        source = []
        if copy_from and conn.execute("SELECT 1 FROM subjects WHERE name = ?", (copy_from,)).fetchone():
            src = _section_of(conn, copy_from)
            source = [r["student_id"] for r in conn.execute(
                "SELECT student_id FROM enrollments WHERE section_id = ? ORDER BY id", (src,))]
        sec = _insert_subject(conn, name, owner)
        for sid in source:
            _enroll(conn, sid, sec)
        return len(source)
    return mutate(run)


# -------------------------------------------------------- teacher accounts
def list_teachers():
    with _Tx() as conn:
        rows = conn.execute(
            "SELECT t.id, t.username, t.display_name, t.is_admin, t.created_at, "
            "(SELECT COUNT(*) FROM subjects s WHERE s.teacher_id = t.id) AS n_subjects "
            "FROM teachers t ORDER BY t.is_admin DESC, t.display_name, t.username").fetchall()
        return [dict(r) for r in rows]


def get_teacher(teacher_id):
    with _Tx() as conn:
        row = conn.execute("SELECT id, username, display_name, password_hash, is_admin FROM teachers WHERE id = ?",
                           (teacher_id,)).fetchone()
        return dict(row) if row else None


def verify_teacher(username_or_pw, password=None):
    """Verify a teacher by (username, password), or if username is blank, check password against all teachers."""
    with _Tx() as conn:
        if password is not None and username_or_pw:
            row = conn.execute("SELECT id, username, display_name, password_hash, is_admin FROM teachers "
                               "WHERE username = ?", (username_or_pw.strip(),)).fetchone()
            if row and check_password_hash(row["password_hash"], password):
                return dict(row)
            return None
        pw = password if password is not None else username_or_pw
        for row in conn.execute("SELECT id, username, display_name, password_hash, is_admin FROM teachers"):
            if check_password_hash(row["password_hash"], pw):
                return dict(row)
        return None


def create_teacher(username, display_name, password, is_admin=False):
    uname = re.sub(r"[^a-zA-Z0-9_.\-]", "", (username or "").strip()).lower()
    dname = clean_name(display_name or uname)
    if not uname or len(uname) < 2:
        raise ValueError("Username must be at least 2 characters (letters, numbers, _, ., -).")
    if not password or len(password) < MIN_PASSWORD:
        raise ValueError(f"Password must be at least {MIN_PASSWORD} characters.")
    pw_hash = generate_password_hash(password)

    def run(conn):
        if conn.execute("SELECT 1 FROM teachers WHERE username = ?", (uname,)).fetchone():
            raise ValueError("That username is already taken.")
        return conn.execute(
            "INSERT INTO teachers (username, display_name, password_hash, is_admin) VALUES (?, ?, ?, ?)",
            (uname, dname, pw_hash, 1 if is_admin else 0)).lastrowid
    return mutate(run)


def update_teacher_password(teacher_id, new_password):
    if not new_password or len(new_password) < MIN_PASSWORD:
        raise ValueError(f"Password must be at least {MIN_PASSWORD} characters.")
    pw_hash = generate_password_hash(new_password)

    def run(conn):
        cur = conn.execute("UPDATE teachers SET password_hash = ? WHERE id = ?", (pw_hash, int(teacher_id)))
        if not cur.rowcount:
            raise ValueError("Teacher account not found.")
    mutate(run)


def delete_teacher(teacher_id):
    def run(conn):
        row = conn.execute("SELECT is_admin FROM teachers WHERE id = ?", (int(teacher_id),)).fetchone()
        if not row:
            raise ValueError("Teacher account not found.")
        if row["is_admin"]:
            admins = conn.execute("SELECT COUNT(*) FROM teachers WHERE is_admin = 1").fetchone()[0]
            if admins <= 1:
                raise ValueError("Cannot delete the last admin account.")
        conn.execute("DELETE FROM teachers WHERE id = ?", (int(teacher_id),))
    mutate(run)


def list_subjects_with_owners():
    with _Tx() as conn:
        rows = conn.execute(
            "SELECT s.id, s.name, s.teacher_id, t.username AS teacher_username, t.display_name AS teacher_name "
            "FROM subjects s LEFT JOIN teachers t ON t.id = s.teacher_id ORDER BY s.position, s.id").fetchall()
        return [dict(r) for r in rows]


def assign_subject_teacher(subject_name, teacher_id):
    def run(conn):
        tid = int(teacher_id) if teacher_id not in (None, "", "0", 0) else None
        if tid is not None and not conn.execute("SELECT 1 FROM teachers WHERE id = ?", (tid,)).fetchone():
            raise ValueError("Selected teacher does not exist.")
        cur = conn.execute("UPDATE subjects SET teacher_id = ? WHERE name = ?", (tid, subject_name))
        if not cur.rowcount:
            raise ValueError("Subject not found.")
    mutate(run)

