"""
Page and JSON API routes for marking, records, scanning, Meet import, students, log, and files.
"""
import base64
import io
import os
import re
import subprocess
import sys
from datetime import date, datetime, timedelta

from flask import flash, jsonify, redirect, render_template, request, send_file, url_for

from ai_scan import AIError, call_ai, get_api_key, normalize_scan, provider_of
from config import (API_KEY_FILE, LOG_FILE, LOW_RATE, MAX_CSV, MAX_IMAGES,
                    MAX_UPLOAD, MEET_PRESENT_PCT, SUBJECT_IMG_DIR, DB_FILE)
from excel_io import build_workbook
from store import (FileLocked, add_section, add_students, add_subject,
                   apply_marks, backup_workbook, delete_date, delete_section,
                   delete_subject, ensure_db, get_subject_image_file,
                   load_data, remove_student, remove_subject_image,
                   rename_section, student_stats, subject_image_url)
from helpers import (LETTER, clean_name, clean_sheet_name, log_change,
                     parse_iso, read_log, safe_text, short_list)
from meet_import import match_roster, name_tokens, parse_meet_csv, read_aliases, write_aliases
from web import app

LOCKED_MSG = ("The database is busy right now, so the change was not saved. "
              "Wait a few seconds and try again.")


def make_tabs(subjects, current, endpoint, **extra):
    return [{"name": s, "active": s == current, "url": url_for(endpoint, subject=s, **extra)} for s in subjects]


def make_section_tabs(section_names, current_section, subject, endpoint, **extra):
    if not subject or not section_names:
        return []
    return [{"name": sec, "active": sec == current_section,
             "url": url_for(endpoint, subject=subject, section=sec, **extra)} for sec in section_names]


def pick_subject(data):
    subjects = list(data.keys())
    wanted = request.args.get("subject") or request.form.get("subject")
    return subjects, (wanted if wanted in data else (subjects[0] if subjects else None))


def pick_section(sd):
    if not sd:
        return [], None, {"students": [], "dates": [], "cells": {}}
    secs_map = sd.get("sections") or {sd.get("section", "BSCS-1A"): sd}
    sec_names = sd.get("section_names") or list(secs_map.keys())
    wanted = (request.args.get("section") or request.form.get("section") or "").strip()
    matched = next((s for s in sec_names if s.lower() == wanted.lower()), None) if wanted else None
    cur = matched or (sec_names[0] if sec_names else None)
    return sec_names, cur, (secs_map[cur] if cur else sd)


@app.errorhandler(FileLocked)
def handle_locked(_e):
    if request.path.startswith("/api/"):
        return jsonify(ok=False, error=LOCKED_MSG), 423
    flash(LOCKED_MSG, "err")
    return redirect(request.referrer or url_for("dashboard"))


@app.route("/")
def dashboard():
    data = load_data()
    today = date.today()
    cards = []
    for name, sd in data.items():
        stats = student_stats(sd)
        rated = [s for s in stats if s["rate"] is not None]
        avg = sum(s["rate"] for s in rated) / len(rated) if rated else None
        today_counts, absent = None, []
        tcol = next((d["col"] for d in sd["dates"] if d["date"] == today), None)
        if tcol is not None:
            today_counts = {"p": 0, "x": 0, "l": 0, "e": 0, "r": 0}
            for s in sd["students"]:
                code = sd["cells"].get((s["row"], tcol), "")
                if code and code in today_counts:
                    today_counts[code] += 1
                if code == "x":
                    absent.append(s["name"])
        watch = sorted([s for s in rated if s["rate"] < LOW_RATE], key=lambda s: s["rate"])
        cards.append({"name": name, "n_students": len(stats), "held": len(sd["dates"]), "avg": avg,
                      "today": today_counts, "absent_today": absent, "watch": watch,
                      "image_url": subject_image_url(name)})
    return render_template("dashboard.html", page="dashboard", cards=cards, low=LOW_RATE, today_iso=today.isoformat(),
                           today_label=today.strftime("%A, %B %d, %Y").replace(" 0", " "))


