"""
Import an Excel attendance workbook into the SQLite database.

    python migrate_excel.py                         # uses attendance_records.xlsx next to the code
    python migrate_excel.py path/to/file.xlsx       # a different workbook
    python migrate_excel.py --replace               # rebuild: the current database is kept as attendance.db.bak

The site also does this automatically the first time it starts with no database, so you only need
this script to re-import. The workbook itself is never modified.
"""
import os
import sys

import db
from config import DB_FILE, XLSX
from excel_io import read_workbook
from store import import_data


def main(argv):
    replace = "--replace" in argv
    paths = [a for a in argv if not a.startswith("--")]
    src = paths[0] if paths else XLSX
    if not os.path.exists(src):
        print(f"Workbook not found: {src}")
        return 1
    if os.path.exists(DB_FILE) and not replace:
        print(f"{DB_FILE} already exists. Use --replace to rebuild it from the workbook "
              "(the current database is saved as attendance.db.bak).")
        return 1
    tmp = DB_FILE + ".new"
    if os.path.exists(tmp):
        os.remove(tmp)
    conn = db.connect(tmp)
    try:
        db.migrate(conn)
        import_data(conn, read_workbook(src))
        conn.commit()
        subjects = conn.execute("SELECT COUNT(*) FROM subjects").fetchone()[0]
        students = conn.execute("SELECT COUNT(*) FROM students").fetchone()[0]
        marks = conn.execute("SELECT COUNT(*) FROM attendance").fetchone()[0]
    finally:
        conn.close()
    if os.path.exists(DB_FILE):
        bak = DB_FILE + ".bak"
        if os.path.exists(bak):
            os.remove(bak)
        os.replace(DB_FILE, bak)
    os.replace(tmp, DB_FILE)
    print(f"Imported {subjects} subject(s), {students} student(s) and {marks} attendance mark(s) into {DB_FILE}.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
