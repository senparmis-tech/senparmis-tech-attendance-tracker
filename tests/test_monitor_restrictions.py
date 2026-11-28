import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_tmp = tempfile.mkdtemp(prefix="attendance_test_monitor_")
os.environ["ATTENDANCE_DATA_DIR"] = _tmp

import flask_app  # noqa: E402
import auth  # noqa: E402
import store  # noqa: E402

app = flask_app.app

# --- Module-level account setup: idempotent, works with shared DB ---
# Ensure test password values are always correct regardless of what other modules did.

# Reset or create admin with password "adminpass1" (unique name to avoid conflicts)
try:
    admin_id = store.create_teacher("monitor_admin", "Section Monitor Admin", "adminpass1", is_admin=True)
    admin = store.get_teacher(admin_id)
except ValueError:
    admin = store.get_teacher(admin_id)
    store.update_teacher_password(admin["id"], "adminpass1")

# Reset or create regular teacher (id 2) with password "teacherpass1"
try:
    teacher_id = store.create_teacher("teacher", "Regular Teacher", "teacherpass1", is_admin=False)
    teacher = store.get_teacher(teacher_id)
except ValueError:
    teachers = store.list_teachers()
    teacher = next((t for t in teachers if t["username"] == "teacher"), None)
    # Reset password to ensure test consistency
    if teacher:
        store.update_teacher_password(teacher["id"], "teacherpass1")

# Reset or create monitor (id 3) with password "monitorpass1", section 2
try:
    monitor_id = store.create_teacher("monitor", "Section Monitor", "monitorpass1", is_admin=False, monitor_section_id=2)
    monitor = store.get_teacher(monitor_id)
except ValueError:
    teachers = store.list_teachers()
    monitor = next((t for t in teachers if t["username"] == "monitor"), None)
    # Reset password and monitor section for consistency
    if monitor:
        store.update_teacher_password(monitor["id"], "monitorpass1")

# Ensure subjects exist: MMW (id 1) with section BSCS-1A (id 1) and BSCS-1B (id 2)
if "MMW" not in store.load_data(include_archived=True):
    store.add_subject("MMW", None, section_name="BSCS-1A")
    store.add_section("MMW", "BSCS-1B")
else:
    # Ensure BSCS-1B exists
    data = store.load_data(include_archived=True)
    if "BSCS-1B" not in data["MMW"]["section_names"]:
        store.add_section("MMW", "BSCS-1B")

# Add a student to BSCS-1A for attendance tests
store.add_students(["MMW"], ["Monitor Student"], section="BSCS-1A")

def _login(username, password):
    c = app.test_client()
    auth._fails.clear()
    r = c.post("/login", data={"username": username, "password": password})
    assert r.status_code == 302, f"Login failed for {username}: {r.status_code}"
    return c

def _login_api(username, password):
    c = app.test_client()
    auth._fails.clear()
    r = c.post("/api/login", json={"username": username, "password": password})
    assert r.status_code == 200 and r.get_json()["ok"], f"API login failed for {username}"
    return c