@app.route("/mark")
def mark():
    data = load_data()
    subjects, subject = pick_subject(data)
    sec_names, section, sd = pick_section(data.get(subject))
    d = parse_iso(request.args.get("date"))          # no date unless you pick one
    today = date.today()
    extra = {"date": d.isoformat()} if d else {}
    today_url = url_for("mark", subject=subject, section=section, date=today.isoformat()) if subject else ""
    ctx = dict(page="mark", subject=subject, section=section, section_names=sec_names,
               tabs=make_tabs(subjects, subject, "mark", **extra),
               section_tabs=make_section_tabs(sec_names, section, subject, "mark", **extra),
               students=[], date_iso=d.isoformat() if d else "", recorded=False, topic="", today_url=today_url)
    if subject:
        col = next((x["col"] for x in sd["dates"] if x["date"] == d), None) if d else None
        topic = next((x["topic"] for x in sd["dates"] if x["date"] == d), "") if d else ""
        ctx["students"] = [{"row": s["row"], "name": s["name"],
                            "code": (sd["cells"].get((s["row"], col), "") if col else "") or "p"}
                           for s in sd["students"]]
        ctx.update(recorded=col is not None, topic=topic, subject_img_url=subject_image_url(subject),
                   base_url=url_for("mark", subject=subject, section=section), save_url=url_for("api_save"),
                   prev_url=url_for("mark", subject=subject, section=section, date=(d - timedelta(days=1)).isoformat()) if d else "",
                   next_url=url_for("mark", subject=subject, section=section, date=(d + timedelta(days=1)).isoformat()) if d else "",
                   date_label=d.strftime("%A, %B %d, %Y").replace(" 0", " ") if d else "")
    return render_template("mark.html", **ctx)


@app.route("/api/save", methods=["POST"])
def api_save():
    body = request.get_json(silent=True) or {}
    d = parse_iso(body.get("date"))
    items = body.get("marks")
    if not d or not isinstance(items, list) or len(items) > 1000:
        return jsonify(ok=False, error="That request was not understood."), 400
    clean = [{"row": it.get("row"), "name": it.get("name"), "code": it.get("code"), "clear": bool(it.get("clear"))}
             for it in items if isinstance(it, dict)]
    new_raw = body.get("new_students")
    new_names = [str(n)[:80] for n in new_raw[:100]] if isinstance(new_raw, list) else []
    section = clean_name(str(body.get("section") or "")) or None
    try:
        res = apply_marks(str(body.get("subject", "")), d, str(body.get("topic", ""))[:120],
                          clean, new_names, section=section)
    except ValueError as err:
        return jsonify(ok=False, error=str(err)), 400
    subject = str(body.get("subject", ""))
    sec_tag = f" ({section})" if section else ""
    counts = {"p": 0, "x": 0, "l": 0, "e": 0, "r": 0, "": 0}
    for name, old, new in res["changes"]:
        if new in counts:
            counts[new] += 1
        elif new:
            counts["p"] += 1
    kind = {"scan": "Scan", "meet": "Meet import"}.get(body.get("source"), "Attendance")
    action = f"{kind} {'saved' if res['created'] else 'updated'}"
    detail = (f"{d.isoformat()}: Present {counts['p']} · Absent {counts['x']} · Late {counts['l']} · Excused {counts['e']} · Recited {counts['r']}"
              + (f" · Blank {counts['']}" if counts[""] else ""))
    topic = safe_text(str(body.get("topic", ""))[:120])
    if topic:
        detail += f" · Topic: {topic}"
    if res["created"]:
        absent = [n for n, o, c in res["changes"] if c == "x"]
        if absent:
            detail += " · Absent: " + short_list(absent, 15)
    else:
        diffs = [f"{n} {LETTER[o]}→{LETTER[c]}" for n, o, c in res["changes"] if o != c]
        detail += " · Changed: " + (short_list(diffs, 25) if diffs else "nothing (same as before)")
    if res["added"]:
        detail += " · New students added: " + short_list(res["added"], 15)
    log_change(action, subject + sec_tag, detail)
    return jsonify(ok=True, saved=res["saved"])


@app.errorhandler(413)
def too_big(_e):
    return jsonify(ok=False, error="That photo is too large. Try a smaller one."), 413


