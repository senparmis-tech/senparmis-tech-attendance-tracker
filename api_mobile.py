"""
JSON endpoints the Android app needs on top of the ones in routes.py.

The web pages change data with form posts that answer with a redirect, which an app can't use,
so these do the same jobs and answer with JSON. The permission rules live in the store.py
functions they call, so the app follows the same teacher / monitor / admin rules as the website.
"""
from flask import g, jsonify, request, session

import auth
from helpers import (clean_name, clean_sheet_name, log_change, parse_iso, read_log,
                     safe_text, short_list)
from routes import pick_section, pick_subject
from store import (add_grade_item, add_section, add_students, add_subject, archive_subject,
                   assign_subject_teacher, backup_workbook, create_teacher, delete_date,
                   delete_grade_item, delete_section, delete_subject, delete_teacher,
                   ensure_db, get_teacher, is_subject_archived, list_all_sections,
                   list_periods, list_subjects_with_owners, list_teachers, load_data,
                   lock_period, remove_student, rename_section, save_grade_weights,
                   set_weights_lock, student_stats, suggest_next_period, unarchive_subject,
                   unlock_period, update_period, update_student_profile,
                   update_teacher_password)
from web import app

# Section monitors may use these too (the same things they can do on the website).
auth.MONITOR_ALLOWED_ENDPOINTS.update({
    "api_students", "api_students_add", "api_students_remove", "api_student_profile",
    "api_date_delete", "api_log",
})


# ------------------------------------------------------------------ helpers
def _body():
    return request.get_json(silent=True) or {}


def _s(body, key):
    return str(body.get(key) or "").strip()


def _sec(body):
    return clean_name(_s(body, "section")) or None


def _fail(msg, code=400):
    return jsonify(ok=False, error=msg), code


def _where(subject, section):
    return f"{subject} ({section})" if section else subject


# ------------------------------------------------------------------ archive
def _subject_and_note():
    body = _body()
    return str(body.get("subject", "")).strip(), str(body.get("note", "")).strip()


@app.route("/api/subject_archive", methods=["POST"])
def api_subject_archive():
    name, note = _subject_and_note()
    if not name:
        return _fail("Choose a subject first.")
    try:
        archive_subject(name, note)
    except ValueError as err:
        return _fail(str(err))
    log_change("Subject archived", name,
               f"Subject marked as completed/archived. {note}" if note else "Subject marked as completed/archived")
    return jsonify(ok=True, message=f"Archived '{name}'.")


@app.route("/api/subject_unarchive", methods=["POST"])
def api_subject_unarchive():
    name, _note = _subject_and_note()
    if not name:
        return _fail("Choose a subject first.")
    try:
        unarchive_subject(name)
    except ValueError as err:
        return _fail(str(err))
    log_change("Subject restored", name, "Subject restored to active")
    return jsonify(ok=True, message=f"Restored '{name}'.")


# ------------------------------------------------------------------ subjects and sections
@app.route("/api/subject_add", methods=["POST"])
def api_subject_add():
    b = _body()
    name = clean_sheet_name(_s(b, "name"))
    sec_name = clean_sheet_name(_s(b, "section_name")) or None
    copy_from = _s(b, "copy_from")
    if not name or name.lower() == "guide":
        return _fail("Please enter a different subject name.")
    try:
        n = add_subject(name, copy_from, section_name=sec_name)
    except ValueError as err:
        return _fail(str(err))
    log_change("Subject added", name, f"Copied {n} students from {copy_from}" if n else "New empty subject")
    return jsonify(ok=True, message=f"Created {name}.")


@app.route("/api/subject_delete", methods=["POST"])
def api_subject_delete():
    name = _s(_body(), "subject")
    try:
        delete_subject(name)
    except ValueError as err:
        return _fail(str(err))
    log_change("Subject deleted", name, "Subject and records removed")
    return jsonify(ok=True)


@app.route("/api/section_add", methods=["POST"])
def api_section_add():
    b = _body()
    subject, sec_name = _s(b, "subject"), clean_sheet_name(_s(b, "section"))
    copy_from = _s(b, "copy_from") or None
    if not subject or not sec_name:
        return _fail("Enter a section name (e.g. BSCS-1B).")
    try:
        n = add_section(subject, sec_name, copy_from_section=copy_from)
    except ValueError as err:
        return _fail(str(err))
    log_change("Section added", f"{subject} ({sec_name})",
               f"Copied {n} students from {copy_from}" if n else "New empty section")
    return jsonify(ok=True, section=sec_name)


