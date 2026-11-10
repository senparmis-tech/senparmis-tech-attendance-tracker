"""
AI attendance-sheet photo reader (Anthropic Claude and Google Gemini).
"""
import difflib
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

from config import AI_MODEL, API_KEY_FILE, GEMINI_FALLBACKS, GEMINI_MODEL
from helpers import clean_name, norm_code, parse_iso, safe_text

# ------------------------------------------------------------- AI sheet reader
class AIError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code, self.message = code, message


def get_api_key():
    key = ""
    for var in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"):
        key = os.environ.get(var, "").strip()
        if key:
            break
    if not key and os.path.exists(API_KEY_FILE):
        try:
            with open(API_KEY_FILE, encoding="utf-8") as f:
                key = f.read().strip()
        except OSError:
            key = ""
    return key


SHEET_TOOL = {
    "name": "record_sheet",
    "description": "Record every name found on the photographed attendance sheet.",
    "input_schema": {
        "type": "object",
        "properties": {
            "sheet_title": {"type": "string", "description": "Class or title written at the top, if any"},
            "date_text": {"type": "string", "description": "Date exactly as written on the sheet, or empty"},
            "date_iso": {"type": "string", "description": "That date as YYYY-MM-DD (month/day/year unless clearly otherwise), or empty"},
            "entries": {
                "type": "array",
                "description": "One item per name line on the sheet, in order",
                "items": {
                    "type": "object",
                    "properties": {
                        "written_name": {"type": "string", "description": "The name as you read it"},
                        "roster_match": {"type": "string", "description": "The matching name copied exactly from the class list, or empty if nobody on the class list fits"},
                        "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
                        "mark": {"type": "string", "enum": ["signed", "checked", "crossed_out", "none"],
                                 "description": "What is written next to the name: signature or scribble = signed, tick = checked, name struck through = crossed_out, nothing = none"},
                        "written_status": {"type": "string", "enum": ["p", "x", "l", "e", ""],
                                           "description": "Only if the sheet itself writes a status next to the name (P/present, A or X/absent, L/late, E/excused); otherwise empty"},
                        "attended_percent": {"type": "number",
                                             "description": "For online-meeting attendance reports: the attended percentage shown for this person (0-100). Use -1 if no percentage is shown"},
                    },
                    "required": ["written_name", "roster_match", "confidence", "mark"],
                },
            },
        },
        "required": ["entries"],
    },
}


def build_prompt(roster):
    class_list = "\n".join(f"- {n}" for n in roster) or "(empty)"
    return (
        "You are given one or more photos or screenshots of ONE attendance record for a class: a handwritten sheet, "
        "or an online-meeting attendance report with durations and percentages. Several images may be pages or "
        "scrolled parts of the same list and may overlap; list each person once. Read carefully and report "
        "every name line, in order (record_sheet format). Do not skip lines and do not invent names. "
        "The record may also contain people who are NOT in this class (other sections, teachers, room or school "
        "accounts): still list them, with an empty roster_match.\n\n"
        "The official class list is:\n" + class_list + "\n\n"
        "For each line on the sheet, set roster_match to the class-list name it refers to, copied EXACTLY as spelled "
        "in the class list. Names on paper may be written 'Last, First M.' or 'First Last', abbreviated or misspelled. "
        "If nobody on the class list plausibly fits, leave roster_match empty. Never match two lines to the same person. "
        "If handwriting is hard to read, give your best guess and lower the confidence. "
        "Do not add class-list students who are not on the sheet."
    )


def provider_of(key):
    """Claude keys start with sk-ant-; any other key is treated as a Google Gemini key (AIza... or AQ....)."""
    key = key or ""
    return "anthropic" if key.startswith("sk-ant-") or not key else "gemini"