@app.route("/scan")
def scan():
    data = load_data()
    subjects, subject = pick_subject(data)
    sec_names, section, sd = pick_section(data.get(subject))
    return render_template(
        "scan.html", page="scan", subject=subject, section=section,
        tabs=make_tabs(subjects, subject, "scan"),
        section_tabs=make_section_tabs(sec_names, section, subject, "scan"),
        students=[{"name": s["name"], "row": s["row"]} for s in sd["students"]],
        recorded=[x["date"].isoformat() for x in sd["dates"]], today=date.today().isoformat(),
        has_key=bool(get_api_key()), provider=provider_of(get_api_key()) if get_api_key() else "",
        records_url=url_for("records", subject=subject, section=section) if subject else "",
        scan_url=url_for("api_scan"), save_url=url_for("api_save"), key_url=url_for("api_set_key"),
        max_images=MAX_IMAGES, pct=int(MEET_PRESENT_PCT * 100))


@app.route("/api/scan", methods=["POST"])
def api_scan():
    """Read photos/screenshots of an attendance record. This only READS: nothing is saved here."""
    data = load_data()
    subject = request.form.get("subject", "")
    files = [f for f in request.files.getlist("image") if f]
    if subject not in data or not files:
        return jsonify(ok=False, error="Choose a subject and at least one photo first."), 400
    if len(files) > MAX_IMAGES:
        return jsonify(ok=False, error=f"Please use at most {MAX_IMAGES} photos at a time."), 400
    images = []
    for f in files:
        raw = f.read(MAX_UPLOAD + 1)
        if not raw or len(raw) > MAX_UPLOAD:
            return jsonify(ok=False, error="One of the photos is empty or too large."), 400
        media = f.mimetype if f.mimetype in ("image/jpeg", "image/png", "image/webp", "image/gif") else "image/jpeg"
        images.append((base64.b64encode(raw).decode("ascii"), media))
    _, _, sd = pick_section(data[subject])
    roster = [s["name"] for s in sd["students"]]
    try:
        result = call_ai(images, roster)
    except AIError as err:
        return jsonify(ok=False, code=err.code, error=err.message), (400 if err.code in ("no_key", "bad_key") else 502)
    return jsonify(ok=True, result=normalize_scan(result, roster))


@app.route("/api/set_key", methods=["POST"])
def api_set_key():
    # Only the computer running the site may save the key (the site may be open to the network).
    if request.remote_addr not in ("127.0.0.1", "::1"):
        return jsonify(ok=False, error="For safety, the key can only be saved from the computer that runs the site. "
                                       "Or create a file named api_key.txt next to app.py containing the key."), 403
    key = str((request.get_json(silent=True) or {}).get("key", "")).strip().strip("\"'").strip()
    if not re.fullmatch(r"[A-Za-z0-9_.\-]{30,}", key):
        return jsonify(ok=False, error="That doesn't look like an API key. Paste only the key itself, with no spaces or quotes. "
                                       "A Claude key starts with sk-ant- and a Gemini key starts with AIza or AQ."), 400
    try:
        with open(API_KEY_FILE, "w", encoding="utf-8") as fh:
            fh.write(key)
    except OSError:
        return jsonify(ok=False, error="Could not save the key file in this folder."), 500
    return jsonify(ok=True)


@app.route("/records")
def records():
    data = load_data()
    subjects, subject = pick_subject(data)
    sec_names, section, sd = pick_section(data.get(subject))
    rows, dates = [], []
    if subject:
        dates = [{"label": x["date"].strftime("%b %d").replace(" 0", " "), "iso": x["date"].isoformat(),
                  "topic": x["topic"]} for x in sd["dates"]]
        for s in student_stats(sd):
            s["codes"] = [sd["cells"].get((s["row"], x["col"]), "") for x in sd["dates"]]
            rows.append(s)
    return render_template("records.html", page="records", subject=subject, section=section,
                           rows=rows, dates=dates, low=LOW_RATE,
                           tabs=make_tabs(subjects, subject, "records"),
                           section_tabs=make_section_tabs(sec_names, section, subject, "records"))


