"""
SQLite connection helpers and schema migrations.

The schema version is kept in ``PRAGMA user_version``. To change the schema later, append a new
script to ``MIGRATIONS``; existing databases are upgraded automatically the next time the site starts.
"""
import sqlite3

from config import DB_FILE

MIGRATIONS = [
    # 1: attendance core. A subject has one or more sections; students are shared across subjects.
    """
    CREATE TABLE subjects (
        id       INTEGER PRIMARY KEY,
        name     TEXT NOT NULL UNIQUE COLLATE NOCASE,
        position INTEGER NOT NULL DEFAULT 0
    );
    CREATE TABLE sections (
        id         INTEGER PRIMARY KEY,
        subject_id INTEGER NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
        name       TEXT NOT NULL DEFAULT 'Main',
        UNIQUE (subject_id, name)
    );
    CREATE TABLE students (
        id       INTEGER PRIMARY KEY,
        name     TEXT NOT NULL,
        name_key TEXT NOT NULL UNIQUE
    );
    CREATE TABLE enrollments (
        id         INTEGER PRIMARY KEY,
        student_id INTEGER NOT NULL REFERENCES students(id) ON DELETE CASCADE,
        section_id INTEGER NOT NULL REFERENCES sections(id) ON DELETE CASCADE,
        UNIQUE (student_id, section_id)
    );
    CREATE TABLE sessions (
        id         INTEGER PRIMARY KEY,
        section_id INTEGER NOT NULL REFERENCES sections(id) ON DELETE CASCADE,
        date       TEXT NOT NULL,
        topic      TEXT,
        UNIQUE (section_id, date)
    );
    CREATE TABLE attendance (
        enrollment_id INTEGER NOT NULL REFERENCES enrollments(id) ON DELETE CASCADE,
        session_id    INTEGER NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
        code          TEXT NOT NULL CHECK (code IN ('p', 'x', 'l', 'e', 'r')),
        PRIMARY KEY (enrollment_id, session_id)
    );
    CREATE INDEX idx_enrollments_section ON enrollments(section_id);
    CREATE INDEX idx_sessions_section ON sessions(section_id);
    CREATE INDEX idx_attendance_session ON attendance(session_id);
    """,
    # 2: per-teacher accounts and subject ownership.
    """
    CREATE TABLE teachers (
        id            INTEGER PRIMARY KEY,
        username      TEXT NOT NULL UNIQUE COLLATE NOCASE,
        display_name  TEXT NOT NULL,
        password_hash TEXT NOT NULL,
        is_admin      INTEGER NOT NULL DEFAULT 0,
        created_at    TEXT NOT NULL DEFAULT (datetime('now'))
    );
    ALTER TABLE subjects ADD COLUMN teacher_id INTEGER REFERENCES teachers(id) ON DELETE SET NULL;
    CREATE INDEX idx_subjects_teacher ON subjects(teacher_id);
    """,
    # 3: rename legacy 'Main' sections to 'BSCS-1A'.
    """
    UPDATE sections SET name = 'BSCS-1A'
    WHERE name = 'Main'
      AND NOT EXISTS (
        SELECT 1 FROM sections s2
        WHERE s2.subject_id = sections.subject_id AND s2.name = 'BSCS-1A'
      );
    """,
    # 4: student profile fields (student number, guardian, contact, email, address).
    """
    ALTER TABLE students ADD COLUMN student_no TEXT DEFAULT '';
    ALTER TABLE students ADD COLUMN guardian_name TEXT DEFAULT '';
    ALTER TABLE students ADD COLUMN guardian_phone TEXT DEFAULT '';
    ALTER TABLE students ADD COLUMN email TEXT DEFAULT '';
    ALTER TABLE students ADD COLUMN address TEXT DEFAULT '';
    """,
    # 5: grades (exam, quiz, activity), category weights, and weight lock per section.
    """
    ALTER TABLE sections ADD COLUMN exam_weight REAL NOT NULL DEFAULT 50.0;
    ALTER TABLE sections ADD COLUMN quiz_weight REAL NOT NULL DEFAULT 30.0;
    ALTER TABLE sections ADD COLUMN activity_weight REAL NOT NULL DEFAULT 20.0;
    ALTER TABLE sections ADD COLUMN weights_locked INTEGER NOT NULL DEFAULT 0;
    CREATE TABLE grade_items (
        id         INTEGER PRIMARY KEY,
        section_id INTEGER NOT NULL REFERENCES sections(id) ON DELETE CASCADE,
        category   TEXT NOT NULL CHECK (category IN ('exam', 'quiz', 'activity')),
        title      TEXT NOT NULL,
        max_score  REAL NOT NULL CHECK (max_score > 0),
        date       TEXT DEFAULT ''
    );
    CREATE TABLE grades (
        grade_item_id INTEGER NOT NULL REFERENCES grade_items(id) ON DELETE CASCADE,
        enrollment_id INTEGER NOT NULL REFERENCES enrollments(id) ON DELETE CASCADE,
        score         REAL NOT NULL,
        PRIMARY KEY (grade_item_id, enrollment_id)
    );
    CREATE INDEX idx_grade_items_section ON grade_items(section_id);
    CREATE INDEX idx_grades_enrollment ON grades(enrollment_id);
    """,
]


def connect(path=None):
    conn = sqlite3.connect(path or DB_FILE, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def migrate(conn):
    """Bring a database up to the newest schema version."""
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    for n, script in enumerate(MIGRATIONS, start=1):
        if n > version:
            conn.executescript(script)
            conn.execute(f"PRAGMA user_version = {n}")
            conn.commit()