def call_claude(images, roster, key=None):
    """Send the photos [(base64, media_type), ...] to Claude and return the structured reading."""
    key = key or get_api_key()
    if not key:
        raise AIError("no_key", "No API key is set up yet.")
    content = [{"type": "image", "source": {"type": "base64", "media_type": mt, "data": b64}} for b64, mt in images]
    content.append({"type": "text", "text": build_prompt(roster)})
    payload = {
        "model": AI_MODEL,
        "max_tokens": 8000,
        "tools": [SHEET_TOOL],
        "tool_choice": {"type": "tool", "name": "record_sheet"},
        "messages": [{"role": "user", "content": content}],
    }
    req = urllib.request.Request(
        "https://api.anthropic.com/v1/messages", data=json.dumps(payload).encode("utf-8"),
        headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = json.load(resp)
    except urllib.error.HTTPError as e:
        try:
            detail = json.load(e).get("error", {}).get("message", "")
        except Exception:
            detail = ""
        if e.code in (401, 403):
            raise AIError("bad_key", "The API key was rejected. Check that it was copied completely.")
        if e.code == 429 or e.code >= 500:
            raise AIError("busy", "The AI service is busy right now. Wait a minute and try again.")
        if "credit" in detail.lower():
            raise AIError("credit", "The API account has no credit left. Add credit in the Claude Console and try again.")
        raise AIError("api", "The AI service could not read this photo. " + detail)
    except (urllib.error.URLError, TimeoutError, OSError):
        raise AIError("network", "Could not reach the AI service. Check the internet connection and try again.")
    for block in body.get("content", []):
        if block.get("type") == "tool_use":
            return block.get("input") or {}
    raise AIError("parse", "The AI did not return a readable result. Try a clearer photo.")


def gemini_schema(node):
    """Convert the tool schema into the schema format Gemini accepts."""
    if isinstance(node, dict):
        out = {}
        for k, v in node.items():
            if k == "enum" and "" in v:      # Gemini does not accept an empty-string enum value
                continue
            out[k] = gemini_schema(v)
        return out
    if isinstance(node, list):
        return [gemini_schema(x) for x in node]
    return node


def call_gemini(images, roster, key=None):
    """Same job as call_claude, using a Google Gemini API key."""
    key = key or get_api_key()
    if not key:
        raise AIError("no_key", "No API key is set up yet.")
    parts = [{"text": build_prompt(roster)}]
    parts += [{"inline_data": {"mime_type": mt, "data": b64}} for b64, mt in images]
    payload = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {"temperature": 0, "responseMimeType": "application/json",
                             "responseSchema": gemini_schema(SHEET_TOOL["input_schema"])},
    }
    data = json.dumps(payload).encode("utf-8")

    def post(style, model):
        base = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        url, headers = base, {"content-type": "application/json"}
        if style == "header":
            headers["x-goog-api-key"] = key
        elif style == "query":
            url = base + "?key=" + urllib.parse.quote(key, safe="")
        else:
            headers["Authorization"] = "Bearer " + key
        try:
            with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=headers), timeout=120) as resp:
                return json.load(resp)
        except urllib.error.HTTPError as e:
            try:
                detail = json.load(e).get("error", {}).get("message", "")
            except Exception:
                detail = ""
            if e.code in (401, 403) or "api key" in detail.lower():
                raise AIError("bad_key", "Google rejected the Gemini API key. " + detail[:160])
            if e.code == 429:
                raise AIError("busy", "The Gemini free limit was reached for now. Wait a minute (or until tomorrow) and try again.")
            if e.code >= 500:
                raise AIError("busy", "Google's Gemini service is overloaded right now (the site already retried a few times). Wait a minute and try again.")
            if e.code == 404:
                raise AIError("api", "Gemini model '" + model + "' was not found. Set the GEMINI_MODEL setting to a current model name.")
            raise AIError("api", "The AI service could not read this photo. " + detail[:200])
        except (urllib.error.URLError, TimeoutError, OSError):
            raise AIError("network", "Could not reach the AI service. Check the internet connection and try again.")

    # Google's newer "AQ." keys are reported to be refused in some setups, so try each way of sending the key.
    styles = ["header", "query", "bearer"] if key.startswith("AQ.") else ["header"]

    def attempt(model):
        last = None
        for style in styles:
            try:
                return post(style, model)
            except AIError as err:
                last = err
                if err.code != "bad_key":
                    raise
        if key.startswith("AQ."):
            last.message += (" Google's new AQ. keys are sometimes refused by the Gemini web API. "
                             "Try creating a new key, or use a Claude key instead.")
        raise last

    # The free Gemini models are often overloaded: retry a few times, then try a lighter fallback model.
    models = [GEMINI_MODEL] + [m for m in GEMINI_FALLBACKS if m != GEMINI_MODEL]
    body, busy = None, None
    for i, model in enumerate(models):
        for n in range(3):
            try:
                body = attempt(model)
                break
            except AIError as err:
                if i == 0 and err.code != "busy":
                    raise                       # wrong key, bad photo, etc.: retrying will not help
                if err.code != "busy" and i > 0:
                    break                       # fallback model unusable: move on
                busy = busy or err
                if n < 2:
                    time.sleep(2 * (n + 1))
        if body is not None:
            break
    if body is None:
        raise busy
    try:
        text = body["candidates"][0]["content"]["parts"][0]["text"]
        result = json.loads(text)
    except (KeyError, IndexError, TypeError, ValueError):
        raise AIError("parse", "The AI did not return a readable result. Try a clearer photo.")
    if isinstance(result, list):             # tolerate a bare list of entries
        result = {"entries": result}
    if not isinstance(result, dict):
        raise AIError("parse", "The AI did not return a readable result. Try a clearer photo.")
    return result


