"""
Password configuration, per-teacher sign-in/sign-out routes, and request authentication gate.
"""
import hashlib
import hmac
import time
import urllib.parse

from flask import flash, g, jsonify, redirect, render_template, request, session, url_for
from markupsafe import escape

from config import MIN_PASSWORD, OPEN_MODE
from helpers import log_change
from store import (assign_subject_teacher, create_teacher, delete_teacher,
                   get_teacher, get_student_hash, list_all_sections, list_subjects_with_owners, list_teachers,
                   update_teacher_password, verify_teacher, set_student_password, verify_student_password)
from web import app


def pw_version(role, extra=""):
    return hmac.new(app.secret_key.encode(), f"{role}:{extra}".encode(), hashlib.sha256).hexdigest()[:20]


def _resolve_session():
    """Return (role, teacher_id, teacher_name, is_admin, monitor_section_id) for the current session."""
    role = session.get("role")
    tid = session.get("teacher_id")
    if role == "teacher" and tid:
        t = get_teacher(tid)
        if t and hmac.compare_digest(str(session.get("pv", "")), pw_version("teacher_db", t["password_hash"])):
            mon_sec = t.get("monitor_section_id")
            # Preview-as-monitor: admin toggles session["preview_section_id"]
            preview_sec = session.get("preview_section_id")
            return "teacher", t["id"], t["display_name"], bool(t["is_admin"]), mon_sec, preview_sec
        return None, None, None, False, None, None
    if role == "student":
        student_hash = get_student_hash()
        if student_hash and hmac.compare_digest(str(session.get("pv", "")), pw_version("student_db", student_hash)):
            return "student", None, None, False, None, None
    return None, None, None, False, None, None


def current_role():
    return _resolve_session()[0]


def locked_page(problem):
    html = (
        "<!doctype html><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<title>Site locked</title><body style=\"font:16px/1.5 system-ui,Segoe UI,Arial;max-width:640px;margin:40px auto;padding:0 16px;background:#f8fafc;color:#0f172a\">"
        "<div style='background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:24px;box-shadow:0 2px 8px rgba(0,0,0,0.05)'>"
        "<h1 style='margin-top:0;font-size:22px'>🔒 This site is locked</h1>"
        f"<p style='color:#dc2626;font-weight:700'>{escape(problem)}</p>"
        "<p>To protect student names on PythonAnywhere, a teacher account must be created before opening the site.</p>"
        "<p>Open the <code>/setup</code> page from localhost to create the first teacher account.</p>"
        "<p>Then refresh this page.</p></div></body>")
    return html, 503


_fails = {}


def fail_key():
    return (request.remote_addr or "") + "|" + request.headers.get("X-Forwarded-For", "").split(",")[0].strip()


PUBLIC_ENDPOINTS = {"login", "logout", "static", "subject_image", "api_login", "setup"}
STUDENT_ENDPOINTS = {"records", "api_records", "api_me", "api_logout"}
MONITOR_ALLOWED_ENDPOINTS = {
    "dashboard",
    "api_dashboard",
    "mark",
    "api_mark",
    "api_save",
    "scan",
    "api_scan",
    "api_set_key",
    "records",
    "api_records",
    "print_sheet",
    "dates_delete",
    "import_meet",
    "api_meet_alias",
    "students",
    "api_subjects",
    "students_add",
    "students_remove",
    "students_profile",
    "lookup",
    "api_lookup",
    "log_page",
    "preview_monitor",
    "api_me",
    "api_logout",
}


@app.context_processor
def inject_auth():
    return {
        "role": getattr(g, "role", None),
        "teacher_id": getattr(g, "teacher_id", None),
        "teacher_name": getattr(g, "teacher_name", None),
        "is_admin": False if getattr(g, "preview_section_id", None) else getattr(g, "is_admin", False),
        "is_monitor": getattr(g, "is_monitor", False),
        "monitor_section_name": getattr(g, "monitor_section_name", None),
        "monitor_sec_name": getattr(g, "monitor_sec_name", None),
        "monitor_sub_name": getattr(g, "monitor_sub_name", None),
        "preview_section_id": getattr(g, "preview_section_id", None),
        "auth_on": bool(list_teachers()),
    }


