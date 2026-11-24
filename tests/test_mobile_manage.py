"""Tests for the JSON endpoints the Android app uses to manage students, grades, terms and accounts."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("ATTENDANCE_DATA_DIR", tempfile.mkdtemp(prefix="attendance_test_"))
os.environ.setdefault("ATTENDANCE_TEACHER_PASSWORD", "teacherpass1")
os.environ.setdefault("ATTENDANCE_STUDENT_PASSWORD", "studentpass1")

import flask_app  # noqa: E402

app = flask_app.app


def _teacher():
    c = app.test_client()
    assert c.post("/api/login", json={"password": "teacherpass1"}).status_code == 200
    return c


def test_students_and_sections_api():
    c = _teacher()
    assert c.post("/api/subject_add", json={"name": "Mob 101", "section_name": "M1"}).get_json()["ok"]
    r = c.post("/api/students_add", json={"subject": "Mob 101", "section": "M1", "names": ["Ana Cruz", "Ben Lee"]})
    assert r.get_json()["added"] == 2
    s = c.get("/api/students?subject=Mob+101&section=M1").get_json()
    assert [x["name"] for x in s["rows"]] == ["Ana Cruz", "Ben Lee"]
    r = c.post("/api/student_profile", json={"old_name": "Ana Cruz", "name": "Ana Cruz", "student_no": "2026-1",
                                              "guardian_name": "Mrs Cruz", "subject": "Mob 101"})
    assert r.get_json()["ok"]
    s = c.get("/api/students?subject=Mob+101&section=M1").get_json()
    assert s["rows"][0]["student_no"] == "2026-1"
    assert c.post("/api/section_add", json={"subject": "Mob 101", "section": "M2"}).get_json()["ok"]
    assert c.post("/api/section_rename", json={"subject": "Mob 101", "old_section": "M2", "new_section": "M3"}).get_json()["ok"]
    assert c.post("/api/section_delete", json={"subject": "Mob 101", "section": "M3"}).get_json()["ok"]
    r = c.post("/api/students_remove", json={"subject": "Mob 101", "section": "M1", "name": "Ben Lee"})
    assert r.get_json()["ok"]
    assert c.post("/api/subject_delete", json={"subject": "Mob 101"}).get_json()["ok"]


def test_grade_setup_and_terms_api():
    c = _teacher()
    c.post("/api/subject_add", json={"name": "Mob 202", "section_name": "M1"})
    c.post("/api/students_add", json={"subject": "Mob 202", "section": "M1", "names": ["Cy Dee"]})
    bad = c.post("/api/grade_weights", json={"subject": "Mob 202", "section": "M1", "exam": 60, "quiz": 60, "activity": 10})
    assert bad.status_code == 400 and not bad.get_json()["ok"]
    ok = c.post("/api/grade_weights", json={"subject": "Mob 202", "section": "M1", "exam": 40, "quiz": 40, "activity": 20})
    assert ok.get_json()["ok"]
    assert c.post("/api/grade_item_add", json={"subject": "Mob 202", "section": "M1", "category": "quiz",
                                                "title": "Q1", "max_score": 20}).get_json()["ok"]
    gb = c.get("/api/grades?subject=Mob+202&section=M1").get_json()
    assert gb["weights"]["exam"] == 40.0 and gb["items"][0]["title"] == "Q1"
    p = c.get("/api/periods?subject=Mob+202&section=M1").get_json()
    assert p["ok"] and p["current_id"] and p["next_term"]
    lock = c.post("/api/period_lock", json={"subject": "Mob 202", "section": "M1", "semester": "1st Sem",
                                             "term": "Prelim", "next_semester": "1st Sem", "next_term": "Midterm"})
    assert lock.get_json()["ok"]
    p = c.get("/api/periods?subject=Mob+202&section=M1").get_json()
    assert [x["locked"] for x in p["periods"]] == [True, False]
    assert c.get("/api/log").get_json()["ok"]
    assert c.post("/api/subject_delete", json={"subject": "Mob 202"}).get_json()["ok"]


def test_accounts_api_rules():
    c = _teacher()
    assert c.get("/api/teachers").get_json()["is_admin"] is True
    r = c.post("/api/teacher_add", json={"username": "mobteacher", "display_name": "Mob T", "password": "mobpassword1"})
    assert r.get_json()["ok"]
    tid = next(t["id"] for t in c.get("/api/teachers").get_json()["teachers"] if t["username"] == "mobteacher")

    t = app.test_client()
    assert t.post("/api/login", json={"username": "mobteacher", "password": "mobpassword1"}).get_json()["ok"]
    assert t.post("/api/teacher_add", json={"username": "x1", "password": "xxxxxxxx1"}).status_code == 403
    assert t.get("/api/teachers").get_json()["teachers"] == []
    assert t.post("/api/teacher_password", json={"teacher_id": tid, "password": "newpassword12"}).get_json()["ok"]
    assert t.get("/api/me").status_code == 200            # own sign-in stays valid after the change

    assert c.post("/api/teacher_delete", json={"teacher_id": tid}).get_json()["ok"]
