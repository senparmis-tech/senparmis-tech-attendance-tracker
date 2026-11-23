"""
Password configuration, per-teacher sign-in/sign-out routes, and request authentication gate.
"""
import hashlib
import hmac
import os
import time
import urllib.parse

from flask import flash, g, jsonify, redirect, render_template, request, session, url_for
from markupsafe import escape

from config import MIN_PASSWORD, OPEN_MODE, PASSWORD_FILE
from helpers import log_change
from store import (assign_subject_teacher, create_teacher, delete_teacher,
                   get_teacher, list_all_sections, list_subjects_with_owners, list_teachers,
                   update_teacher_password, verify_teacher)
from web import app


def read_passwords():
    out = {"teacher": [], "student": []}
    env_t = os.environ.get("ATTENDANCE_TEACHER_PASSWORD", "").strip()
    if env_t:
        out["teacher"].extend([p.strip() for p in env_t.split(",") if p.strip()])
    env_s = os.environ.get("ATTENDANCE_STUDENT_PASSWORD", "").strip()
    if env_s:
        out["student"].extend([p.strip() for p in env_s.split(",") if p.strip()])
    try:
        with open(PASSWORD_FILE, encoding="utf-8-sig") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip().lower()
                if k in ("teacher", "student"):
                    for p in v.split(","):
                        cleaned = p.strip().strip("'\"")
                        if cleaned and cleaned not in out[k]:
                            out[k].append(cleaned)
    except OSError:
        pass
    return out


def password_problem(cfg):
    """None when the passwords or teacher accounts are usable, otherwise a short explanation."""
    t, s = cfg["teacher"], cfg["student"]
    has_db_teachers = bool(list_teachers())
    if not t and not has_db_teachers:
        return "No teacher password is set yet in passwords.txt."
    for p in t:
        if len(p) < MIN_PASSWORD:
            return f"A teacher password is too short (use at least {MIN_PASSWORD} characters)."
    for p in s:
        if len(p) < MIN_PASSWORD:
            return f"A student password is too short (use at least {MIN_PASSWORD} characters)."
    if any(p in t for p in s):
        return "Student passwords must be different from teacher passwords."
    return None


def pw_version(role, cfg, extra=""):
    pws = ",".join(sorted(cfg.get(role, [])))
    return hmac.new(app.secret_key.encode(), f"{role}:{pws}:{extra}".encode(), hashlib.sha256).hexdigest()[:20]


def _resolve_session():
    """Return (role, teacher_id, teacher_name, is_admin, monitor_section_id) for the current session."""
    cfg = read_passwords()
    role = session.get("role")
    tid = session.get("teacher_id")
    if role == "teacher" and tid:
        t = get_teacher(tid)
        if t and hmac.compare_digest(str(session.get("pv", "")), pw_version("teacher_db", cfg, t["password_hash"])):
            mon_sec = t.get("monitor_section_id")
            # Preview-as-monitor: admin toggles session["preview_section_id"]
            preview_sec = session.get("preview_section_id")
            return "teacher", t["id"], t["display_name"], bool(t["is_admin"]), mon_sec, preview_sec
        return None, None, None, False, None, None
    if role in ("teacher", "student") and cfg.get(role) and hmac.compare_digest(
            str(session.get("pv", "")), pw_version(role, cfg)):
        return role, None, ("Admin" if role == "teacher" else None), (role == "teacher"), None, None
    return None, None, None, False, None, None


def current_role():
    return _resolve_session()[0]


def locked_page(problem):
    path = escape(PASSWORD_FILE)
    html = (
        "<!doctype html><meta charset='utf-8'><meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<title>Site locked</title><body style=\"font:16px/1.5 system-ui,Segoe UI,Arial;max-width:640px;margin:40px auto;padding:0 16px;background:#f8fafc;color:#0f172a\">"
        "<div style='background:#fff;border:1px solid #e2e8f0;border-radius:12px;padding:24px;box-shadow:0 2px 8px rgba(0,0,0,0.05)'>"
        "<h1 style='margin-top:0;font-size:22px'>🔒 This site is locked</h1>"
        f"<p style='color:#dc2626;font-weight:700'>{escape(problem)}</p>"
        "<p>To protect student names on PythonAnywhere, a teacher password must be set before opening the site.</p>"
        "<p>Open or create a plain text file at this location:</p>"
        f"<pre style='background:#f1f5f9;padding:12px;border-radius:8px;white-space:pre-wrap;word-break:break-all;font-size:14px'>{path}</pre>"
        "<p>and add these lines (at least " + str(MIN_PASSWORD) + " characters for security):</p>"
        "<pre style='background:#f1f5f9;padding:12px;border-radius:8px;font-size:14px'>teacher=your-teacher-password\nstudent=your-student-password</pre>"
        "<p>You can also add multiple teacher passwords separated by commas.</p>"
        "<p>Then refresh this page.</p></div></body>")
    return html, 503


_fails = {}


def fail_key():
    return (request.remote_addr or "") + "|" + request.headers.get("X-Forwarded-For", "").split(",")[0].strip()


PUBLIC_ENDPOINTS = {"login", "logout", "static", "subject_image"}
STUDENT_ENDPOINTS = {"records"}
MONITOR_ALLOWED_ENDPOINTS = {
    "dashboard",
    "mark",
    "api_save",
    "scan",
    "api_scan",
    "api_set_key",
    "records",
    "print_sheet",
    "dates_delete",
    "import_meet",
    "api_meet_alias",
    "students",
    "students_add",
    "students_remove",
    "students_profile",
    "lookup",
    "log_page",
    "preview_monitor",
}


@app.context_processor
def inject_auth():
    cfg = read_passwords()
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
        "auth_on": bool(cfg["teacher"] or list_teachers()),
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
    cfg = read_passwords()
    if OPEN_MODE and not cfg["teacher"] and not list_teachers():
        g.role = "teacher"
        g.teacher_name = "Admin"
        g.is_admin = True
        return None
    problem = password_problem(cfg)
    if problem:
        return locked_page(problem)
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


@app.route("/login", methods=["GET", "POST"])
def login():
    cfg = read_passwords()
    teachers = list_teachers()
    if OPEN_MODE and not cfg["teacher"] and not teachers:
        return redirect(url_for("dashboard"))
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
            matched_teacher = verify_teacher(username, pw) if username else verify_teacher(pw)
            role = None
            if matched_teacher:
                session.clear()
                session.update(role="teacher", teacher_id=matched_teacher["id"],
                               pv=pw_version("teacher_db", cfg, matched_teacher["password_hash"]))
                session.permanent = True
                _fails.pop(key, None)
                log_change("Sign-in", "", f"Teacher '{matched_teacher['display_name']}' ({matched_teacher['username']}) signed in")
                return redirect(url_for("dashboard"))
            if (not username or username.lower() == "admin") and any(
                    hmac.compare_digest(pw.encode(), t_pw.encode()) for t_pw in cfg["teacher"]):
                role = "teacher"
            elif (not username or username.lower() == "student") and any(
                    hmac.compare_digest(pw.encode(), s_pw.encode()) for s_pw in cfg["student"]):
                role = "student"
            if role:
                session.clear()
                session.update(role=role, pv=pw_version(role, cfg))
                session.permanent = True
                _fails.pop(key, None)
                log_change("Sign-in", "", f"{role.capitalize()} signed in")
                return redirect(url_for("dashboard") if role == "teacher" else url_for("records"))
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
            session["pv"] = pw_version("teacher_db", read_passwords(), t_updated["password_hash"])
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