GRID_COLS = 25               # date columns in the printed grid (blank ones are left for future days)
DATES_PER_PAGE = 23         # date columns on one printed page (more days continue on the next page)
FORM_ROWS = 30              # numbered rows on the printed sheet, like the teacher's form
PRINT_MARK = {"x": "X", "r": "R", "e": "E"}   # everything else (p, l, unmarked) prints blank = present


@app.route("/print")
def print_sheet():
    """A printable copy of the attendance in the teacher's paper-form layout."""
    data = load_data()
    subjects, subject = pick_subject(data)
    if not subject:
        flash("Add a subject first.", "err")
        return redirect(url_for("dashboard"))
    sec_names, section, sd = pick_section(data[subject])
    dates, students, cells = sd["dates"], sd["students"], sd["cells"]
    unmarked = []
    for dd in dates:
        n = sum(1 for s in students if not cells.get((s["row"], dd["col"])))
        if n:
            unmarked.append({"label": f"{dd['date'].month}/{dd['date'].day}", "n": n})
    codes = [cells.get((s["row"], dd["col"]), "") for s in students for dd in dates]
    # Totals only count days that have at least one mark. Like the paper, a blank counts as present.
    held_dates = [dd for dd in dates if any(cells.get((s["row"], dd["col"])) for s in students)]
    skipped = [f"{dd['date'].month}/{dd['date'].day}" for dd in dates if dd not in held_dates]
    held = len(held_dates)
    totals = {}
    for s in students:
        got = [cells.get((s["row"], dd["col"]), "") for dd in held_dates]
        totals[s["row"]] = (f"{held - got.count('x') - got.count('e')}/{held}", got.count("r"))
    pages = []
    if students:
        for i in range(0, max(len(dates), 1), DATES_PER_PAGE):
            chunk = dates[i:i + DATES_PER_PAGE]
            rows = [{"n": n, "name": s["name"], "total": totals[s["row"]][0], "rec": totals[s["row"]][1],
                     "marks": [PRINT_MARK.get(cells.get((s["row"], d["col"]), ""), "") for d in chunk]}
                    for n, s in enumerate(students, 1)]
            for n in range(len(students) + 1, max(FORM_ROWS, len(students)) + 1):
                rows.append({"n": n, "name": "", "total": "", "rec": "", "marks": [""] * len(chunk)})
            pages.append({"rows": rows, "pad": GRID_COLS - len(chunk),
                          "cols": [{"label": f"{d['date'].month}/{d['date'].day}", "topic": d["topic"]} for d in chunk]})
    return render_template("print.html", subject=subject, section=section, subjects=subjects, pages=pages,
                           unmarked=unmarked, held=held, skipped=skipped,
                           extra_l=codes.count("l"), extra_e=codes.count("e"))


@app.route("/dates/delete", methods=["POST"])
def dates_delete():
    subject = request.form.get("subject", "")
    section = request.form.get("section", "") or None
    d = parse_iso(request.form.get("date", ""))
    if not d:
        flash("That date was not understood.", "err")
        return redirect(url_for("records", subject=subject, section=section))
    try:
        ensure_db()
        backup_workbook("before_delete_date")
        marks, topic = delete_date(subject, d, section=section)
    except ValueError as err:
        flash(str(err), "err")
        return redirect(url_for("records", subject=subject, section=section))
    log_change("Date deleted", subject, f"{d.isoformat()}" + (f" ({topic})" if topic else "")
               + f" · {marks} mark(s) removed")
    flash(f"Deleted {d.strftime('%b')} {d.day} from {subject}. A backup copy was saved in the backups folder.", "ok")
    return redirect(url_for("records", subject=subject, section=section))


