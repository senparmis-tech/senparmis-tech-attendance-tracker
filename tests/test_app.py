"""
Automated tests for the attendance tracker.
Runs against an isolated temporary folder so the real workbook is never touched.
"""
import io
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_tmp = tempfile.mkdtemp(prefix="attendance_test_")
os.environ["ATTENDANCE_DATA_DIR"] = _tmp
os.environ["ATTENDANCE_TEACHER_PASSWORD"] = "teacherpass1"
os.environ["ATTENDANCE_STUDENT_PASSWORD"] = "studentpass1"

import flask_app  # noqa: E402
from openpyxl import load_workbook  # noqa: E402
import db  # noqa: E402
import excel_io  # noqa: E402
import store  # noqa: E402

app = flask_app.app


def _teacher_client():
    c = app.test_client()
    r = c.post("/login", data={"password": "teacherpass1"})
    assert r.status_code == 302
    return c


def test_auth_gate_and_roles():
    anon = app.test_client()
    assert anon.get("/").status_code == 302
    assert "/login" in anon.get("/").headers["Location"]
    assert anon.post("/api/save", json={}).status_code == 401

    stu = app.test_client()
    assert stu.post("/login", data={"password": "studentpass1"}).headers["Location"].endswith("/records")
    assert stu.get("/records").status_code == 200
    assert stu.get("/students").status_code == 302
    assert stu.get("/download").status_code == 302
    assert stu.post("/api/save", json={}).status_code == 403


def test_every_page_and_static_asset_loads():
    c = _teacher_client()
    for path in ["/", "/mark", "/mark?subject=MMW&date=2026-11-10", "/records", "/students",
                 "/scan", "/print", "/log", "/files", "/login"]:
        r = c.get(path)
        assert r.status_code == 200, path
    for asset in ["css/app.css", "css/mark.css", "css/print.css", "js/mark.js", "js/scan.js", "js/import.js"]:
        r = c.get("/static/" + asset)
        assert r.status_code == 200 and len(r.data) > 50, asset


def test_save_attendance_and_database_roundtrip():
    c = _teacher_client()
    r = c.post("/api/save", json={
        "subject": "MMW", "date": "2026-11-10", "topic": "=DangerTopic",
        "marks": [{"row": 0, "name": "Sample Student A", "code": "x"},
                  {"row": 0, "name": "Sample Student B", "code": "r"}],
        "new_students": ["Added Student"],
    })
    assert r.status_code == 200 and r.get_json()["ok"] is True
    sd = store.load_data()["MMW"]
    day = next(d for d in sd["dates"] if d["date"].isoformat() == "2026-11-10")
    assert day["topic"] == "DangerTopic"            # leading '=' stripped against formula injection
    by_name = {s["name"]: sd["cells"].get((s["row"], day["col"]), "") for s in sd["students"]}
    assert by_name["Sample Student A"] == "x" and by_name["Sample Student B"] == "r"
    assert "Added Student" in by_name
    # changing a mark updates it, and clearing removes it
    c.post("/api/save", json={"subject": "MMW", "date": "2026-11-10", "topic": "",
                              "marks": [{"name": "Sample Student A", "code": "p"},
                                        {"name": "Sample Student B", "code": "", "clear": True}]})
    sd = store.load_data()["MMW"]
    by_name = {s["name"]: sd["cells"].get((s["row"], day["col"]), "") for s in sd["students"]}
    assert by_name["Sample Student A"] == "p" and by_name["Sample Student B"] == ""
    assert c.post("/api/save", json={"subject": "Nope", "date": "2026-11-10", "marks": []}).status_code == 400


def test_excel_export_and_import_roundtrip():
    c = _teacher_client()
    r = c.get("/download")
    assert r.status_code == 200 and r.data[:2] == b"PK"
    wb = load_workbook(io.BytesIO(r.data))
    assert "MMW" in wb.sheetnames
    # import the exported workbook into a brand-new database and compare
    path = os.path.join(_tmp, "roundtrip.xlsx")
    wb.save(path)
    original = store.load_data()
    fresh = os.path.join(_tmp, "fresh.db")
    conn = db.connect(fresh)
    db.migrate(conn)
    store.import_data(conn, excel_io.read_workbook(path))
    conn.commit()
    conn.close()
    conn = db.connect(fresh)
    n_students = conn.execute("SELECT COUNT(*) FROM students").fetchone()[0]
    n_marks = conn.execute("SELECT COUNT(*) FROM attendance").fetchone()[0]
    conn.close()
    assert n_students == len({s["name"].casefold() for sd in original.values() for s in sd["students"]})
    assert n_marks == sum(len(sd["cells"]) for sd in original.values())


