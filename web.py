"""
Flask application object and session/secret-key setup.
"""
import os
import secrets
from datetime import timedelta

from flask import Flask

from config import MAX_UPLOAD, SECRET_FILE

app = Flask(__name__)


def load_secret():
    env = os.environ.get("ATTENDANCE_SECRET_KEY", "").strip()
    if len(env) >= 32:
        return env
    try:
        with open(SECRET_FILE, encoding="utf-8") as f:
            s = f.read().strip()
        if len(s) >= 32:
            return s
    except OSError:
        pass
    s = secrets.token_hex(32)
    try:
        with open(SECRET_FILE, "w", encoding="utf-8") as f:
            f.write(s)
    except OSError:
        pass
    return s


app.secret_key = load_secret()
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
                  PERMANENT_SESSION_LIFETIME=timedelta(hours=12))
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD * 4