@app.before_request
def gate():
    g.role = None
    g.teacher_id = None
    g.teacher_name = None
    g.is_admin = False
    g.is_monitor = False
    g.monitor_section_id = None
    g.monitor_section_name = None
    g.monitor_sec_name = None
    g.monitor_sub_name = None
    g.preview_section_id = None
    if request.method == "POST":
        origin = request.headers.get("Origin")
        allowed_hosts = {request.host, request.headers.get("X-Forwarded-Host", "").split(",")[0].strip()}
        if origin and urllib.parse.urlparse(origin).netloc not in allowed_hosts:
            msg = "That request came from another site and was blocked."
            return (jsonify(ok=False, error=msg), 403) if request.path.startswith("/api/") else (msg, 403)
    if request.endpoint is None:
        return None
    if not list_teachers() and request.endpoint != "setup" and request.endpoint not in PUBLIC_ENDPOINTS:
        return redirect(url_for("setup"))
    role, tid, tname, is_adm, mon_sec, preview_sec = _resolve_session()
    g.role, g.teacher_id, g.teacher_name, g.is_admin = role, tid, tname, is_adm
    g.monitor_section_id = mon_sec or preview_sec
    g.preview_section_id = preview_sec
    g.is_monitor = bool(mon_sec or preview_sec)
    # Load section name for monitor label in UI
    if mon_sec or preview_sec:
        sec_id = preview_sec or mon_sec
        try:
            import db as _db
            conn = _db.connect()
            row = conn.execute(
                "SELECT sec.name AS sec_name, sub.name AS sub_name FROM sections sec "
                "JOIN subjects sub ON sub.id = sec.subject_id WHERE sec.id = ?", (sec_id,)).fetchone()
            conn.close()
            if row:
                g.monitor_section_name = f"{row['sub_name']} · {row['sec_name']}"
                g.monitor_sec_name = row['sec_name']
                g.monitor_sub_name = row['sub_name']
        except Exception:
            pass
    if request.endpoint in PUBLIC_ENDPOINTS:
        return None
    if g.is_monitor:
        if request.endpoint not in MONITOR_ALLOWED_ENDPOINTS:
            if request.path.startswith("/api/"):
                return jsonify(ok=False, error="Section monitors do not have access to that feature."), 403
            flash("You don't have access to that page.", "err")
            return redirect(url_for("dashboard"))
        return None
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


@app.route("/setup", methods=["GET", "POST"])
def setup():
    if list_teachers():
        return redirect(url_for("login"))
    if request.remote_addr != "127.0.0.1" and request.remote_addr != "::1":
        return "Setup is only allowed from localhost for security reasons.", 403
    error = ""
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        admin_pw = request.form.get("admin_password", "").strip()
        student_pw = request.form.get("student_password", "").strip()
        try:
            create_teacher(username or "admin", "Administrator", admin_pw, is_admin=True)
            set_student_password(student_pw)
            return redirect(url_for("login"))
        except ValueError as err:
            error = str(err)
    return render_template("setup.html", error=error)


@app.route("/login", methods=["GET", "POST"])
def login():
    teachers = list_teachers()
    error = ""
    username = ""
    if request.method == "POST":
        key, now = fail_key(), time.time()
        count, until = _fails.get(key, (0, 0))
        if until > now:
            error = f"Too many wrong passwords. Wait {int((until - now) // 60) + 1} minute(s) and try again."
        else:
            username = request.form.get("username", "").strip()
            pw = request.form.get("password", "").strip()
            if username:
                matched_teacher = verify_teacher(username, pw)
                role = None
                if matched_teacher:
                    session.clear()
                    session.update(role="teacher", teacher_id=matched_teacher["id"],
                                   pv=pw_version("teacher_db", matched_teacher["password_hash"]))
                    session.permanent = True
                    _fails.pop(key, None)
                    log_change("Sign-in", "", f"Teacher '{matched_teacher['display_name']}' ({matched_teacher['username']}) signed in")
                    return redirect(url_for("dashboard"))
                time.sleep(0.5)
                count += 1
                _fails[key] = (0, now + 300) if count >= 5 else (count, 0)
                log_change("Failed sign-in", "", "Wrong password" + (" (locked for 5 minutes)" if count >= 5 else ""))
                error = "Wrong username or password."
            elif verify_student_password(pw):
                role = "student"
                session.clear()
                shash = get_student_hash()
                session.update(role="student", pv=pw_version("student_db", shash or ""))
                session.permanent = True
                _fails.pop(key, None)
                log_change("Sign-in", "", f"{role.capitalize()} signed in")
                return redirect(url_for("records"))
            else:
                time.sleep(0.5)
                count += 1
                _fails[key] = (0, now + 300) if count >= 5 else (count, 0)
                log_change("Failed sign-in", "", "Wrong password" + (" (locked for 5 minutes)" if count >= 5 else ""))
                error = "Wrong username or password." if teachers else "Wrong password."
    return render_template("login.html", page="login", error=error, username=username, has_teachers=bool(teachers))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


