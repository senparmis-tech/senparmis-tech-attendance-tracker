"""
Student lookup: search a student by name, ID, or section and see their attendance and contact info in every subject.
Teacher-only (the auth gate only lets students open the Records page).
"""
from flask import render_template, request

from config import CODES, LOW_RATE
from helpers import clean_name
from store import load_data, student_stats
from web import app


def _key(name):
    return clean_name(name).casefold()


def build_index(data):
    """Map each student (by lowercase name) to their profile, stats, and history in every subject and section."""
    people = {}
    all_sections = []
    for subject, sd in data.items():
        secs_map = sd.get("sections") or {sd.get("section", "BSCS-1A"): sd}
        for sec_name, sec_sd in secs_map.items():
            if sec_name not in all_sections:
                all_sections.append(sec_name)
            for st in student_stats(sec_sd):
                p = people.setdefault(_key(st["name"]), {
                    "name": st["name"],
                    "student_no": st.get("student_no", ""),
                    "guardian_name": st.get("guardian_name", ""),
                    "guardian_phone": st.get("guardian_phone", ""),
                    "email": st.get("email", ""),
                    "address": st.get("address", ""),
                    "subjects": [],
                    "sections": [],
                })
                if sec_name not in p["sections"]:
                    p["sections"].append(sec_name)
                history = []
                for dd in sec_sd["dates"]:
                    code = sec_sd["cells"].get((st["row"], dd["col"]), "")
                    if code:
                        history.append({"date": dd["date"], "topic": dd["topic"],
                                        "code": code, "label": CODES.get(code, code)})
                p["subjects"].append({"subject": subject, "section": sec_name,
                                      "p": st["p"], "x": st["x"], "l": st["l"],
                                      "e": st["e"], "r": st["r"], "total": st["total"],
                                      "rate": st["rate"], "low": st["rate"] is not None and st["rate"] < LOW_RATE,
                                      "history": sorted(history, key=lambda h: h["date"], reverse=True)})
    for p in people.values():
        rated = [s["rate"] for s in p["subjects"] if s["rate"] is not None]
        p["avg"] = sum(rated) / len(rated) if rated else None
        p["low"] = any(s["low"] for s in p["subjects"])
    return people, all_sections


@app.route("/lookup")
def lookup():
    data = load_data()
    people, all_sections = build_index(data)
    q = clean_name(request.args.get("q", ""))
    subject = request.args.get("subject", "")
    section = request.args.get("section", "")
    pick = request.args.get("student", "")
    results = []
    q_low = q.casefold()
    for key, p in people.items():
        if q_low and (q_low not in key
                      and q_low not in p["student_no"].casefold()
                      and q_low not in p["guardian_name"].casefold()
                      and not any(q_low in sec.casefold() for sec in p["sections"])):
            continue
        if subject and not any(s["subject"] == subject for s in p["subjects"]):
            continue
        if section and not any(s["section"].casefold() == section.casefold() for s in p["subjects"]):
            continue
        results.append(p)
    results.sort(key=lambda p: p["name"].casefold())
    selected = people.get(_key(pick)) if pick else (results[0] if len(results) == 1 and (q or section) else None)
    return render_template("lookup.html", page="lookup", q=q, subject=subject, section=section,
                           subjects=list(data.keys()), sections=all_sections, results=results[:100],
                           total_matches=len(results), selected=selected, low=LOW_RATE,
                           print_view=request.args.get("print") == "1")
