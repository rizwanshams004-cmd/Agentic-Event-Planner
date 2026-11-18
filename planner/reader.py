"""Reader: the only language step. Prompt fill, schema check, one repair, number grounding, escape hatch."""
import json
import re
from pathlib import Path
from .llm import LLMError
from .plan import FEAT

ROOT = Path(__file__).resolve().parent.parent
PROMPT = (ROOT / "prompts/reader.txt").read_text(encoding="utf-8")
AREA_PROMPT = (ROOT / "prompts/area.txt").read_text(encoding="utf-8")
REPAIR = 'Fix this into valid JSON of the form {"msgs":[...]} exactly as described. Output JSON only.\n'
ROLES = {"authority", "finance", "venue", "caterer", "judging", "judge", "student", "vendor", "official", "unknown"}
AREAS = ("venue", "schedule", "food", "judging", "budget")
INT_KEYS = {"students", "team_size", "teams", "duration_min", "staff", "judges_available", "honorarium",
            "min_per_team", "max_teams_per_judge", "judges_per_team", "budget"}
STR_KEYS = {"start_time", "end_time"}
DICT_KEYS = {"extra_people", "reserve", "seat_factor", "venue", "venue_require", "venue_exclude", "block",
             "window", "late", "food", "food_require", "diet", "judges_change", "cost", "claim"}
NUMF = ("seats", "price", "amount", "n", "min", "delta", "pct", "price_per_head", "fee", "min_order", "value")
WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
         "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15, "twenty": 20, "thirty": 30, "forty": 40,
         "fifty": 50, "sixty": 60, "hundred": 100, "half": 0.5, "hour": 1, "ghanta": 1, "dozen": 12,
         "ek": 1, "do": 2, "teen": 3, "char": 4, "chaar": 4, "panch": 5, "paanch": 5, "chay": 6, "chhe": 6,
         "saat": 7, "aath": 8, "nau": 9, "das": 10, "bees": 20, "pachees": 25, "tees": 30, "chalees": 40,
         "pachas": 50, "pachaas": 50, "saath": 60, "sattar": 70, "assi": 80, "sau": 100, "dedh": 1.5,
         "dhai": 2.5, "adha": 0.5, "aadha": 0.5}
MULT = {"k": 1e3, "thousand": 1e3, "hazaar": 1e3, "hazar": 1e3, "hajar": 1e3, "lakh": 1e5, "lac": 1e5,
        "lacs": 1e5, "lakhs": 1e5, "laakh": 1e5, "crore": 1e7, "million": 1e6, "sau": 100, "hundred": 100}


# Sender-name keywords -> role (first match wins). Generic role words, not pack data.
ROLE_RULES = [("student", r"student|society|club|\bclass\b|batch"),
              ("judging", r"judg\w*\s+(coord|panel|lead|head)|coordinator"),
              ("judge", r"\bjudge\b"), ("finance", r"financ|account|treasur|bursar"),
              ("caterer", r"cater|food|kitchen|restaurant"), ("venue", r"venue|\bhall\b|auditorium|facilit|estate"),
              ("official", r"iesco|wapda|police|\bcda\b|govt|government|municipal|utility|electric|notice"),
              ("authority", r"dean|principal|registrar|rector|\bvc\b|vice.?chancellor|director|organi[sz]er|admin|\bhod\b|head of"),
              ("unknown", r"volunteer|anonymous|unknown|someone")]


def role_of(sender, model_role):
    for role, rx in ROLE_RULES:
        if re.search(rx, sender, re.I):
            return role
    return model_role if model_role in ROLES else "unknown"