@app.route("/api/section_rename", methods=["POST"])
def api_section_rename():
    b = _body()
    subject, old, new = _s(b, "subject"), _s(b, "old_section"), clean_sheet_name(_s(b, "new_section"))
    try:
        updated = rename_section(subject, old, new)
    except ValueError as err:
        return _fail(str(err))
    log_change("Section renamed", subject, f"{old} → {updated}")
    return jsonify(ok=True, section=updated)


@app.route("/api/section_delete", methods=["POST"])
def api_section_delete():
    b = _body()
    subject, sec = _s(b, "subject"), _s(b, "section")
    try:
        delete_section(subject, sec)
    except ValueError as err:
        return _fail(str(err))
    log_change("Section deleted", f"{subject} ({sec})", "Section and its records removed")
    return jsonify(ok=True)


# ------------------------------------------------------------------ students
@app.route("/api/students", methods=["GET"])
def api_students():
    req_sub = request.args.get("subject", "").strip()
    is_arch = is_subject_archived(req_sub) if req_sub else False
    data = load_data(include_archived=is_arch)
    subjects, subject = pick_subject(data)
    if not subject:
        return _fail("No subjects found.", 404)
    sec_names, section, sd = pick_section(data.get(subject))
    period = sd.get("period") or {}
    rows = [{
        "row": s["row"], "name": s["name"], "student_no": s.get("student_no", ""),
        "guardian_name": s.get("guardian_name", ""), "guardian_phone": s.get("guardian_phone", ""),
        "email": s.get("email", ""), "address": s.get("address", ""), "rate": s["rate"],
    } for s in student_stats(sd)]
    return jsonify(ok=True, subject=subject, section=section, section_names=sec_names,
                   is_archived=is_subject_archived(subject), term=period.get("label"),
                   term_locked=bool(period.get("locked")), rows=rows)


@app.route("/api/students_add", methods=["POST"])
def api_students_add():
    b = _body()
    names = []
    raw = b.get("names")
    for line in (raw if isinstance(raw, list) else str(raw or "").splitlines()):
        n = safe_text(str(line))
        if n and n.lower() not in [x.lower() for x in names]:
            names.append(n)
    subject, section = _s(b, "subject"), _sec(b)
    if not names or not subject:
        return _fail("Enter at least one student name.")
    try:
        added, skipped = add_students([subject], names, section=section)
    except ValueError as err:
        return _fail(str(err))
    if added:
        log_change("Students added", _where(subject, section),
                   short_list(names, 30) + (" · Already on the list: " + short_list(skipped, 10) if skipped else ""))
    return jsonify(ok=True, added=added, skipped=skipped)


@app.route("/api/students_remove", methods=["POST"])
def api_students_remove():
    b = _body()
    subject, section = _s(b, "subject"), _sec(b)
    name = clean_name(_s(b, "name"))
    row = b.get("row") if isinstance(b.get("row"), int) else None
    everywhere = bool(b.get("everywhere"))
    try:
        removed = remove_student(subject, row, name, everywhere, section=section)
    except ValueError as err:
        return _fail(str(err))
    if not removed:
        return _fail(f"{name} was not found.", 404)
    log_change("Student removed", "All subjects" if everywhere else _where(subject, section), name)
    return jsonify(ok=True)


@app.route("/api/student_profile", methods=["POST"])
def api_student_profile():
    b = _body()
    old_name = clean_name(_s(b, "old_name"))
    try:
        saved = update_student_profile(
            old_name, new_name=clean_name(_s(b, "name")) or old_name, student_no=_s(b, "student_no"),
            guardian_name=_s(b, "guardian_name"), guardian_phone=_s(b, "guardian_phone"),
            email=_s(b, "email"), address=_s(b, "address"))
    except ValueError as err:
        return _fail(str(err))
    log_change("Student profile updated", _s(b, "subject"), f"{saved} (ID: {_s(b, 'student_no') or '—'})")
    return jsonify(ok=True, name=saved)


@app.route("/api/date_delete", methods=["POST"])
def api_date_delete():
    b = _body()
    subject, section = _s(b, "subject"), _sec(b)
    d = parse_iso(_s(b, "date"))
    if not d:
        return _fail("That date was not understood.")
    try:
        ensure_db()
        backup_workbook("before_delete_date")
        marks, topic = delete_date(subject, d, section=section)
    except ValueError as err:
        return _fail(str(err))
    log_change("Date deleted", subject, f"{d.isoformat()}" + (f" ({topic})" if topic else "")
               + f" · {marks} mark(s) removed")
    return jsonify(ok=True)


