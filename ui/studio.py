"""Planner Studio server: serves the approved 'Planner Studio.dc.html' UI with live planner data.

    python ui/studio.py [messages.txt]      -> http://localhost:8600

GET  /api/state    view model built from state/<file>.json (same state the CLI writes)
POST /api/add      {"text": ...} appends the message to the same file and calls the same engine.run()
GET  /api/presets  test messages from tests/messages/*.txt (data files, not code)
"""
import json
import re
import sys
from datetime import datetime
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from planner import engine, report, state as S  # noqa: E402
from planner.resolver import fmt  # noqa: E402
from planner.trace import line  # noqa: E402

STUDIO = ROOT / "ui" / "studio"
PACK = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "pack.txt").resolve()
N = lambda x: f"{x:,.0f}" if isinstance(x, (int, float)) else "—" if x is None else str(x)
SENDER = re.compile(r"^\s*(\d+\)\s*)?([A-Z][\w'’.&\- ]{1,40})(,[^:\n]{0,40})?:")


def as_message(text):
    """Text typed in the UI comes from the organiser unless it is a pasted message with its own sender line."""
    m = SENDER.match(text)
    label = m.group(2).lower() if m else ""
    if m and len(label.split()) <= 4 and not re.search(r"quote|update|note|info|detail|plan|budget|price|option|request|"
                                                       r"change|menu|schedule|here|wedding|event", label):
        return text.strip()
    return f"Organizer (planner UI), {datetime.now():%d %b %Y}: {text.strip()}"


LABEL = {"students": "Guests / participants", "team_size": "Team size", "teams": "Teams", "duration_min": "Event length (min)",
         "staff": "Staff", "budget": "Budget (Rs)", "judges_available": "Judges available", "honorarium": "Judge fee (Rs)",
         "min_per_team": "Minutes per team", "max_teams_per_judge": "Max teams per judge", "event_type": "Event type",
         "start_time": "Start time", "end_time": "End time"}


def human(f):
    """One readable line per fact (no JSON)."""
    k, v = f["k"], f["v"]
    if not isinstance(v, dict):
        return f"{LABEL.get(k, k)}: {N(v) if isinstance(v, (int, float)) else v}"
    if k == "venue":
        bits = [f"{N(v['seats'])} seats" if v.get("seats") else "", f"Rs {N(v['price'])}" + ("/hour" if v.get("basis") == "per_hour" else "")
                if v.get("price") is not None else "", ", ".join(v.get("features") or []), "not available" if v.get("available") is False else ""]
        return f"Venue {v.get('name')}: " + " · ".join(b for b in bits if b)
    if k == "food":
        return f"Catering {v.get('name')}: " + " · ".join(b for b in [f"Rs {N(v['price_per_head'])} per person" if v.get("price_per_head") else "",
                                                                       f"fee Rs {N(v['fee'])}" if v.get("fee") else ""] if b)
    if k == "cost":
        return f"Cost {v.get('name')}: Rs {N(v.get('amount'))} ({v.get('status', 'required')})"
    if k == "claim":
        return f"Claims {v.get('key')} = {N(v.get('value'))}"
    if k == "block":
        return f"Schedule item {v.get('name')}: {N(v.get('min'))} min"
    if k == "late":
        return f"{v.get('who')} late by {N(v.get('min'))} min"
    if k == "judges_change":
        return f"Judges change: {N(v.get('delta'))}"
    if k == "venue_require":
        return f"Venue must have: {v.get('feature')}"
    return f"{LABEL.get(k, k)}: " + ", ".join(f"{a} {N(b) if isinstance(b, (int, float)) else b}" for a, b in v.items())


def status_key(m, infeasible_runs):
    s = m["status"]
    if s.startswith("request"):
        return "request"
    if s == "no impact":
        return "noimpact"
    if s == "applied" and m["run"] in infeasible_runs:
        return "infeasible"
    return s if s in ("applied", "rejected", "superseded") else "noimpact"