def test_backup_is_a_valid_database():
    store.backup_latest()
    from config import BACKUP_DIR
    conn = db.connect(os.path.join(BACKUP_DIR, "attendance_LATEST.db"))
    assert conn.execute("SELECT COUNT(*) FROM subjects").fetchone()[0] >= 1
    conn.close()


def test_students_subjects_and_meet_import():
    c = _teacher_client()
    assert c.post("/students/add", data={"names": "Maria Santos", "subjects": ["MMW"]}).status_code == 302
    assert c.post("/subjects/add", data={"name": "Physics", "copy_from": "MMW"}).status_code == 302
    csv_bytes = ("Created on 2026-11-08 09:00:00\nEnded on 2026-11-08 10:00:00\n\n"
                 "Full Name,Time in Call\nMaria Santos,50:00\n").encode()
    r = c.post("/import", data={"subject": "MMW", "csv": (io.BytesIO(csv_bytes), "m.csv")},
               content_type="multipart/form-data")
    assert r.status_code == 200 and b"Maria Santos" in r.data
    assert c.post("/dates/delete", data={"subject": "MMW", "date": "2026-11-10"}).status_code == 302
    assert c.post("/subjects/delete", data={"subject": "Physics"}).status_code == 302


def test_cross_origin_post_blocked():
    c = _teacher_client()
    r = c.post("/api/save", json={}, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403


def test_dark_mode_toggle_and_css_present():
    c = _teacher_client()
    html = c.get("/").get_data(as_text=True)
    assert 'id="themeToggleBtn"' in html
    assert "data-theme" in html
    css = c.get("/static/css/app.css").get_data(as_text=True)
    assert '[data-theme="dark"]' in css


def test_student_lookup():
    c = _teacher_client()
    r = c.get("/lookup?q=sample student a")
    assert r.status_code == 200
    assert b"Sample Student A" in r.data
    assert b"Print slip" in r.data
    assert b"No student matches" in c.get("/lookup?q=zzzz").data
    stu = app.test_client()
    stu.post("/login", data={"password": "studentpass1"})
    assert stu.get("/lookup").status_code == 302


def test_per_teacher_accounts_and_subject_isolation():
    admin = _teacher_client()
    assert admin.get("/teachers").status_code == 200
    r = admin.post("/teachers/add", data={
        "username": "msantos", "display_name": "Prof. Santos", "password": "santospassword1",
    })
    assert r.status_code == 302
    teachers = store.list_teachers()
    santos = next(t for t in teachers if t["username"] == "msantos")
    assert not santos["is_admin"]

    # Assign MMW to Prof. Santos; College Algebra remains unassigned (admin-only when signed in as non-admin)
    assert admin.post("/teachers/assign_subject",
                      data={"subject": "MMW", "teacher_id": str(santos["id"])}).status_code == 302

    # Sign in as Prof. Santos
    tc = app.test_client()
    r = tc.post("/login", data={"username": "msantos", "password": "santospassword1"})
    assert r.status_code == 302 and r.headers["Location"].endswith("/")
    dash = tc.get("/").get_data(as_text=True)
    assert "MMW" in dash
    assert "College Algebra" not in dash

    # Non-admin teacher cannot modify an unassigned / other teacher's subject
    r_forbid = tc.post("/api/save", json={
        "subject": "College Algebra", "date": "2026-11-11", "topic": "Forbidden",
        "marks": [{"name": "Sample Student A", "code": "p"}],
    })
    assert r_forbid.status_code == 400

    # Non-admin teacher can create their own subject and it is automatically owned by them
    assert tc.post("/subjects/add", data={"name": "Data Structures", "copy_from": "MMW"}).status_code == 302
    assert "Data Structures" in tc.get("/").get_data(as_text=True)

    # Non-admin cannot create another teacher account
    tc.post("/teachers/add", data={"username": "hacker", "password": "hackerpassword1"})
    assert not any(t["username"] == "hacker" for t in store.list_teachers())

    # Clean up test subject and teacher
    assert admin.post("/subjects/delete", data={"subject": "Data Structures"}).status_code == 302
    assert admin.post("/teachers/delete", data={"teacher_id": str(santos["id"])}).status_code == 302

