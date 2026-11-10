"""
Application settings and file paths.
"""
import os

HOST = "0.0.0.0"            # "0.0.0.0" allows phones and other devices on your Wi-Fi to open the site
START_PORT = 5000
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
# Data and secret files live next to the code unless ATTENDANCE_DATA_DIR points somewhere else
# (the automated tests use this so they never touch the real workbook).
DATA_DIR = os.environ.get("ATTENDANCE_DATA_DIR", "").strip() or BASE_DIR
XLSX = os.path.join(DATA_DIR, "attendance_records.xlsx")

SAMPLE_SUBJECTS = ["College Algebra", "MMW"]
SAMPLE_STUDENTS = ["Sample Student A", "Sample Student B", "Sample Student C"]
LOW_RATE = 0.80             # attendance rates below this are shown in red

# AI sheet scanning (optional). The key comes from the ANTHROPIC_API_KEY environment
# variable or from a file called api_key.txt next to this script.
API_KEY_FILE = os.path.join(DATA_DIR, "api_key.txt")
SUBJECT_IMG_DIR = os.path.join(DATA_DIR, "subject_images")
AI_MODEL = os.environ.get("ATTENDANCE_MODEL", "claude-sonnet-5-5")          # used with Claude keys
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")         # used with Gemini keys
GEMINI_FALLBACKS = [m.strip() for m in os.environ.get("GEMINI_FALLBACK_MODEL", "gemini-flash-lite-latest").split(",") if m.strip()]
PASSWORD_FILE = os.path.join(DATA_DIR, "passwords.txt")    # lines: teacher=...  and (optional) student=...
SECRET_FILE = os.path.join(DATA_DIR, "secret_key.txt")      # made automatically; keeps sign-ins private
MIN_PASSWORD = 8
OPEN_MODE = False        # On PythonAnywhere, always False to require password sign-in
# Backups: a copy of the workbook is saved here automatically. To keep them in Google Drive,
# set the environment variable ATTENDANCE_BACKUP_DIR to a folder inside your Google Drive folder.
BACKUP_DIR = os.environ.get("ATTENDANCE_BACKUP_DIR", "").strip() or os.path.join(DATA_DIR, "backups")
BACKUP_EVERY_MIN = 10       # at most one timestamped copy per this many minutes of saving
BACKUP_KEEP = {"auto": 60, "before_delete_date": 30}   # how many timestamped copies of each kind to keep
# Google Meet CSV import
MEET_PRESENT_PCT = 0.75     # present if the student was in the call at least this share of the meeting
MEET_ALIAS_FILE = os.path.join(DATA_DIR, "meet_aliases.json")   # remembers "Meet name -> class-list name"
MAX_CSV = 1024 * 1024
LOG_FILE = os.path.join(DATA_DIR, "changes_log.jsonl")     # the "Changes log" page reads this file
LOG_MAX_SHOWN = 500
MAX_UPLOAD = 12 * 1024 * 1024
MAX_IMAGES = 6

TOPIC_ROW, HEADER_ROW, FIRST_ROW = 3, 4, 5
FIRST_DATE_COL = 8          # column H
MAX_COL, MAX_ROW = 200, 300
CODES = {"p": "Present", "x": "Absent", "l": "Late", "e": "Excused", "r": "Recited"}
