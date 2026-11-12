"""
Student lookup: search a student by name and see their attendance in every subject.
Teacher-only (the auth gate only lets students open the Records page).
"""
from flask import render_template, request

from config import CODES, LOW_RATE
from excel_store import load_data, student_stats
from helpers import clean_name
from web import app


def _key(name):
    return clean_name(name).casefold()


def build_index(data):
    """Map each student (by lowercase name) to their stats and history in every subject."""
    people = {}
    for subject, sd in data.items():
        for st in student_stats(sd):
            p = people.setdefault(_key(st["name"]), {"name": st["name"], "subjects": []})
            history = []
            for dd in sd["dates"]:
                code = sd["cells"].get((st["row"], dd["col"]), "")
                if code:
                    history.append({"date": dd["date"], "topic": dd["topic"],
                                    "code": code, "label": CODES.get(code, code)})
            p["subjects"].append({"subject": subject, "p": st["p"], "x": st["x"], "l": st["l"],
                                  "e": st["e"], "r": st["r"], "total": st["total"],
                                  "rate": st["rate"], "low": st["rate"] is not None and st["rate"] < LOW_RATE,
                                  "history": sorted(history, key=lambda h: h["date"], reverse=True)})
    for p in people.values():
        rated = [s["rate"] for s in p["subjects"] if s["rate"] is not None]
        p["avg"] = sum(rated) / len(rated) if rated else None
        p["low"] = any(s["low"] for s in p["subjects"])
    return people


@app.route("/lookup")
def lookup():
    data = load_data()
    people = build_index(data)
    q = clean_name(request.args.get("q", ""))
    subject = request.args.get("subject", "")
    pick = request.args.get("student", "")
    results = []
    for key, p in people.items():
        if q and q.casefold() not in key:
            continue
        if subject and not any(s["subject"] == subject for s in p["subjects"]):
            continue
        results.append(p)
    results.sort(key=lambda p: p["name"].casefold())
    selected = people.get(_key(pick)) if pick else (results[0] if len(results) == 1 and q else None)
    return render_template("lookup.html", page="lookup", q=q, subject=subject,
                           subjects=list(data.keys()), results=results[:100],
                           total_matches=len(results), selected=selected, low=LOW_RATE,
                           print_view=request.args.get("print") == "1")
