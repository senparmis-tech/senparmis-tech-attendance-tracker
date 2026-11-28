#!/usr/bin/env python3
"""
set_password.py — change the teacher or student password in the SQLite database
the app actually uses.

The new password is NEVER accepted as a command-line argument: it is typed at an
interactive prompt (hidden input) and asked twice for confirmation. Minimum
length comes from config.MIN_PASSWORD (8 characters).

Usage (run it where the app's data directory lives / ATTENDANCE_DATA_DIR points):
    python set_password.py student
    python set_password.py teacher            # defaults to the "admin" account
    python set_password.py teacher <username>

Exit code 0 on success, 1 on any failure.
"""
import getpass
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import db  # noqa: E402
import store  # noqa: E402
from config import MIN_PASSWORD  # noqa: E402
from werkzeug.security import generate_password_hash  # noqa: E402


def _read_new_password(label):
    """Prompt twice for a new password and return it, or None if unusable."""
    pwd = getpass.getpass(f"New {label} password (at least {MIN_PASSWORD} characters): ")
    if len(pwd) < MIN_PASSWORD:
        print(f"Password must be at least {MIN_PASSWORD} characters.")
        return None
    again = getpass.getpass(f"Repeat new {label} password: ")
    if pwd != again:
        print("Passwords do not match.")
        return None
    return pwd


def change_student_password():
    if not store.db_ready():
        print("No database found yet. Open the app once (or the /setup page) first.")
        return False
    new_password = _read_new_password("student")
    if not new_password:
        return False
    store.set_student_password(new_password)
    print("Student password updated.")
    return True


def change_teacher_password(username):
    new_password = _read_new_password(f"teacher '{username}'")
    if not new_password:
        return False

    # Look up teacher by username only (no password check)
    teacher = store.verify_teacher(username, by_username=True)
    if not teacher:
        print(f"No teacher account named '{username}' exists in the database.")
        # Offer to create it if this is the default 'admin' account
        if username.lower() == "admin":
            print("Would you like to create an admin account now? (y/N)")
            try:
                ans = input().strip().lower()
            except EOFError:
                ans = "n"
            if ans == "y":
                print(f"Creating admin account '{username}'...")
                try:
                    store.create_teacher(username, "Administrator", new_password, is_admin=True)
                    print(f"Admin account '{username}' created successfully.")
                    return True
                except ValueError as e:
                    print(f"Failed to create admin account: {e}")
                    return False
            else:
                print("Admin account not created.")
                return False
        return False

    store.update_teacher_password(teacher["id"], new_password)
    print(f"Password updated for teacher '{username}'.")
    return True


def main():
    if len(sys.argv) < 2 or sys.argv[1].lower() not in ("student", "teacher"):
        print("Usage:\n  python set_password.py student\n  python set_password.py teacher [username]")
        return 1
    store.ensure_db()
    if sys.argv[1].lower() == "student":
        ok = change_student_password()
    else:
        username = sys.argv[2] if len(sys.argv) > 2 else "admin"
        ok = change_teacher_password(username)
    if not ok:
        return 1
    print("Restart the app if it is running, then sign in with the new password.")
    return 0


if __name__ == "__main__":
    sys.exit(main())