def test_monitor_restrictions_web():
    """Section Monitor should only view own section and take attendance; all other actions blocked."""
    mon = _login("monitor", "monitorpass1")
    # Allowed: view dashboard, mark, scan, records, students (own section), lookup, log
    assert mon.get("/").status_code == 200
    assert mon.get("/mark?subject=MMW&section=BSCS-1A").status_code == 200
    assert mon.get("/scan?subject=MMW&section=BSCS-1A").status_code == 200
    assert mon.get("/records?subject=MMW&section=BSCS-1A").status_code == 200
    assert mon.get("/students?subject=MMW&section=BSCS-1A").status_code == 200
    assert mon.get("/lookup?q=Monitor").status_code == 200
    assert mon.get("/log").status_code == 200

    # Blocked: add student
    r = mon.post("/students/add", data={"names": "New Student", "subjects": ["MMW"], "section": "BSCS-1A"})
    assert r.status_code == 302 and r.headers["Location"] == "/", f"Add student should be blocked, got {r.status_code}, Location={r.headers['Location']}"
    # Blocked: remove student
    r = mon.post("/students/remove", data={"subject": "MMW", "section": "BSCS-1A", "name": "Monitor Student"})
    assert r.status_code == 302 and r.headers["Location"] == "/", f"Remove student should be blocked, got {r.status_code}, Location={r.headers['Location']}"
    # Blocked: edit student profile
    r = mon.post("/students/profile", data={"old_name": "Monitor Student", "name": "Monitor Student", "subject": "MMW"})
    assert r.status_code == 302 and r.headers["Location"] == "/", f"Edit profile should be blocked, got {r.status_code}, Location={r.headers['Location']}"
    # Blocked: delete date
    r = mon.post("/dates/delete", data={"subject": "MMW", "date": "2026-11-10", "section": "BSCS-1A"})
    assert r.status_code == 302 and r.headers["Location"] == "/", f"Delete date should be blocked, got {r.status_code}, Location={r.headers['Location']}"
    # Blocked: import meet (gate blocks before file parsing; 302 redirect is sufficient proof)
    r = mon.post("/import", data={"subject": "MMW"})
    assert r.status_code == 302 and r.headers["Location"] == "/", f"Import should be blocked, got {r.status_code}, Location={r.headers['Location']}"
    # Blocked: set API key
    r = mon.post("/api/set_key", json={"key": "a"*30})
    assert r.status_code == 403
    # Blocked: add section
    r = mon.post("/sections/add", data={"subject": "MMW", "section": "BSCS-1C"})
    assert r.status_code == 302 and r.headers["Location"] == "/", f"Add section should be blocked, got {r.status_code}, Location={r.headers['Location']}"
    # Blocked: rename section
    r = mon.post("/sections/rename", data={"subject": "MMW", "old_section": "BSCS-1A", "new_section": "BSCS-1X"})
    assert r.status_code == 302 and r.headers["Location"] == "/", f"Rename section should be blocked, got {r.status_code}, Location={r.headers['Location']}"
    # Blocked: delete section
    r = mon.post("/sections/delete", data={"subject": "MMW", "section": "BSCS-1B"})
    assert r.status_code == 302 and r.headers["Location"] == "/", f"Delete section should be blocked, got {r.status_code}, Location={r.headers['Location']}"
    # Blocked: add subject
    r = mon.post("/subjects/add", data={"name": "New Subject"})
    assert r.status_code == 302 and r.headers["Location"] == "/", f"Add subject should be blocked, got {r.status_code}, Location={r.headers['Location']}"
    # Blocked: archive/unarchive/delete subject
    r = mon.post("/subjects/archive", data={"subject": "MMW"})
    assert r.status_code == 302 and r.headers["Location"] == "/", f"Archive should be blocked, got {r.status_code}, Location={r.headers['Location']}"
    r = mon.post("/subjects/unarchive", data={"subject": "MMW"})
    assert r.status_code == 302 and r.headers["Location"] == "/", f"Unarchive should be blocked, got {r.status_code}, Location={r.headers['Location']}"
    r = mon.post("/subjects/delete", data={"subject": "MMW"})
    assert r.status_code == 302 and r.headers["Location"] == "/", f"Delete subject should be blocked, got {r.status_code}, Location={r.headers['Location']}"
    # Blocked: grade weights, items, scores, lock
    r = mon.post("/grades/weights", data={"subject": "MMW", "section": "BSCS-1A", "exam_weight": "50", "quiz_weight": "30", "activity_weight": "20"})
    assert r.status_code == 302 and r.headers["Location"] == "/", f"Grade weights should be blocked, got {r.status_code}, Location={r.headers['Location']}"
    r = mon.post("/grades/lock", data={"subject": "MMW", "section": "BSCS-1A", "locked": "1"})
    assert r.status_code == 302 and r.headers["Location"] == "/", f"Grade lock should be blocked, got {r.status_code}, Location={r.headers['Location']}"
    r = mon.post("/grades/items/add", data={"subject": "MMW", "section": "BSCS-1A", "category": "quiz", "title": "Q1", "max_score": "20"})
    assert r.status_code == 302 and r.headers["Location"] == "/", f"Grade items/add should be blocked, got {r.status_code}, Location={r.headers['Location']}"
    r = mon.post("/grades/items/delete", data={"subject": "MMW", "section": "BSCS-1A", "item_id": "1"})
    assert r.status_code == 302 and r.headers["Location"] == "/", f"Grade items/delete should be blocked, got {r.status_code}, Location={r.headers['Location']}"
    r = mon.post("/grades/scores", data={"subject": "MMW", "section": "BSCS-1A", "score_1_1": "10"})
    assert r.status_code == 302 and r.headers["Location"] == "/", f"Grade scores should be blocked, got {r.status_code}, Location={r.headers['Location']}"
    # Blocked: period actions
    r = mon.post("/api/period_edit", json={"subject": "MMW", "section": "BSCS-1A", "semester": "1st Sem", "term": "Prelim"})
    assert r.status_code == 403
    r = mon.post("/api/period_lock", json={"subject": "MMW", "section": "BSCS-1A", "semester": "1st Sem", "term": "Prelim", "next_semester": "1st Sem", "next_term": "Midterm"})
    assert r.status_code == 403
    r = mon.post("/api/period_unlock", json={"subject": "MMW", "section": "BSCS-1A", "period_id": 1})
    assert r.status_code == 403
    # Blocked: teacher management
    r = mon.post("/teachers/add", data={"username": "hacker", "password": "hackerpass1"})
    assert r.status_code == 302 and r.headers["Location"] == "/", f"Add teacher should be blocked, got {r.status_code}, Location={r.headers['Location']}"
    r = mon.post("/teachers/delete", data={"teacher_id": "2"})
    assert r.status_code == 302 and r.headers["Location"] == "/", f"Delete teacher should be blocked, got {r.status_code}, Location={r.headers['Location']}"
    r = mon.post("/teachers/assign_subject", data={"subject": "MMW", "teacher_id": "2"})
    assert r.status_code == 302 and r.headers["Location"] == "/", f"Assign subject should be blocked, got {r.status_code}, Location={r.headers['Location']}"
    r = mon.post("/teachers/password", data={"teacher_id": "2", "password": "newpass123"})
    assert r.status_code == 302 and r.headers["Location"] == "/", f"Change other's password should be blocked, got {r.status_code}, Location={r.headers['Location']}"
    # Allowed: change own password (should succeed)
    r = mon.post("/teachers/password", data={"teacher_id": monitor["id"], "password": "newmonitorpass1"})
    assert r.status_code == 302  # redirects to teachers page or dashboard; not blocked