@app.route("/api/login", methods=["POST"])
def api_login():
    """Mobile app & API login endpoint returning JSON session status."""
    data = request.get_json(silent=True) or request.form.to_dict() or {}
    username = str(data.get("username", "")).strip()
    pw = str(data.get("password", "")).strip()
    if not pw:
        return jsonify(ok=False, error="Password is required."), 400
    teachers = list_teachers()
    key, now = fail_key(), time.time()
    count, until = _fails.get(key, (0, 0))
    if until > now:
        mins = int((until - now) // 60) + 1
        return jsonify(ok=False, error=f"Too many wrong attempts. Wait {mins} minute(s)."), 429

    if username:
        matched_teacher = verify_teacher(username, pw)
        if matched_teacher:
            session.clear()
            session.update(role="teacher", teacher_id=matched_teacher["id"],
                           pv=pw_version("teacher_db", matched_teacher["password_hash"]))
            session.permanent = True
            _fails.pop(key, None)
            log_change("API Sign-in", "", f"Teacher '{matched_teacher['display_name']}' signed in via Mobile App")
            return jsonify(
                ok=True,
                role="teacher",
                teacher_id=matched_teacher["id"],
                username=matched_teacher["username"],
                display_name=matched_teacher["display_name"],
                is_admin=bool(matched_teacher["is_admin"]),
                is_monitor=bool(matched_teacher["is_monitor"]),
                monitor_section_id=matched_teacher.get("monitor_section_id"),
            )
        time.sleep(0.5)
        count += 1
        _fails[key] = (0, now + 300) if count >= 5 else (count, 0)
        log_change("Failed API sign-in", "", "Wrong password" + (" (locked for 5 minutes)" if count >= 5 else ""))
        return jsonify(ok=False, error="Wrong username or password."), 401
    elif verify_student_password(pw):
        role = "student"
        user_info = {
            "role": "student",
            "teacher_id": None,
            "username": "student",
            "display_name": "Student",
            "is_admin": False,
            "is_monitor": False,
            "monitor_section_id": None,
        }
        session.clear()
        shash = get_student_hash()
        session.update(role="student", pv=pw_version("student_db", shash or ""))
        session.permanent = True
        _fails.pop(key, None)
        log_change("API Sign-in", "", f"{role.capitalize()} signed in via Mobile App")
        return jsonify(ok=True, **user_info)
    else:
        time.sleep(0.5)
        count += 1
        _fails[key] = (0, now + 300) if count >= 5 else (count, 0)
        log_change("Failed API sign-in", "", "Wrong password" + (" (locked for 5 minutes)" if count >= 5 else ""))
        return jsonify(ok=False, error="Wrong username or password."), 401


@app.route("/api/me", methods=["GET"])
def api_me():
    """Return the authenticated user profile and roles."""
    if not getattr(g, "role", None):
        return jsonify(ok=False, authenticated=False), 401
    return jsonify(
        ok=True,
        authenticated=True,
        role=g.role,
        teacher_id=g.teacher_id,
        display_name=g.teacher_name,
        is_admin=g.is_admin,
        is_monitor=g.is_monitor,
        monitor_section_id=g.monitor_section_id,
        monitor_section_name=g.monitor_section_name,
    )


@app.route("/api/logout", methods=["POST", "GET"])
def api_logout():
    """End the current API session."""
    session.clear()
    return jsonify(ok=True, message="Signed out.")


# -------------------------------------------------------- teacher management
@app.route("/teachers")
def teachers_page():
    from store import list_all_sections
    return render_template(
        "teachers.html", page="teachers",
        teachers=list_teachers(),
        subjects=list_subjects_with_owners() if g.is_admin else [],
        all_sections=list_all_sections() if g.is_admin else [],
    )


@app.route("/teachers/add", methods=["POST"])
def teachers_add():
    if not g.is_admin:
        flash("Only an admin can add teacher accounts.", "err")
        return redirect(url_for("teachers_page"))
    username = request.form.get("username", "").strip()
    display_name = request.form.get("display_name", "").strip()
    password = request.form.get("password", "").strip()
    is_adm = request.form.get("is_admin") == "1"
    is_mon = request.form.get("is_monitor") == "1"
    monitor_section_id = request.form.get("monitor_section_id", "").strip() or None
    if is_mon and not monitor_section_id:
        flash("Pick the section this monitor will manage.", "err")
        return redirect(url_for("teachers_page"))
    try:
        create_teacher(username, display_name, password, is_admin=is_adm,
                       monitor_section_id=monitor_section_id if is_mon else None)
        role_label = "admin" if is_adm else ("section monitor" if is_mon else "teacher")
        log_change("Teacher added", "", f"Created {role_label} '{display_name or username}' ({username})")
        flash(f"Created {role_label} account '{username}'.", "ok")
    except ValueError as err:
        flash(str(err), "err")
    return redirect(url_for("teachers_page"))


@app.route("/teachers/password", methods=["POST"])
def teachers_password():
    target_id = request.form.get("teacher_id", "").strip()
    new_pw = request.form.get("password", "").strip()
    try:
        tid = int(target_id)
    except ValueError:
        flash("Invalid teacher account.", "err")
        return redirect(url_for("teachers_page"))
    if not g.is_admin and tid != g.teacher_id:
        flash("You can only change your own password.", "err")
        return redirect(url_for("teachers_page"))
    try:
        t = get_teacher(tid)
        update_teacher_password(tid, new_pw)
        if tid == g.teacher_id:
            t_updated = get_teacher(tid)
            session["pv"] = pw_version("teacher_db", t_updated["password_hash"])
        log_change("Password updated", "", f"Updated password for '{t['username'] if t else tid}'")
        flash("Password updated.", "ok")
    except ValueError as err:
        flash(str(err), "err")
    return redirect(url_for("teachers_page"))


@app.route("/teachers/delete", methods=["POST"])
def teachers_delete():
    if not g.is_admin:
        flash("Only an admin can remove teacher accounts.", "err")
        return redirect(url_for("teachers_page"))
    target_id = request.form.get("teacher_id", "").strip()
    try:
        tid = int(target_id)
        if tid == g.teacher_id:
            flash("You cannot delete the account you are currently signed in with.", "err")
            return redirect(url_for("teachers_page"))
        t = get_teacher(tid)
        delete_teacher(tid)
        log_change("Teacher removed", "", f"Deleted teacher '{t['username'] if t else tid}'")
        flash("Teacher account removed.", "ok")
    except ValueError as err:
        flash(str(err), "err")
    return redirect(url_for("teachers_page"))


@app.route("/teachers/assign_subject", methods=["POST"])
def teachers_assign_subject():
    if not g.is_admin:
        flash("Only an admin can reassign subjects.", "err")
        return redirect(url_for("teachers_page"))
    subject_name = request.form.get("subject", "").strip()
    teacher_id = request.form.get("teacher_id", "").strip()
    try:
        assign_subject_teacher(subject_name, teacher_id)
        t = get_teacher(int(teacher_id)) if teacher_id not in ("", "0") else None
        owner_label = f"{t['display_name']} ({t['username']})" if t else "Shared / Admin only"
        log_change("Subject assigned", subject_name, f"Owner set to {owner_label}")
        flash(f"Assigned '{subject_name}' to {owner_label}.", "ok")
    except ValueError as err:
        flash(str(err), "err")
    return redirect(url_for("teachers_page"))


# -------------------------------------------------------- preview-as-monitor toggle
@app.route("/preview_monitor", methods=["POST"])
def preview_monitor():
    """Admin only: toggle a 'preview as monitor' mode to see what a section monitor would see."""
    if not g.is_admin:
        flash("Only an admin can use preview mode.", "err")
        return redirect(url_for("dashboard"))
    sec_id_raw = request.form.get("section_id", "").strip()
    if sec_id_raw:
        try:
            session["preview_section_id"] = int(sec_id_raw)
            flash("👁 Previewing as Section Monitor. Click 'Exit Preview' to return to your admin view.", "ok")
        except ValueError:
            flash("Invalid section.", "err")
    else:
        session.pop("preview_section_id", None)
        flash("Exited monitor preview — back to your admin view.", "ok")
    return redirect(url_for("dashboard"))
