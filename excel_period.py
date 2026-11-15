"""
Excel file for ONE term of a subject/section: an Attendance sheet (same layout as the main export)
and a Grades sheet (scores, category percentages, final percentage and the 1.00 - 5.00 grade).
"""
from openpyxl.styles import Alignment, Font
from openpyxl.utils import get_column_letter

from excel_io import BORDER, CENTER, HEAD_FILL, build_workbook
from store import CATEGORY_LABELS, GRADE_CATEGORIES


def build_period_workbook(subject, section, label, sd, gb):
    """``sd`` comes from store.load_period_data, ``gb`` from store.load_grades (same term)."""
    wb = build_workbook({"Attendance": sd})
    ws = wb["Attendance"]
    ws["A1"] = f"{subject} · {section} · {label}"

    gs = wb.create_sheet("Grades")
    gs["A1"] = f"{subject} · {section} · {label}"
    gs["A1"].font = Font(bold=True, size=16)
    w = gb["weights"]
    gs["A2"] = (f"Weights: Exam {w['exam']:g}% · Quiz {w['quiz']:g}% · Activity {w['activity']:g}%"
                + ("   (locked term)" if gb.get("period_locked") else ""))
    gs["A2"].font = Font(italic=True, color="667085")

    heads = ["No.", "Student Name"]
    heads += [f"{it['label']}: {it['title']} (/{it['max_score']:g})" for it in gb["items"]]
    heads += [f"{CATEGORY_LABELS[c]} %" for c in GRADE_CATEGORIES] + ["Final %", "Grade"]
    for i, h in enumerate(heads, start=1):
        c = gs.cell(4, i, h)
        c.font = Font(bold=True)
        c.fill = HEAD_FILL
        c.border = BORDER
        c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    gs.row_dimensions[4].height = 44
    gs.column_dimensions["A"].width = 6
    gs.column_dimensions["B"].width = 30
    for i in range(3, len(heads) + 1):
        gs.column_dimensions[get_column_letter(i)].width = 14

    for n, r in enumerate(gb["rows"], start=1):
        row = 4 + n
        vals = [n, r["name"]]
        vals += [r["scores"].get(it["id"]) for it in gb["items"]]
        vals += [None if r["cat_pct"][c] is None else round(r["cat_pct"][c], 1) for c in GRADE_CATEGORIES]
        vals += [None if r["final_pct"] is None else round(r["final_pct"], 1), r["scale"]]
        for i, v in enumerate(vals, start=1):
            c = gs.cell(row, i, v)
            c.border = BORDER
            c.alignment = Alignment(vertical="center") if i == 2 else CENTER
    gs.freeze_panes = "C5"
    if not gb["items"]:
        gs["A3"] = "No graded items were recorded in this term."
        gs["A3"].font = Font(italic=True, color="667085")
    return wb
