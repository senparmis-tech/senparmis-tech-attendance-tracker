"""
Terms inside a semester (Prelim, Midterm, Pre-final, Final): lock a finished term, start the next one,
look back at old terms, and download or print them.

Teachers can lock their own subjects; only an admin can reopen a locked term.
"""
import io
import re

from flask import flash, g, redirect, render_template, request, send_file, url_for

from excel_period import build_period_workbook
from helpers import clean_name, log_change
from routes import make_section_tabs, make_tabs, pick_section, pick_subject
from store import (SEMESTER_NAMES, TERM_NAMES, list_periods, load_data, load_grades,
                   load_period_data, lock_period, suggest_next_period, unlock_period,
                   update_period)
from web import app


def _args():
    subject = (request.values.get("subject") or "").strip()
    section = clean_name(request.values.get("section") or "") or None
    return subject, section


@app.route("/periods")
def periods_page():
    data = load_data()
    subjects, subject = pick_subject(data)
    sec_names, section, _sd = pick_section(data.get(subject))
    periods = list_periods(subject, section) if subject else []
    current = next((p for p in reversed(periods) if not p["locked"]), None)
    sem, trm = suggest_next_period(current["semester"], current["term"]) if current else ("", "")
    groups = []                                   # terms grouped by semester, oldest first
    for p in periods:
        if not groups or groups[-1]["semester"].casefold() != p["semester"].casefold():
            groups.append({"semester": p["semester"], "periods": []})
        groups[-1]["periods"].append(p)
    return render_template(
        "periods.html", page="records", subject=subject, section=section, groups=groups, current=current,
        next_semester=sem, next_term=trm, semesters=SEMESTER_NAMES, terms=TERM_NAMES,
        is_admin=bool(getattr(g, "is_admin", False)),
        tabs=make_tabs(subjects, subject, "periods_page"),
        section_tabs=make_section_tabs(sec_names, section, subject, "periods_page"))


@app.route("/periods/edit", methods=["POST"])
def periods_edit():
    """Rename the current open term (semester and term label) without locking it."""
    subject, section = _args()
    period_id = request.form.get("period_id", type=int)
    semester = request.form.get("semester", "").strip()
    term = request.form.get("term", "").strip()
    try:
        p = update_period(subject, section, semester, term, period_id)
    except ValueError as err:
        flash(str(err), "err")
        return redirect(request.referrer or url_for("periods_page", subject=subject, section=section))
    log_change("Term renamed", f"{subject} ({section or ''})",
               f"Term updated to: {p['label']}")
    flash(f"Term updated to '{p['label']}'.", "ok")
    back = request.form.get("next", "")
    if back == "students":
        return redirect(url_for("students", subject=subject, section=section))
    return redirect(url_for("periods_page", subject=subject, section=section))


@app.route("/periods/lock", methods=["POST"])
def periods_lock():
    subject, section = _args()
    try:
        res = lock_period(subject, section, request.form.get("semester", ""), request.form.get("term", ""),
                          request.form.get("next_semester", ""), request.form.get("next_term", ""))
    except ValueError as err:
        flash(str(err), "err")
        return redirect(url_for("periods_page", subject=subject, section=section))
    log_change("Term locked", f"{subject} ({section or ''})",
               f"{res['locked']} locked ({res['n_dates']} date(s), {res['n_items']} graded item(s)) · "
               f"New term: {res['next']}")
    flash(f"Locked {res['locked']}. {res['next']} is open and empty: mark attendance and add scores as usual. "
          "You can look at, print or download the locked term below.", "ok")
    return redirect(url_for("periods_page", subject=subject, section=section))


@app.route("/periods/unlock", methods=["POST"])
def periods_unlock():
    subject, section = _args()
    if not getattr(g, "is_admin", False):
        flash("Only an admin can reopen a locked term.", "err")
        return redirect(url_for("periods_page", subject=subject, section=section))
    try:
        p = unlock_period(subject, section, request.form.get("period"))
    except ValueError as err:
        flash(str(err), "err")
        return redirect(url_for("periods_page", subject=subject, section=section))
    log_change("Term reopened", f"{subject} ({section or ''})", f"{p['label']} was unlocked")
    flash(f"Reopened {p['label']}. It is the current term again.", "ok")
    return redirect(url_for("periods_page", subject=subject, section=section))


@app.route("/periods/download")
def periods_download():
    subject, section = _args()
    pid = request.args.get("period", type=int)
    try:
        sd = load_period_data(subject, section, pid)
        gb = load_grades(subject, section, pid)
    except ValueError as err:
        flash(str(err), "err")
        return redirect(url_for("periods_page", subject=subject, section=section))
    buf = io.BytesIO()
    build_period_workbook(subject, gb["section"], sd["period"]["label"], sd, gb).save(buf)
    buf.seek(0)
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", f"{subject}_{gb['section']}_{sd['period']['semester']}_{sd['period']['term']}")
    return send_file(buf, as_attachment=True, download_name=f"{stem.strip('_')}.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