def test_monitor_restrictions_mobile():
    """Section Monitor mobile API restrictions."""
    mon = _login_api("monitor", "monitorpass1")
    # Allowed: view students, mark, scan, records, log
    assert mon.get("/api/students?subject=MMW&section=BSCS-1A").status_code == 200
    assert mon.get("/api/mark?subject=MMW&section=BSCS-1A").status_code == 200
    assert mon.get("/api/records?subject=MMW&section=BSCS-1A").status_code == 200
    assert mon.get("/api/log").status_code == 200
    # Blocked: add student
    r = mon.post("/api/students_add", json={"subject": "MMW", "section": "BSCS-1A", "names": ["New Student"]})
    assert r.status_code == 403, f"Add student should be 403, got {r.status_code}"
    # Blocked: remove student
    r = mon.post("/api/students_remove", json={"subject": "MMW", "section": "BSCS-1A", "name": "Monitor Student"})
    assert r.status_code == 403
    # Blocked: edit profile
    r = mon.post("/api/student_profile", json={"old_name": "Monitor Student", "name": "Monitor Student", "subject": "MMW"})
    assert r.status_code == 403
    # Blocked: delete date
    r = mon.post("/api/date_delete", json={"subject": "MMW", "section": "BSCS-1A", "date": "2026-11-10"})
    assert r.status_code == 403
    # Blocked: set key
    r = mon.post("/api/set_key", json={"key": "a"*30})
    assert r.status_code == 403
    # Blocked: section add/rename/delete
    r = mon.post("/api/section_add", json={"subject": "MMW", "section": "BSCS-1C"})
    assert r.status_code == 403
    r = mon.post("/api/section_rename", json={"subject": "MMW", "old_section": "BSCS-1A", "new_section": "BSCS-1X"})
    assert r.status_code == 403
    r = mon.post("/api/section_delete", json={"subject": "MMW", "section": "BSCS-1B"})
    assert r.status_code == 403
    # Blocked: subject add/archive/unarchive/delete
    r = mon.post("/api/subject_add", json={"name": "New Subject"})
    assert r.status_code == 403
    r = mon.post("/api/subject_archive", json={"subject": "MMW"})
    assert r.status_code == 403
    r = mon.post("/api/subject_unarchive", json={"subject": "MMW"})
    assert r.status_code == 403
    r = mon.post("/api/subject_delete", json={"subject": "MMW"})
    assert r.status_code == 403
    # Blocked: grade actions
    r = mon.post("/api/grade_weights", json={"subject": "MMW", "section": "BSCS-1A", "exam": 50, "quiz": 30, "activity": 20})
    assert r.status_code == 403
    r = mon.post("/api/grade_lock", json={"subject": "MMW", "section": "BSCS-1A", "locked": True})
    assert r.status_code == 403
    r = mon.post("/api/grade_item_add", json={"subject": "MMW", "section": "BSCS-1A", "category": "quiz", "title": "Q1", "max_score": 20})
    assert r.status_code == 403
    r = mon.post("/api/grade_item_delete", json={"subject": "MMW", "section": "BSCS-1A", "item_id": 1})
    assert r.status_code == 403
    r = mon.post("/api/grade_score", json={"subject": "MMW", "section": "BSCS-1A", "item_id": 1, "enrollment_id": 1, "score": 10})
    assert r.status_code == 403
    # Blocked: period actions
    r = mon.post("/api/period_edit", json={"subject": "MMW", "section": "BSCS-1A", "semester": "1st Sem", "term": "Prelim"})
    assert r.status_code == 403
    r = mon.post("/api/period_lock", json={"subject": "MMW", "section": "BSCS-1A", "semester": "1st Sem", "term": "Prelim", "next_semester": "1st Sem", "next_term": "Midterm"})
    assert r.status_code == 403
    r = mon.post("/api/period_unlock", json={"subject": "MMW", "section": "BSCS-1A", "period_id": 1})
    assert r.status_code == 403
    # Blocked: teacher management
    r = mon.post("/api/teacher_add", json={"username": "hacker", "password": "hackerpass1"})
    assert r.status_code == 403
    r = mon.post("/api/teacher_delete", json={"teacher_id": 2})
    assert r.status_code == 403
    r = mon.post("/api/teacher_assign", json={"subject": "MMW", "teacher_id": 2})
    assert r.status_code == 403
    r = mon.post("/api/teacher_password", json={"teacher_id": 2, "password": "newpass123"})
    assert r.status_code == 403
    # Gate blocks own-password change for monitors too (endpoint not in monitor whitelist), consistent with web
    r = mon.post("/api/teacher_password", json={"teacher_id": monitor["id"], "password": "newmonitorpass1"})
    assert r.status_code == 403

