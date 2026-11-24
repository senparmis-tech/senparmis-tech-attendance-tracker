"""
JSON endpoints the Android app needs on top of the ones in routes.py.

The web pages archive and restore subjects with form posts that answer with a redirect, which
an app can't use, so these do the same job and answer with JSON. The permission rules live in
store.archive_subject / store.unarchive_subject: an admin can archive any subject, a teacher
only their own, and a section monitor none.
"""
from flask import jsonify, request

from helpers import log_change
from store import archive_subject, unarchive_subject
from web import app


def _subject_and_note():
    body = request.get_json(silent=True) or {}
    return str(body.get("subject", "")).strip(), str(body.get("note", "")).strip()


@app.route("/api/subject_archive", methods=["POST"])
def api_subject_archive():
    name, note = _subject_and_note()
    if not name:
        return jsonify(ok=False, error="Choose a subject first."), 400
    try:
        archive_subject(name, note)
    except ValueError as err:
        return jsonify(ok=False, error=str(err)), 400
    log_change("Subject archived", name,
               f"Subject marked as completed/archived. {note}" if note else "Subject marked as completed/archived")
    return jsonify(ok=True, message=f"Archived '{name}'.")


@app.route("/api/subject_unarchive", methods=["POST"])
def api_subject_unarchive():
    name, _note = _subject_and_note()
    if not name:
        return jsonify(ok=False, error="Choose a subject first."), 400
    try:
        unarchive_subject(name)
    except ValueError as err:
        return jsonify(ok=False, error=str(err)), 400
    log_change("Subject restored", name, "Subject restored to active")
    return jsonify(ok=True, message=f"Restored '{name}'.")
