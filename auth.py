"""
Password configuration, sign-in/sign-out routes, and request authentication gate.
"""
import hashlib
import hmac
import os
import time
import urllib.parse

from flask import g, jsonify, redirect, render_template, request, session, url_for
from markupsafe import escape

from config import MIN_PASSWORD, OPEN_MODE, PASSWORD_FILE
from helpers import log_change
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
    """None when the passwords are usable, otherwise a short explanation."""
    t, s = cfg["teacher"], cfg["student"]
    if not t:
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


def pw_version(role, cfg):
    pws = ",".join(sorted(cfg[role]))
    return hmac.new(app.secret_key.encode(), f"{role}:{pws}".encode(), hashlib.sha256).hexdigest()[:20]


def current_role():
    cfg = read_passwords()
    role = session.get("role")
    if role in ("teacher", "student") and cfg.get(role) and hmac.compare_digest(
            str(session.get("pv", "")), pw_version(role, cfg)):
        return role
    return None


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


@app.context_processor
def inject_auth():
    return {"role": getattr(g, "role", None), "auth_on": bool(read_passwords()["teacher"])}


@app.before_request
def gate():
    g.role = None
    if request.method == "POST":
        origin = request.headers.get("Origin")
        if origin and urllib.parse.urlparse(origin).netloc != request.host:
            msg = "That request came from another site and was blocked."
            return (jsonify(ok=False, error=msg), 403) if request.path.startswith("/api/") else (msg, 403)
    if request.endpoint is None:
        return None
    cfg = read_passwords()
    if OPEN_MODE and not cfg["teacher"]:
        g.role = "teacher"
        return None
    problem = password_problem(cfg)
    if problem:
        return locked_page(problem)
    if request.endpoint in PUBLIC_ENDPOINTS:
        g.role = current_role()
        return None
    role = current_role()
    g.role = role
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
    if OPEN_MODE and not cfg["teacher"]:
        return redirect(url_for("dashboard"))
    error = ""
    if request.method == "POST":
        key, now = fail_key(), time.time()
        count, until = _fails.get(key, (0, 0))
        if until > now:
            error = f"Too many wrong passwords. Wait {int((until - now) // 60) + 1} minute(s) and try again."
        else:
            pw = request.form.get("password", "").strip()
            role = None
            if any(hmac.compare_digest(pw.encode(), t_pw.encode()) for t_pw in cfg["teacher"]):
                role = "teacher"
            elif any(hmac.compare_digest(pw.encode(), s_pw.encode()) for s_pw in cfg["student"]):
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
            error = "Wrong password."
    return render_template("login.html", page="login", error=error)


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))