# ------------------------------------------------------------------ grade setup
@app.route("/api/grade_weights", methods=["POST"])
def api_grade_weights():
    b = _body()
    subject, section = _s(b, "subject"), _sec(b)
    try:
        save_grade_weights(subject, section, b.get("exam"), b.get("quiz"), b.get("activity"))
    except ValueError as err:
        return _fail(str(err))
    log_change("Grade weights updated", _where(subject, section),
               f"Exam {b.get('exam')}% · Quiz {b.get('quiz')}% · Activity {b.get('activity')}%")
    return jsonify(ok=True)


@app.route("/api/grade_lock", methods=["POST"])
def api_grade_lock():
    b = _body()
    subject, section, on = _s(b, "subject"), _sec(b), bool(b.get("locked"))
    try:
        set_weights_lock(subject, section, on)
    except ValueError as err:
        return _fail(str(err))
    log_change("Grade weights " + ("locked" if on else "unlocked"), _where(subject, section), "")
    return jsonify(ok=True)


@app.route("/api/grade_item_add", methods=["POST"])
def api_grade_item_add():
    b = _body()
    subject, section = _s(b, "subject"), _sec(b)
    category, title, max_score = _s(b, "category"), _s(b, "title"), _s(b, "max_score")
    try:
        add_grade_item(subject, section, category, title, max_score, date_str=_s(b, "date"))
    except ValueError as err:
        return _fail(str(err))
    log_change("Grade item added", _where(subject, section), f"{category.capitalize()}: {title} (max {max_score})")
    return jsonify(ok=True)


@app.route("/api/grade_item_delete", methods=["POST"])
def api_grade_item_delete():
    b = _body()
    subject, section = _s(b, "subject"), _sec(b)
    try:
        title = delete_grade_item(subject, section, _s(b, "item_id"))
    except ValueError as err:
        return _fail(str(err))
    log_change("Grade item deleted", _where(subject, section), title)
    return jsonify(ok=True)


# ------------------------------------------------------------------ terms
@app.route("/api/periods", methods=["GET"])
def api_periods():
    subject = request.args.get("subject", "").strip()
    section = clean_name(request.args.get("section", "")) or None
    if not subject:
        return _fail("Choose a subject first.")
    try:
        periods = list_periods(subject, section)
    except ValueError as err:
        return _fail(str(err))
    current = next((p for p in reversed(periods) if not p["locked"]), None)
    sem, trm = suggest_next_period(current["semester"], current["term"]) if current else ("", "")
    return jsonify(ok=True, subject=subject, section=section or "", periods=periods,
                   current_id=current["id"] if current else None,
                   next_semester=sem, next_term=trm, is_admin=bool(getattr(g, "is_admin", False)))


@app.route("/api/period_edit", methods=["POST"])
def api_period_edit():
    b = _body()
    subject, section = _s(b, "subject"), _sec(b)
    try:
        p = update_period(subject, section, _s(b, "semester"), _s(b, "term"),
                          b.get("period_id") if isinstance(b.get("period_id"), int) else None)
    except ValueError as err:
        return _fail(str(err))
    log_change("Term renamed", _where(subject, section), f"Term updated to: {p['label']}")
    return jsonify(ok=True)


@app.route("/api/period_lock", methods=["POST"])
def api_period_lock():
    b = _body()
    subject, section = _s(b, "subject"), _sec(b)
    try:
        res = lock_period(subject, section, _s(b, "semester"), _s(b, "term"),
                          _s(b, "next_semester"), _s(b, "next_term"))
    except ValueError as err:
        return _fail(str(err))
    log_change("Term locked", _where(subject, section),
               f"{res['locked']} locked ({res['n_dates']} date(s), {res['n_items']} graded item(s)) · "
               f"New term: {res['next']}")
    return jsonify(ok=True, message=f"Locked {res['locked']}. {res['next']} is now open.")


@app.route("/api/period_unlock", methods=["POST"])
def api_period_unlock():
    b = _body()
    subject, section = _s(b, "subject"), _sec(b)
    try:
        p = unlock_period(subject, section, b.get("period_id"))
    except ValueError as err:
        return _fail(str(err))
    log_change("Term reopened", _where(subject, section), f"{p['label']} was unlocked")
    return jsonify(ok=True)


