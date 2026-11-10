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
from config import XLSX  # noqa: E402

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


def test_save_attendance_and_excel_roundtrip():
    c = _teacher_client()
    r = c.post("/api/save", json={
        "subject": "MMW", "date": "2026-11-10", "topic": "=DangerTopic",
        "marks": [{"row": 5, "name": "Sample Student A", "code": "x"},
                  {"row": 6, "name": "Sample Student B", "code": "r"}],
        "new_students": ["Added Student"],
    })
    assert r.status_code == 200 and r.get_json()["ok"] is True
    wb = load_workbook(XLSX)
    ws = wb["MMW"]
    assert ws.cell(3, 8).value == "DangerTopic"     # leading '=' stripped against formula injection
    assert ws.cell(5, 8).value == "x"
    assert ws.cell(6, 8).value == "r"


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