def view(st):
    p = st.get("plan")
    inf_runs = {r["run"] for r in st["runs"] if r.get("infeasible")}
    facts = {}
    for f in st["facts"]:
        facts.setdefault(f["msg"], []).append(f)
    msgs = []
    audit_text = {a["msg"]: a.get("text", "") for a in st.get("audit", [])}
    for m in st["msgs"]:
        fs = facts.get(m["n"], [])
        msgs.append(dict(i=m["n"], frm=m["frm"], role=m["role"], date=m["date"] or "undated", run=m["run"],
                         status=status_key(m, inf_runs), statusText=m["status"], reason=m["reason"],
                         ch="whatsapp" if "whatsapp" in m["frm"].lower() else "pasted" if m["role"] == "organizer" else "email",
                         text=audit_text.get(m["n"], ""),
                         decision=((m.get("guardian") or {}).get("decision", "") + ". " if (m.get("guardian") or {}).get("decision")
                                   in ("QUARANTINED", "FLAGGED") else "") + m["reason"],
                         quotes="\n".join(f"“{f['q']}”" for f in fs if f.get("q")) or m.get("note") or "(no quote)",
                         facts="\n".join(f"{human(f)}   [{f['status']}]" for f in fs) or "none",
                         guardian=m.get("guardian") or {}))
    runs = []
    cum = 0
    for r in st["runs"]:
        ev = [e for e in st["trace"] if e["run"] == r["run"]]
        head = next((e["text"] for e in ev if e["t"] == "head"), "")
        calls = [dict(n=e["n"], model=e["model"], area=e["area"], secs=e.get("secs", 0), error=e.get("error"),
                      input=e["input"], output=e.get("output") or "", **(e.get("usage") or
                      {"prompt": None, "completion": None, "total": None})) for e in ev if e["t"] == "call"]
        cum += r.get("tokens", 0)
        new = [m for m in msgs if m["run"] == r["run"]]
        if r["mode"] == "full":
            title, icon, color = "Full run", "flag", "#16A34A"
        else:
            st0 = new[0]["status"] if new else "noimpact"
            title = (new[0]["frm"] if new else "Update") + (f" +{len(new) - 1}" if len(new) > 1 else "")
            icon, color = {"rejected": ("octagon-x", "#DC2626"), "infeasible": ("triangle-alert", "#DC2626"),
                           "applied": ("circle-check", "#16A34A"), "superseded": ("history", "#71717A")}.get(
                st0, ("circle-minus", "#71717A"))
        runs.append(dict(r=r["run"], kind=r["mode"], time=(re.findall(r"\d{2} \w{3} [\d:]{8}", head) or [""])[0],
                         title=title, icon=icon, color=color, calls=calls, tokens=r.get("tokens", 0), cum=cum,
                         areas=r.get("areas", []), changed=r.get("changed", []), failed=bool(r.get("failed")),
                         infeasible=r.get("infeasible"), before=r.get("before", {}), after=r.get("after", {}),
                         code="\n".join(e["text"] for e in ev if e["t"] == "code"),
                         decisions="\n".join(e["text"] for e in ev if e["t"] == "code" and re.match(
                             r"(resolver|superseded|repair|role|grounding|impact|schema|lever|INFEAS)", e["text"]))))
    from planner import guardian
    v = guardian.verify(st.get("audit", []))
    needs = (p or {}).get("needs") or [x[len("provide: "):] for x in st.get("infeasible") or [] if x.startswith("provide: ")]
    out = dict(needs=needs, complete=bool(p) and not st.get("infeasible"), audit=dict(ok=v["ok"], entries=len(st.get("audit", [])), problem=v["problem"]), file=PACK.name, nmsgs=len(msgs), msgs=msgs, runs=runs, calls=st["calls"], tokens=st["tokens"],
               infeasible="; ".join(st.get("infeasible") or []), planMd=report.plan_md(st),
               traceTxt="\n".join(line(e) for e in st["trace"]) +
                        f"\n=== SESSION TOTAL: {st['calls']} model calls · {st['tokens']:,} tokens ===\n")
    if p:
        F, B, V, FD, SC = p["figures"], p["budget"], p["venue"], p["food"], p["schedule"]
        out.update(checks=[dict(name=c["name"], ok=c["ok"], detail=c["detail"]) for c in st["checks"] or []], plan=dict(
            headcount=F["headcount"], teams=F["teams"], judges=f"{F['judges_used']} / {F['judges_available']}",
            total=N(B["total"]), remaining=N(B["remaining"]), budget=N(B["budget"]),
            venue=f"{V.get('name')} · {N(V.get('cost'))}", schedule=f"{F['duration_min']} min · {len(SC['blocks'])} blocks",
            food=f"{FD.get('boxes')} × {N(FD.get('pph'))}", judging=f"{F['judges_used']} of {F['judges_available']} · {F['rounds']} rounds",
            budgetLine=f"{N(B['total'])} / {N(B['budget'])}",
            derived="\n".join([f"teams = ceil({F['students']} / {F['team_size']}) = {F['teams']}",
                               f"judges needed = ceil({F['teams']} × {F['judges_per_team']} / {F['max_teams_per_judge']}) = {F['judges_needed']}",
                               f"rounds = ceil({F['teams']} / {F['judges_used']}) = {F['rounds']} → {F['judging_min']} min",
                               f"headcount = {F['students']} + {F['judges_used']} + {F['staff']}" + (f" + {F['extra']}" if F["extra"] else "") + f" = {F['headcount']}",
                               f"venue = cheapest with seats ≥ {F['headcount']}" + (f" + {', '.join(V['required'])}" if V["required"] else "") + f" → {V.get('name')}",
                               f"food = {FD.get('qty')} × {N(FD.get('pph'))}" + (f" + {N(FD['fee'])}" if FD.get("fee") else "") + f" = {N(FD.get('cost'))}"]
                              + [f"rejected: {r['name']} ({r['why']})" for r in V["rejected"]]),
            budgetTxt="\n".join(f"{l['line'][:26]:<26} {N(l['amount']):>9}   {l['src']}" for l in B["lines"]) +
                      f"\n{'total':<26} {N(B['total']):>9}\n{'reserve':<26} {N(B['reserve']):>9}\n{'remaining':<26} {N(B['remaining']):>9}",
            scheduleTxt="\n".join(f"{b['time']}  {b['name'][:34]:<34} {b['min']:>3}" for b in SC["blocks"]) +
                        ("\nStart time is a planner assumption." if SC["assumed"] else ""),
            gridTxt="\n".join(f"J{i + 1:<3} {', '.join(t)}" for i, t in enumerate(p["judging"]["grid"])),
            decisions="\n".join(p["levers"] + p["notes"]) or "none"))
    return out


