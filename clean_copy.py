#!/usr/bin/env python3
"""Strip filler copy from the remaining templates.

Run from the project root:  python3 clean_copy.py
Backs up each changed file to <name>.bak, prints how many replacements were made
per file, and lists any string it could not find so you can fix it by hand.
"""
import os
import sys

TEMPLATES = "templates"

# file -> list of (old, new)
REPLACEMENTS = {
    "records.html": [
        ("[Locked 🔒]", "(Locked)"),
        ("🔒", ""),
    ],
    "teachers.html": [
        ("Teachers & Role-Based Access", "Teachers & access"),
        ("Teachers &amp; Role-Based Access", "Teachers &amp; access"),
        ("🔒", ""),
    ],
    "files.html": [
        ("Timestamp", "When"),
    ],
    "log.html": [
        ("Timestamp", "When"),
    ],
    "periods.html": [],
    "scan.html": [],
    "grades.html": [
        ("[Locked 🔒]", "(Locked)"),
        ("🔒", ""),
    ],
    "lookup.html": [],
    "students.html": [
        ("🔒", ""),
    ],
}

# Replacements applied to every template listed above.
GLOBAL = [
    ("Faculty Instructor", "Teacher"),
    ("Academic Term:", "Term:"),
]


def main():
    if not os.path.isdir(TEMPLATES):
        sys.exit("Run this from the project root (the folder that contains templates/).")
    total = 0
    for fname, pairs in REPLACEMENTS.items():
        path = os.path.join(TEMPLATES, fname)
        if not os.path.exists(path):
            print(f"skip   {fname} (not found)")
            continue
        with open(path, encoding="utf-8") as f:
            text = f.read()
        orig = text
        count = 0
        missing = []
        for old, new in pairs:
            n = text.count(old)
            if n:
                text = text.replace(old, new)
                count += n
            else:
                missing.append(old)
        for old, new in GLOBAL:
            n = text.count(old)
            if n:
                text = text.replace(old, new)
                count += n
        if text != orig:
            with open(path + ".bak", "w", encoding="utf-8") as f:
                f.write(orig)
            with open(path, "w", encoding="utf-8") as f:
                f.write(text)
        print(f"{'edited' if text != orig else 'same  '} {fname}: {count} replacement(s)")
        for m in missing:
            print(f"   not found: {m!r}")
        total += count
    print(f"done, {total} replacement(s). Originals saved as *.bak")


if __name__ == "__main__":
    main()