# ------------------------------------------------------------------ activity log
@app.route("/api/log", methods=["GET"])
def api_log():
    shown, total = read_log()
    if getattr(g, "is_monitor", False):
        sec = (getattr(g, "monitor_sec_name", "") or "").lower()
        sub = (getattr(g, "monitor_sub_name", "") or "").lower()
        who = (getattr(g, "teacher_name", "") or "").lower()
        shown = [e for e in shown
                 if (sec and f"({sec})" in (e.get("subject") or "").lower())
                 or (sub and sec and sub in (e.get("subject") or "").lower() and sec in (e.get("subject") or "").lower())
                 or (who and who in (e.get("who") or "").lower())]
        total = len(shown)
    return jsonify(ok=True, total=total, entries=[
        {"when": e.get("when", ""), "action": e.get("action", ""), "subject": e.get("subject", ""),
         "detail": e.get("detail", ""), "who": e.get("who", "")} for e in shown])


# ------------------------------------------------------------------ teachers and access
@app.route("/api/teachers", methods=["GET"])
def api_teachers():
    is_adm = bool(getattr(g, "is_admin", False))
    return jsonify(
        ok=True, is_admin=is_adm, self_id=getattr(g, "teacher_id", None),
        teachers=list_teachers() if is_adm else [],
        subjects=list_subjects_with_owners() if is_adm else [],
        sections=list_all_sections() if is_adm else [])


def _admin_only():
    if not getattr(g, "is_admin", False):
        return _fail("Only an admin can do that.", 403)
    return None


@app.route("/api/teacher_add", methods=["POST"])
def api_teacher_add():
    denied = _admin_only()
    if denied:
        return denied
    b = _body()
    username, display = _s(b, "username"), _s(b, "display_name")
    is_adm, is_mon = bool(b.get("is_admin")), bool(b.get("is_monitor"))
    mon_sec = b.get("monitor_section_id") if is_mon else None
    if is_mon and not mon_sec:
        return _fail("Pick the section this monitor will manage.")
    try:
        create_teacher(username, display, _s(b, "password"), is_admin=is_adm, monitor_section_id=mon_sec)
    except ValueError as err:
        return _fail(str(err))
    role = "admin" if is_adm else ("section monitor" if is_mon else "teacher")
    log_change("Teacher added", "", f"Created {role} '{display or username}' ({username})")
    return jsonify(ok=True)


@app.route("/api/teacher_password", methods=["POST"])
def api_teacher_password():
    b = _body()
    try:
        tid = int(b.get("teacher_id"))
    except (TypeError, ValueError):
        return _fail("Invalid teacher account.")
    if not getattr(g, "is_admin", False) and tid != getattr(g, "teacher_id", None):
        return _fail("You can only change your own password.", 403)
    try:
        t = get_teacher(tid)
        update_teacher_password(tid, _s(b, "password"))
        if tid == getattr(g, "teacher_id", None):          # keep this sign-in valid after the change
            session["pv"] = auth.pw_version("teacher_db", get_teacher(tid)["password_hash"])
    except ValueError as err:
        return _fail(str(err))
    log_change("Password updated", "", f"Updated password for '{t['username'] if t else tid}'")
    return jsonify(ok=True)


@app.route("/api/teacher_delete", methods=["POST"])
def api_teacher_delete():
    denied = _admin_only()
    if denied:
        return denied
    try:
        tid = int(_body().get("teacher_id"))
        if tid == getattr(g, "teacher_id", None):
            return _fail("You cannot delete the account you are signed in with.")
        t = get_teacher(tid)
        delete_teacher(tid)
    except (TypeError, ValueError) as err:
        return _fail(str(err) or "Invalid teacher account.")
    log_change("Teacher removed", "", f"Deleted teacher '{t['username'] if t else tid}'")
    return jsonify(ok=True)


@app.route("/api/teacher_assign", methods=["POST"])
def api_teacher_assign():
    denied = _admin_only()
    if denied:
        return denied
    b = _body()
    subject, tid = _s(b, "subject"), b.get("teacher_id")
    try:
        assign_subject_teacher(subject, tid)
    except ValueError as err:
        return _fail(str(err))
    log_change("Subject assigned", subject, f"Owner set to teacher id {tid or 'none (admin / shared)'}")
    return jsonify(ok=True)