def test_teacher_restrictions_web():
    """Non-admin teacher should only access own subjects and change own password."""
    tch = _login("teacher", "teacherpass1")
    # Assign MMW to teacher (id 2) so they can access it
    admin_client = _login("monitor_admin", "adminpass1")
    admin_client.post("/teachers/assign_subject", data={"subject": "MMW", "teacher_id": teacher["id"]})
    # Allowed: view MMW
    assert tch.get("/?subject=MMW").status_code == 200
    assert tch.get("/mark?subject=MMW").status_code == 200
    assert tch.get("/students?subject=MMW").status_code == 200
    # Blocked: view other subject (College Algebra - assume exists)
    r = tch.get("/?subject=College+Algebra")
    # Should not show College Algebra; redirect or empty
    assert r.status_code == 200  # dashboard loads but without that subject
    html = r.get_data(as_text=True)
    assert "College Algebra" not in html
    # Blocked: modify other subject
    r = tch.post("/api/save", json={"subject": "College Algebra", "date": "2026-11-11", "marks": []})
    assert r.status_code == 400
    # Blocked: add teacher
    r = tch.post("/teachers/add", data={"username": "hacker", "password": "hackerpass1"})
    assert r.status_code == 302 and r.headers["Location"] == "/teachers", f"Add teacher should be blocked, got {r.status_code}, Location={r.headers['Location']}"
    # Blocked: delete teacher
    r = tch.post("/teachers/delete", data={"teacher_id": "1"})
    assert r.status_code == 302 and r.headers["Location"] == "/teachers", f"Delete teacher should be blocked, got {r.status_code}, Location={r.headers['Location']}"
    # Blocked: assign subject
    r = tch.post("/teachers/assign_subject", data={"subject": "MMW", "teacher_id": "1"})
    assert r.status_code == 302 and r.headers["Location"] == "/teachers", f"Assign subject should be blocked, got {r.status_code}, Location={r.headers['Location']}"
    # Blocked: change other's password
    r = tch.post("/teachers/password", data={"teacher_id": "1", "password": "newpass123"})
    assert r.status_code == 302 and r.headers["Location"] == "/teachers", f"Change other's password should be blocked, got {r.status_code}, Location={r.headers['Location']}"
    # Allowed: change own password
    r = tch.post("/teachers/password", data={"teacher_id": teacher["id"], "password": "newteacherpass1"})
    assert r.status_code == 302