class H(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=str(STUDIO), **k)

    def log_message(self, *a):
        pass

    def send_json(self, obj, code=200):
        b = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            self.send_response(302)
            self.send_header("Location", "/Planner%20Studio.dc.html")
            self.end_headers()
        elif self.path.startswith("/api/state"):
            st = S.load(PACK)
            self.send_json(view(st) if st else {"empty": True, "file": PACK.name})
        elif self.path.startswith("/api/presets"):
            fs = sorted((ROOT / "tests" / "messages").glob("*.txt"))
            self.send_json([dict(label=f.stem.split("_", 1)[-1].replace("_", " "), text=f.read_text(encoding="utf-8").strip())
                            for f in fs])
        else:
            super().do_GET()

    def do_POST(self):
        if not self.path.startswith("/api/add"):
            return self.send_json({"error": "not found"}, 404)
        text = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}").get("text", "").strip()
        if not text:                              # empty: just (re)run the file as it is
            engine.run(str(PACK), echo=False)
            st = S.load(PACK)
            return self.send_json(view(st) if st else {"empty": True, "file": PACK.name})
        old = PACK.read_text(encoding="utf-8") if PACK.exists() else ""
        with open(PACK, "a", encoding="utf-8") as fh:
            fh.write(("" if not old or old.endswith("\n\n") else "\n" if old.endswith("\n") else "\n\n") + as_message(text) + "\n")
        engine.run(str(PACK), echo=False)        # the same code path as `python run.py <file>`
        self.send_json(view(S.load(PACK)))


if __name__ == "__main__":
    port = int(__import__("os").environ.get("PORT", 8600))
    print(f"Planner Studio: http://localhost:{port}   (file: {PACK})")
    ThreadingHTTPServer(("127.0.0.1", port), H).serve_forever()