@app.route("/import", methods=["GET", "POST"])
def import_meet():
    data = load_data()
    subjects, subject = pick_subject(data)
    sec_names, section, sd = pick_section(data.get(subject))
    if request.method == "GET" or not subject:       # the upload form lives on the Import (scan) page
        if subject:
            return redirect(url_for("scan", subject=subject, section=section))
        return render_template("import.html", page="scan", subject=None, review=None, tabs=None)
    f = request.files.get("csv")
    raw = f.read(MAX_CSV + 1) if f and f.filename else b""
    if not raw:
        flash("Choose the Meet CSV file first.", "err")
        return redirect(url_for("scan", subject=subject, section=section))
    if len(raw) > MAX_CSV:
        flash("That file is too big to be a Meet attendance list.", "err")
        return redirect(url_for("scan", subject=subject, section=section))
    try:
        meet = parse_meet_csv(raw)
    except ValueError as err:
        flash(str(err), "err")
        return redirect(url_for("scan", subject=subject, section=section))
    roster = [s["name"] for s in sd["students"]]
    tokens = {n: name_tokens(n) for n in roster}
    aliases = read_aliases()
    mapped, unmatched = {}, []
    for name, secs in meet["people"]:
        who = match_roster(name, roster, tokens, aliases)
        if who:
            m = mapped.setdefault(who, {"meet": [], "secs": 0})
            m["meet"].append(name)
            m["secs"] += secs
        else:
            unmatched.append({"meet": name, "secs": secs})
    d = parse_iso(request.form.get("date")) or (meet["created"].date() if meet["created"] else date.today())
    col = next((x["col"] for x in sd["dates"] if x["date"] == d), None)
    students = []
    for s in sd["students"]:
        m = mapped.get(s["name"], {"meet": [], "secs": 0})
        students.append({"row": s["row"], "name": s["name"], "meet": ", ".join(m["meet"]), "secs": m["secs"],
                         "old": sd["cells"].get((s["row"], col), "") if col else ""})
    when = ""
    if meet["created"] and meet["ended"]:
        when = f"{meet['created'].strftime('%I:%M %p').lstrip('0')} to {meet['ended'].strftime('%I:%M %p').lstrip('0')}"
    review = {"subject": subject, "section": section, "date_iso": d.isoformat(), "date_label": d.strftime("%A, %B ") + str(d.day) + d.strftime(", %Y"),
              "topic": safe_text(request.form.get("topic", ""))[:120], "length": meet["length"],
              "threshold": int(meet["length"] * MEET_PRESENT_PCT), "pct": int(MEET_PRESENT_PCT * 100), "when": when,
              "students": students, "unmatched": unmatched, "existing_date": col is not None,
              "save_url": url_for("api_save"), "alias_url": url_for("api_meet_alias"),
              "records_url": url_for("records", subject=subject, section=section)}
    return render_template("import.html", page="scan", subject=subject, review=review, tabs=None)


@app.route("/api/meet_alias", methods=["POST"])
def api_meet_alias():
    body = request.get_json(silent=True) or {}
    items = body.get("aliases")
    if not isinstance(items, list) or len(items) > 200:
        return jsonify(ok=False, error="That request was not understood."), 400
    allnames = {s["name"].lower(): s["name"]
                for sd in load_data().values()
                for sec_sd in (sd.get("sections") or {"_": sd}).values()
                for s in sec_sd["students"]}
    aliases = read_aliases()
    for it in items:
        if not isinstance(it, dict):
            continue
        meet = clean_name(str(it.get("meet", ""))).lower()[:120]
        stu = allnames.get(clean_name(str(it.get("student", ""))).lower())
        if meet and stu:
            aliases[meet] = stu
    write_aliases(aliases)
    return jsonify(ok=True)


@app.route("/students")
def students():
    data = load_data()
    subjects, subject = pick_subject(data)
    sec_names, section, sd = pick_section(data.get(subject))
    rows = student_stats(sd) if subject else []
    subj_img = subject_image_url(subject) if subject else None
    return render_template("students.html", page="students", subjects=subjects, subject=subject,
                           section=section, section_names=sec_names,
                           rows=rows, low=LOW_RATE, tabs=make_tabs(subjects, subject, "students"),
                           section_tabs=make_section_tabs(sec_names, section, subject, "students"),
                           subject_img_url=subj_img)


@app.route("/students/add", methods=["POST"])
def students_add():
    names = []
    for line in request.form.get("names", "").splitlines():
        n = safe_text(line)
        if n and n.lower() not in [x.lower() for x in names]:
            names.append(n)
    subs = request.form.getlist("subjects")
    section = clean_name(request.form.get("section", "")) or None
    if not names or not subs:
        flash("Enter at least one name and tick at least one subject.", "err")
        return redirect(url_for("students", subject=subs[0] if subs else None, section=section))
    try:
        added, skipped = add_students(subs, names, section=section)
    except ValueError as err:
        flash(str(err), "err")
        return redirect(url_for("students"))
    if added:
        log_change("Students added", ", ".join(subs) + (f" ({section})" if section else ""),
                   short_list(names, 30) + (" · Already on the list: " + short_list(skipped, 10) if skipped else ""))
    msg = f"Added {added} student entr{'y' if added == 1 else 'ies'}."
    if skipped:
        msg += " Already on the list: " + ", ".join(skipped) + "."
    flash(msg, "ok")
    return redirect(url_for("students", subject=subs[0], section=section))