def numbers(text):
    """Every number the text could mean, after normalising commas, k, lakh, hazaar, words, hours."""
    t = re.sub(r"(?<=\d),(?=\d)", "", text.lower())
    toks = re.findall(r"\d+(?:\.\d+)?|[a-z]+", t)
    base = []
    for i, tok in enumerate(toks):
        n = float(tok) if tok[0].isdigit() else WORDS.get(tok)
        if n is None:
            continue
        base.append(n)
        if i + 1 < len(toks) and toks[i + 1] in MULT:
            base.append(n * MULT[toks[i + 1]])
    out = set()
    for n in base:
        out |= {n, n * 60}
    return out


DERIVED_WORDS = r"box|headcount|people|meal|plate|order|quantity|qty|units|count|judges_needed|total|rounds"


def tonum(x):
    if isinstance(x, bool) or x is None:
        return None
    if isinstance(x, (int, float)):
        return x
    try:
        n = float(re.sub(r"(?i)rs\.?|,|\s|%", "", str(x)))
        return int(n) if n == int(n) else n
    except ValueError:
        return None


def clean(f):
    k, v = f.get("k"), f.get("v")
    if k in INT_KEYS:
        v = tonum(v)
        if v is None:
            return None, f"{k}: value {f.get('v')!r} is not a number"
    elif k in STR_KEYS:
        v = str(v)
    elif k in DICT_KEYS:
        if not isinstance(v, dict):
            n = tonum(v)
            if n is None or k not in ("reserve", "seat_factor", "judges_change"):
                return None, f"{k}: expected an object, got {v!r}"
            v = {"reserve": {"amount": n}, "seat_factor": {"pct": n}, "judges_change": {"delta": n}}[k]
        v = dict(v)
        for fld in NUMF:
            if fld in v and v[fld] is not None:
                n = tonum(v[fld])
                if n is None:
                    return None, f"{k}.{fld}: {v[fld]!r} is not a number"
                v[fld] = n
    elif re.search(DERIVED_WORDS, str(k), re.I) and tonum(v) is not None:
        return dict(k="claim", v={"key": str(k), "value": tonum(v)}, q=str(f.get("q", ""))[:80], req=False), None
    else:
        return None, f"unknown key {k!r} (not in vocabulary)"
    return dict(k=k, v=v, q=str(f.get("q", ""))[:80], req=bool(f.get("req"))), None


BREAK = re.compile(r"break|prayer|namaz|lunch|tea|session|opening|closing|ceremony|min", re.I)


def repair(f, role):
    """Generic key repairs for common small-model slips (no pack data). Returns a note or None."""
    k, v = f["k"], f["v"]
    if k == "extra_people" and BREAK.search(str(v.get("who", ""))):
        f["k"], f["v"] = "block", {"name": str(v.get("who")), "min": v.get("n"), "required": True}
        return "extra_people that names a break/session -> block"
    if k == "duration_min" and role == "judging":
        f["k"] = "min_per_team"
        return "duration from the judging coordinator -> min_per_team"
    if k == "food" and tonum(v.get("price_per_head")) == 0:
        f["v"] = {x: y for x, y in v.items() if x not in ("price_per_head", "min_order")}
        return "food item priced 0 per head -> fee-only line"
    if k == "late" and role == "judge" and "judg" not in str(v.get("who", "")).lower():
        f["v"] = {**v, "who": "judge"}
        return "late sender is a judge -> who=judge"
    return None


def ungrounded(f, nums):
    v = f["v"]
    vals = [v] if not isinstance(v, dict) else [v[x] for x in NUMF if tonum(v.get(x)) is not None]
    for x in vals:
        x = tonum(x)
        if x is None or x == 0 or (f["k"] == "judges_per_team" and x == 1):
            continue
        if not any(abs(abs(x) - n) < 0.01 for n in nums):
            return x
    return None


def parse(raw):
    if not raw:
        return None
    s = re.sub(r"^```(?:json)?|```$", "", raw.strip(), flags=re.M)
    i, j = s.find("{"), s.rfind("}")
    try:
        return json.loads(s[i:j + 1])
    except (ValueError, TypeError):
        return None


