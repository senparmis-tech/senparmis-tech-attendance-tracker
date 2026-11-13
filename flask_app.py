"""
School attendance website that keeps its records in a SQLite database (Excel import/export supported).

Layout of every subject sheet (matches a classic attendance sheet):
  - one sheet (tab) per subject
  - students go down the side (column B, from row 5)
  - dates go across the top (row 4, from column H)
  - the lesson topic for each date sits in row 3
  - cells hold  p = present, x = absent, l = late, e = excused, r = recited
  - columns C-G are formulas (Present, Absent, Late, Excused, Rate)

Run it locally with:  python flask_app.py
On PythonAnywhere, the WSGI file imports ``app`` from this module.
"""
import socket
import sys
import threading
import webbrowser

import auth  # registers @app.before_request, /login, /logout
import routes  # registers page and API routes
import lookup  # registers the student lookup page
from config import DB_FILE, HOST, START_PORT
from store import ensure_db
from web import app

__all__ = ["app", "auth", "routes", "lookup"]

# ---------------------------------------------------------------------- main
def free_port(start):
    for p in range(start, start + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", p)) != 0:
                return p
    return start


def get_local_ip():
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"


if __name__ == "__main__":
    ensure_db()
    port = free_port(START_PORT)
    lip = get_local_ip()
    local_url = f"http://localhost:{port}"
    mobile_url = f"http://{lip}:{port}"
    print("=" * 60)
    print(" Attendance site is running")
    print(f" Open on this PC:    {local_url}")
    print(f" Open on your phone: {mobile_url}  (connected to same Wi-Fi)")
    print(f" Database file:      {DB_FILE}")
    print(" Close this window (or press Ctrl+C) to stop the site.")
    print("=" * 60)
    if "--no-browser" not in sys.argv:
        threading.Timer(1.2, lambda: webbrowser.open(local_url)).start()
    app.run(host=HOST, port=port, debug=False)