@app.route("/students/remove", methods=["POST"])
def students_remove():
    subject = request.form.get("subject", "")
    section = clean_name(request.form.get("section", "")) or None
    name = clean_name(request.form.get("name", ""))
    try:
        row = int(request.form.get("row", ""))
    except ValueError:
        row = None
    everywhere = request.form.get("everywhere") == "1"
    try:
        removed = remove_student(subject, row, name, everywhere, section=section)
    except ValueError as err:
        flash(str(err), "err")
        return redirect(url_for("students"))
    if removed:
        log_change("Student removed", "All subjects" if everywhere else f"{subject} ({section or ''})", name)
    flash(f"Removed {name}." if removed else f"{name} was not found.", "ok" if removed else "err")
    return redirect(url_for("students", subject=subject, section=section))



@app.route("/subject_image/<path:subject>")
def subject_image(subject):
    fn = get_subject_image_file(subject)
    if fn:
        return send_file(os.path.join(SUBJECT_IMG_DIR, fn))
    return "Not found", 404


@app.route("/subjects/delete", methods=["POST"])
def subjects_delete():
    name = request.form.get("subject", "").strip()
    try:
        delete_subject(name)
        log_change("Subject deleted", name, "Subject and records removed")
        flash(f"Deleted subject '{name}'.", "ok")
    except Exception as err:
        flash(str(err), "err")
    return redirect(url_for("students"))


@app.route("/subjects/upload_image", methods=["POST"])
def subjects_upload_image():
    subject = request.form.get("subject", "").strip()
    if not subject:
        flash("No subject selected.", "err")
        return redirect(url_for("students"))
    f = request.files.get("image")
    if not f or not f.filename:
        flash("Please select an image file to upload.", "err")
        return redirect(url_for("students", subject=subject))
    ext = os.path.splitext(f.filename)[1].lower()
    if ext not in (".jpg", ".jpeg", ".png", ".webp", ".gif"):
        flash("Supported formats: JPG, PNG, WebP, GIF.", "err")
        return redirect(url_for("students", subject=subject))
    os.makedirs(SUBJECT_IMG_DIR, exist_ok=True)
    remove_subject_image(subject)
    safe = re.sub(r'[^a-zA-Z0-9_\-]', '_', clean_sheet_name(subject).lower())
    target = os.path.join(SUBJECT_IMG_DIR, f"{safe}{ext}")
    f.save(target)
    log_change("Subject image uploaded", subject, f"Updated image: {safe}{ext}")
    flash(f"Custom picture updated for {subject}!", "ok")
    return redirect(url_for("students", subject=subject))


@app.route("/subjects/delete_image", methods=["POST"])
def subjects_delete_image():
    subject = request.form.get("subject", "").strip()
    remove_subject_image(subject)
    log_change("Subject image removed", subject, "Reset to default")
    flash(f"Custom picture removed for {subject}.", "ok")
    return redirect(url_for("students", subject=subject))


@app.route("/subjects/add", methods=["POST"])
def subjects_add():
    name = clean_sheet_name(request.form.get("name", ""))
    sec_name = clean_sheet_name(request.form.get("section_name", "")) or None
    if not name or name.lower() == "guide":
        flash("Please enter a different subject name.", "err")
        return redirect(url_for("students"))
    try:
        n = add_subject(name, request.form.get("copy_from", ""), section_name=sec_name)
    except ValueError as err:
        flash(str(err), "err")
        return redirect(url_for("students"))
    log_change("Subject added", name, f"Copied {n} students from {request.form.get('copy_from')}" if n else "New empty subject")
    flash(f"Created {name}" + (f" with {n} students." if n else "."), "ok")
    return redirect(url_for("students", subject=name))