def call_ai(images, roster):
    key = get_api_key()
    if not key:
        raise AIError("no_key", "No API key is set up yet.")
    fn = call_gemini if provider_of(key) == "gemini" else call_claude
    return fn(images, roster, key)


RANK = {"low": 0, "medium": 1, "high": 2}


def _percent(v):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return -1
    return round(x, 1) if 0 <= x <= 100 else -1


def normalize_scan(raw, roster):
    """Clean the AI output: real class-list names only, repeated lines merged, safe text."""
    lookup = {n.lower(): n for n in roster}
    merged, order = {}, []
    for it in (raw.get("entries") or []):
        if not isinstance(it, dict):
            continue
        written = safe_text(str(it.get("written_name", "")))[:80]
        if not written:
            continue
        match = lookup.get(clean_name(str(it.get("roster_match", ""))).lower(), "")
        conf = it.get("confidence") if it.get("confidence") in RANK else "medium"
        if not match:
            close = difflib.get_close_matches(written.lower(), list(lookup), n=1, cutoff=0.85)
            if close:
                match, conf = lookup[close[0]], "medium"
        mark = it.get("mark") if it.get("mark") in ("signed", "checked", "crossed_out", "none") else "none"
        entry = {"written_name": written, "roster_match": match, "confidence": conf, "mark": mark,
                 "written_status": norm_code(it.get("written_status")),
                 "attended_percent": _percent(it.get("attended_percent"))}
        key = ("m", match) if match else ("u", written.lower())
        old = merged.get(key)
        if old is None:                      # first time this person appears
            merged[key] = entry
            order.append(key)
            continue
        # the same person on overlapping photos: keep the most informative values
        if old["mark"] == "none" and mark != "none":
            old["mark"] = mark
        if not old["written_status"]:
            old["written_status"] = entry["written_status"]
        old["attended_percent"] = max(old["attended_percent"], entry["attended_percent"])
        if RANK[conf] > RANK[old["confidence"]]:
            old["confidence"] = conf
    d = parse_iso(str(raw.get("date_iso", "")))
    return {"sheet_title": safe_text(str(raw.get("sheet_title", "")))[:60],
            "date_text": clean_name(str(raw.get("date_text", "")))[:30],
            "date_iso": d.isoformat() if d else "", "entries": [merged[k] for k in order]}