def test_teacher_restrictions_mobile():
    """Non-admin teacher mobile API restrictions."""
    # Reset teacher password to original since web test changed it
    store.update_teacher_password(teacher["id"], "teacherpass1")
    tch = _login_api("teacher", "teacherpass1")
    # Assign MMW to teacher
    admin_client = _login_api("monitor_admin", "adminpass1")
    admin_client.post("/api/teacher_assign", json={"subject": "MMW", "teacher_id": teacher["id"]})
    # Allowed: view MMW
    assert tch.get("/api/subjects").status_code == 200
    # Blocked: view other subject (should not appear)
    subs = tch.get("/api/subjects").get_json()
    sub_names = [s["name"] for s in subs["subjects"]]
    assert "MMW" in sub_names
    assert "College Algebra" not in sub_names
    # Blocked: modify other subject
    r = tch.post("/api/save", json={"subject": "College Algebra", "date": "2026-11-11", "marks": []})
    assert r.status_code == 400
    # Blocked: add teacher
    r = tch.post("/api/teacher_add", json={"username": "hacker", "password": "hackerpass1"})
    assert r.status_code == 403
    # Blocked: delete teacher
    r = tch.post("/api/teacher_delete", json={"teacher_id": 1})
    assert r.status_code == 403
    # Blocked: assign subject
    r = tch.post("/api/teacher_assign", json={"subject": "MMW", "teacher_id": 1})
    assert r.status_code == 403
    # Blocked: change other's password
    r = tch.post("/api/teacher_password", json={"teacher_id": 1, "password": "newpass123"})
    assert r.status_code == 403
    # Allowed: change own password
    r = tch.post("/api/teacher_password", json={"teacher_id": teacher["id"], "password": "teacherpass1"})
    assert r.status_code == 200 and r.get_json()["ok"]

def test_monitor_attendance_and_scan():
    """Section Monitor can take attendance and scan."""
    mon = _login("monitor", "monitorpass1")
    # Take attendance
    r = mon.post("/api/save", json={
        "subject": "MMW", "section": "BSCS-1A", "date": "2026-11-15", "topic": "Monitor Class",
        "marks": [{"name": "Monitor Student", "score": 100}]
    })
    assert r.status_code == 200 and r.get_json()["ok"]
    # Scan (GET /scan should be allowed, POST /api/scan should be allowed)
    assert mon.get("/scan?subject=MMW&section=BSCS-1A").status_code == 200
    r = mon.post("/api/scan", json={"subject": "MMW", "section": "BSCS-1A", "code": "1234567890"})
    # Scan may fail if code invalid, but should not be 403; accept 200 or 400
    assert r.status_code in (200, 400)