def _facts(lst):
    good, bad = [], []
    for f in lst or []:
        c, err = clean(f) if isinstance(f, dict) else (None, "not an object")
        (good.append(c) if c else bad.append(dict(raw=f, err=err)))
    return good, bad


def read(chunk, known, budget, tr):
    prompt = PROMPT.replace("{known_names}", known or "none").replace("{messages}", chunk.strip())
    raw = budget.call(prompt, "reading")
    d = parse(raw)
    if not (isinstance(d, dict) and isinstance(d.get("msgs"), list)) and budget.left() > 0:
        tr.code("reader output is not valid JSON/schema -> one repair call")
        raw = budget.call(REPAIR + raw if raw else prompt, "reading")
        d = parse(raw)
    if not (isinstance(d, dict) and isinstance(d.get("msgs"), list)):
        raise LLMError("reader output invalid after repair")
    msgs = []
    for m in d["msgs"]:
        if not isinstance(m, dict):
            continue
        good, bad = _facts(m.get("facts"))
        date = m.get("date") if re.match(r"^\d{4}-\d{2}-\d{2}$", str(m.get("date"))) else None
        frm = str(m.get("from") or "?")
        role = role_of(frm, m.get("role"))
        if role != m.get("role"):
            tr.code(f"role  sender '{frm}': model said {m.get('role')!r}, sender-name rule says {role!r} -> {role}")
        msgs.append(dict(frm=frm, role=role,
                         date=date, facts=good, dropped=bad, other=m.get("other") or [], note=str(m.get("note") or "")))
    tr.code(f"reader: {len(msgs)} message(s), {sum(len(m['facts']) for m in msgs)} fact(s), "
            f"{sum(len(m['dropped']) for m in msgs)} dropped by schema check")
    return msgs


AREA_WORDS = [("venue", r"venue|hall|room|seat|power|generator|parking|access"), ("food", r"food|lunch|meal|tea|cater|diet|veg"),
              ("judging", r"judg|score|jury"), ("budget", r"\brs\b|rupee|cost|price|tax|gst|budget|fee|pay")]


def infer_area(text):
    return next((a for a, rx in AREA_WORDS if re.search(rx, str(text), re.I)), "schedule")


def escape(other, M, budget, tr):
    """Area call for constraints outside the vocabulary (max 2 per message, inside the call budget)."""
    out = []
    for it in other[:2]:
        text = it.get("t") if isinstance(it, dict) else str(it)
        m = re.search(r"(\d+)\s*(?:-\s*)?min", str(text), re.I)
        if m and BREAK.search(str(text)):        # obvious timed break: map in code, no model call
            out.append(dict(k="block", v={"name": str(text), "min": int(m[1]), "required": True}, q=str(text)[:80], req=False))
            tr.code(f"escape hatch (code, 0 tokens) '{text}' -> block {m[1]} min")
            continue
        area = it.get("a") if isinstance(it, dict) and it.get("a") in AREAS else infer_area(text)
        ft = next((b for a, b in FEAT.items() if a in str(text).lower()), None)
        if ft:                                   # known venue feature: map in code, no model call
            out.append(dict(k="venue_require", v={"feature": ft}, q=str(text)[:80], req=False))
            tr.code(f"escape hatch (code, 0 tokens) '{text}' -> venue_require {ft}")
            continue
        if budget.left() <= 0:
            tr.code(f"escape hatch skipped (call budget used up): {text}")
            break
        prompt = AREA_PROMPT.replace("{area}", area).replace("{role}", M["role"]).replace("{text}", str(text))
        try:
            d = parse(budget.call(prompt, area)) or {}
        except LLMError as e:
            tr.code(f"escape hatch failed: {e}")
            break
        good, bad = _facts(d.get("facts"))
        tr.code(f"escape hatch [{area}] '{text}' -> {len(good)} fact(s)" + (f"; note: {d.get('note')}" if d.get("note") else ""))
        out += good
    return out