@app.route("/sections/add", methods=["POST"])
def sections_add():
    subject = request.form.get("subject", "").strip()
    sec_name = clean_sheet_name(request.form.get("section", ""))
    copy_from = request.form.get("copy_from_section", "").strip() or None
    if not subject or not sec_name:
        flash("Enter a section name (e.g. BSCS-1B).", "err")
        return redirect(url_for("students", subject=subject))
    try:
        n = add_section(subject, sec_name, copy_from_section=copy_from)
        log_change("Section added", f"{subject} ({sec_name})",
                   f"Copied {n} students from {copy_from}" if n else "New empty section")
        flash(f"Added section '{sec_name}' to {subject}.", "ok")
        return redirect(url_for("students", subject=subject, section=sec_name))
    except ValueError as err:
        flash(str(err), "err")
        return redirect(url_for("students", subject=subject))


@app.route("/sections/rename", methods=["POST"])
def sections_rename():
    subject = request.form.get("subject", "").strip()
    old_name = request.form.get("old_section", "").strip()
    new_name = clean_sheet_name(request.form.get("new_section", ""))
    try:
        updated = rename_section(subject, old_name, new_name)
        log_change("Section renamed", subject, f"{old_name} → {updated}")
        flash(f"Renamed section '{old_name}' to '{updated}'.", "ok")
        return redirect(url_for("students", subject=subject, section=updated))
    except ValueError as err:
        flash(str(err), "err")
        return redirect(url_for("students", subject=subject, section=old_name))


@app.route("/sections/delete", methods=["POST"])
def sections_delete():
    subject = request.form.get("subject", "").strip()
    sec_name = request.form.get("section", "").strip()
    try:
        delete_section(subject, sec_name)
        log_change("Section deleted", f"{subject} ({sec_name})", "Section and its records removed")
        flash(f"Deleted section '{sec_name}' from {subject}.", "ok")
    except ValueError as err:
        flash(str(err), "err")
    return redirect(url_for("students", subject=subject))


@app.route("/log")
def log_page():
    shown, total = read_log()
    return render_template("log.html", page="log", shown=shown, total=total)


def human_size(n):
    return f"{n / 1024:.0f} KB" if n < 1024 * 1024 else f"{n / 1024 / 1024:.1f} MB"


@app.route("/files")
def files_page():
    exists = os.path.exists(DB_FILE)
    size = modified = ""
    if exists:
        st = os.stat(DB_FILE)
        size = human_size(st.st_size)
        modified = datetime.fromtimestamp(st.st_mtime).strftime("%b %d, %Y %I:%M %p").replace(" 0", " ")
    return render_template("files.html", page="files", xlsx_path=DB_FILE, folder=os.path.dirname(DB_FILE),
                           exists=exists, size=size, modified=modified, log_name=os.path.basename(LOG_FILE),
                           is_local=request.remote_addr in ("127.0.0.1", "::1"), open_url=url_for("api_open"))


@app.route("/api/open", methods=["POST"])
def api_open():
    """Open the folder or the file on the PC that runs the site (only when asked from that PC)."""
    if request.remote_addr not in ("127.0.0.1", "::1"):
        return jsonify(ok=False, error="This only works from the computer that runs the site."), 403
    what = (request.get_json(silent=True) or {}).get("what")
    if what not in ("folder", "file"):
        return jsonify(ok=False, error="That request was not understood."), 400
    ensure_db()
    target = os.path.dirname(DB_FILE) if what == "folder" else DB_FILE
    try:
        if sys.platform.startswith("win"):
            os.startfile(target)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", target])
        else:
            subprocess.Popen(["xdg-open", target])
    except Exception:
        return jsonify(ok=False, error="Windows could not open it. Copy the path and paste it in File Explorer."), 500
    return jsonify(ok=True, message="Opened on this PC." if what == "folder" else "Opening in Excel on this PC…")


@app.route("/download")
def download():
    """Download the attendance as a fresh Excel workbook built from the database."""
    buf = io.BytesIO()
    build_workbook(load_data()).save(buf)
    buf.seek(0)
    return send_file(buf, as_attachment=True, download_name="attendance_records.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
