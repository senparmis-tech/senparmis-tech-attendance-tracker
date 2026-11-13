"""
Score roll call: enter one graded item's scores student by student, saving each score as you go.

Registers the page (/grades/rollcall) and two small JSON endpoints. Every write goes through
store.save_grade_scores(), so it keeps the automatic backups and the per-teacher permission checks.
"""
import math

from flask import flash, jsonify, redirect, render_template, request, url_for

from helpers import clean_name, log_change
from store import load_grades, save_grade_scores
from web import app


def _fmt(n):
    return f"{float(n):g}"


def _find_item(gb, item_id):
    return next((it for it in gb["items"] if it["id"] == item_id), None)


@app.route("/grades/rollcall")
def grade_rollcall():
    subject = request.args.get("subject", "").strip()
    section = clean_name(request.args.get("section", "")) or None
    try:
        item_id = int(request.args.get("item", ""))
    except ValueError:
        item_id = None
    try:
        gb = load_grades(subject, section)
    except ValueError as err:
        flash(str(err), "err")
        return redirect(url_for("grades_page"))
    sec = gb["section"]
    gradebook_url = url_for("grades_page", subject=subject, section=sec)
    item = _find_item(gb, item_id)
    if item is None:
        flash("Choose a graded item first.", "err")
        return redirect(gradebook_url)
    if not gb["rows"]:
        flash("There are no students in this section yet.", "err")
        return redirect(gradebook_url)

    items = gb["items"]
    pos = items.index(item)
    nxt = items[pos + 1] if pos + 1 < len(items) else None
    cfg = {
        "students": [{"eid": r["enrollment_id"], "name": r["name"], "no": r["student_no"],
                      "score": r["scores"].get(item["id"])} for r in gb["rows"]],
        "subject": subject, "section": sec, "itemId": item["id"],
        "itemLabel": item["label"], "itemTitle": item["title"], "max": float(item["max_score"]),
        "saveUrl": url_for("api_grade_score"), "logUrl": url_for("api_grade_rollcall_log"),
        "gradebookUrl": gradebook_url,
        "nextUrl": url_for("grade_rollcall", subject=subject, section=sec, item=nxt["id"]) if nxt else "",
        "nextLabel": f"{nxt['label']}: {nxt['title']}" if nxt else "",
    }
    return render_template("grade_rollcall.html", page="grades", subject=subject, section=sec,
                           item=item, max_text=_fmt(item["max_score"]), gradebook_url=gradebook_url, cfg=cfg)


@app.route("/api/grade_score", methods=["POST"])
def api_grade_score():
    """Save (or clear) ONE student's score for one graded item."""
    body = request.get_json(silent=True) or {}
    subject = str(body.get("subject", "")).strip()
    section = clean_name(str(body.get("section") or "")) or None
    try:
        item_id = int(body.get("item_id"))
        eid = int(body.get("enrollment_id"))
    except (TypeError, ValueError):
        return jsonify(ok=False, error="That request was not understood."), 400
    raw = body.get("score")
    if raw is None or raw == "":
        score = None
    else:
        try:
            if isinstance(raw, bool):
                raise ValueError
            score = round(float(raw), 2)
        except (TypeError, ValueError):
            return jsonify(ok=False, error="That score is not a number."), 400
        if not math.isfinite(score):
            return jsonify(ok=False, error="That score is not a number."), 400
    try:
        saved = save_grade_scores(subject, section, [(eid, item_id, score)])
    except ValueError as err:
        return jsonify(ok=False, error=str(err)), 400
    if score is not None and not saved:
        return jsonify(ok=False, error="That student or graded item was not found."), 404
    return jsonify(ok=True, score=score)


@app.route("/api/grade_rollcall_log", methods=["POST"])
def api_grade_rollcall_log():
    """One line in the Changes log for a roll-call session (the per-score saves are not logged one by one)."""
    body = request.get_json(silent=True) or {}
    subject = str(body.get("subject", "")).strip()
    section = clean_name(str(body.get("section") or "")) or None
    try:
        item_id = int(body.get("item_id"))
        count = max(0, min(int(body.get("count") or 0), 10000))
        gb = load_grades(subject, section)
    except (TypeError, ValueError) as err:
        return jsonify(ok=False, error=str(err) or "That request was not understood."), 400
    item = _find_item(gb, item_id)
    if item and count:
        log_change("Score roll call", f"{subject} ({gb['section']})",
                   f"{item['label']}: {item['title']} (max {_fmt(item['max_score'])}) · {count} score(s) entered")
    return jsonify(ok=True)
