"""Event Planner — simple chat + live plan.   streamlit run ui/chat.py

Left: one chat. Right: "Your Event Plan" built step by step from the real planner output.
Every chat message is appended to chat_pack.txt and processed by the same engine.run() as `python run.py`.
Technical evidence (model calls, tokens, security audit) sits in one collapsed panel.
"""
import html
import json
import re
import sys
from datetime import datetime
from pathlib import Path
import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from planner import engine, report, guardian, state as S  # noqa: E402
from planner.plan import gather  # noqa: E402

PACK = ROOT / "chat_pack.txt"
CHAT = ROOT / "state" / "chat_ui.json"
E = html.escape
N = lambda x: f"{x:,.0f}" if isinstance(x, (int, float)) else str(x)

st.set_page_config(page_title="Event Planner", page_icon="◆", layout="wide", initial_sidebar_state="collapsed")
st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Source+Serif+4:opsz,wght@8..60,500;8..60,600&display=swap');
:root{--ink:#18181B;--mute:#71717A;--line:#E4E4E7;--soft:#F4F4F5;--ok:#15803D;--warn:#B45309;--bad:#B91C1C;--acc:#1D4ED8}
html,body,.stMarkdown p,.stMarkdown div,.stMarkdown td,button p,textarea,input{font-family:Inter,system-ui,sans-serif}
#MainMenu,footer,header[data-testid="stHeader"],[data-testid="stToolbar"],[data-testid="stSidebarCollapsedControl"]{display:none!important}
.block-container{padding:1.6rem 2rem 1rem;max-width:1400px}
h1.title{font-family:'Source Serif 4',Georgia,serif;font-weight:600;font-size:1.65rem;letter-spacing:-.01em;margin:0;color:var(--ink)}
.sub{color:var(--mute);font-size:.9rem;margin:.15rem 0 .8rem}
.colhead{font-family:'Source Serif 4',Georgia,serif;font-size:1.2rem;font-weight:600;margin:0 0 .6rem;color:var(--ink)}
[data-testid="stChatMessage"]{animation:rise .22s ease-out;background:transparent;padding:.35rem .2rem}
@keyframes rise{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
.steps{position:relative;margin:.2rem 0 0}
.step{position:relative;padding-left:2.6rem;margin:0 0 .35rem}
.step:before{content:"";position:absolute;left:.86rem;top:2.1rem;bottom:-.5rem;width:1px;background:var(--line)}
.step:last-child:before{display:none}
.dot{position:absolute;left:0;top:.55rem;width:1.75rem;height:1.75rem;border-radius:50%;display:flex;align-items:center;justify-content:center;
 font-size:.78rem;font-weight:600;border:1px solid var(--line);background:#fff;color:var(--mute);transition:all .25s ease}
.done .dot{background:var(--ok);border-color:var(--ok);color:#fff}
.attn .dot{background:#fff;border-color:var(--warn);color:var(--warn)}
.work .dot{border-color:var(--acc);color:var(--acc);animation:pulse 1.2s ease-in-out infinite}
@keyframes pulse{50%{box-shadow:0 0 0 5px rgba(29,78,216,.12)}}
details{border:1px solid var(--line);border-radius:10px;background:#fff;transition:border-color .2s}
details[open]{border-color:#D4D4D8}
summary{list-style:none;cursor:pointer;display:flex;align-items:center;gap:.6rem;padding:.72rem .9rem}
summary::-webkit-details-marker{display:none}
summary .nm{font-weight:500;color:var(--ink)}
summary .hint{color:var(--mute);font-size:.85rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;flex:1;text-align:right}
.pill{font-size:.72rem;font-weight:500;padding:.1rem .5rem;border-radius:99px;background:var(--soft);color:var(--mute);white-space:nowrap}
.done .pill{background:#DCFCE7;color:var(--ok)}.attn .pill{background:#FEF3C7;color:var(--warn)}.work .pill{background:#DBEAFE;color:var(--acc)}
.body{padding:0 .9rem .85rem;color:#3F3F46;font-size:.9rem;animation:rise .2s ease-out}
.body table{width:100%;border-collapse:collapse;font-size:.86rem}
.body td{padding:.32rem 0;border-bottom:1px solid var(--soft)}.body td:last-child{text-align:right;font-variant-numeric:tabular-nums}
.body tr.tot td{font-weight:600;border-bottom:none;padding-top:.5rem}
.note{color:var(--warn);background:#FFFBEB;border-radius:8px;padding:.5rem .65rem;margin:.2rem 0 .5rem;font-size:.86rem}
.muted{color:var(--mute)}
.flash{animation:flash 1.6s ease-out}
@keyframes flash{0%{background:#EFF6FF}100%{background:#fff}}
.kpis{display:flex;gap:1.6rem;flex-wrap:wrap;margin:.1rem 0 1rem}
.kpi b{display:block;font-size:1.25rem;font-weight:600;color:var(--ink);font-variant-numeric:tabular-nums;transition:all .3s}
.kpi span{color:var(--mute);font-size:.78rem}
.slide{border:1px solid var(--line);border-radius:14px;background:#fff;padding:2.2rem 2.4rem;min-height:340px;animation:rise .25s ease-out}
.slide h2{font-family:'Source Serif 4',Georgia,serif;font-weight:600;font-size:1.6rem;margin:0 0 1rem}
.stButton button,.stDownloadButton button{border-radius:8px;border:1px solid var(--line);font-weight:500}
@media (prefers-reduced-motion:reduce){*{animation:none!important;transition:none!important}}
@media (max-width:760px){html,body,[data-testid="stAppViewContainer"],[data-testid="stMain"]{overflow-x:hidden;max-width:100vw}
 .block-container{padding:1rem .8rem;max-width:100vw!important;min-width:0!important}
 [data-testid="stHorizontalBlock"]{flex-wrap:wrap!important;gap:.5rem}
 [data-testid="stColumn"],[data-testid="column"]{width:100%!important;flex:1 1 100%!important;min-width:0!important}
 summary .hint{display:none}.kpis{gap:1rem}}
</style>""", unsafe_allow_html=True)


# ---------- chat history (kept beside the planner state; gitignored) ----------
def load_chat():
    try:
        return json.loads(CHAT.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def save_chat(h):
    CHAT.parent.mkdir(exist_ok=True)
    CHAT.write_text(json.dumps(h, ensure_ascii=False), encoding="utf-8")


if "chat" not in st.session_state:
    st.session_state.chat = load_chat()
SENDER = re.compile(r"^\s*(\d+\)\s*)?[A-Z][\w'’.&\- ]{1,40}(,[^:\n]{0,40})?:", re.M)


def as_message(text):
    """A pasted message keeps its own sender; plain chat text comes from the organiser."""
    m = SENDER.match(text)
    label = re.sub(r"^\s*\d+\)\s*", "", m.group(0)).split(",")[0].lower() if m else ""
    if m and len(label.split()) <= 4 and not re.search(r"quote|update|note|info|detail|plan|budget|price|option|"
                                                       r"request|change|venue option|menu|schedule|here", label):
        return text.strip()                      # looks like a pasted message with its own sender
    return f"Organizer (chat), {datetime.now():%d %b %Y}: {text.strip()}"


# ---------- plain-language reply built from real results (no extra model call) ----------
def friendly(reason):
    m = re.search(r"says (\w+) = ([\d,.]+); \w+ is computed = ([\d,.]+) \((.*?)\)\.", reason)
    if m:
        k = m[1].replace("_", " ")
        return f"The number of {k} is worked out automatically ({m[4]}), so I kept {m[3]} instead of {m[2]}."
    r = re.sub(r"\{[^}]*\}", "", reason)
    r = r.replace("derived-value claim: ", "").replace("no authority: ", "")
    r = re.sub(r"\s*\((msg \d+|authority|finance|student|caterer|venue|judging|judge|official|unknown)\)", "", r)
    r = r.split("; standing rule")[0]
    r = re.sub(r"; owner is ([\w/]+)", lambda m: "; only " + m[1].replace("authority", "the organiser").replace("/", " or ")
               + " can change that", r)
    return r.replace("cannot set", "can't change").strip().rstrip(".") + "."


def reply(before, stn, n0):
    new = stn["msgs"][n0:]
    if not new:
        return "I couldn't reach the planning AI just now (it may be busy). Please send that again in a few seconds."
    p, lines = stn.get("plan"), []
    if len(new) > 1:                                   # a pasted batch: one short summary instead of a line each
        dec = [(m.get("guardian") or {}).get("decision", "") for m in new]
        sup = sum(m["status"] == "superseded" for m in new)
        bits = [f"{sum(d.startswith('ACCEPTED') for d in dec) - sup} used", f"{sup} older ones replaced by newer info" if sup else "",
                f"{dec.count('REJECTED')} not allowed" if "REJECTED" in dec else "",
                f"{dec.count('QUARANTINED')} blocked as unsafe" if "QUARANTINED" in dec else "",
                f"{dec.count('FLAGGED')} from unknown senders" if "FLAGGED" in dec else ""]
        lines.append(f"I read {len(new)} messages: " + ", ".join(b for b in bits if b) + ".")
        new = []
    for m in new:
        g = m.get("guardian") or {}
        d = g.get("decision", "")
        if d == "QUARANTINED":
            lines.append("I ignored that message: it tries to change my instructions or asks for secrets, so it can't change your plan.")
        elif d == "REJECTED":
            lines.append("I didn't apply that change. " + friendly(g.get("reason", m["reason"])))
        elif d == "FLAGGED":
            lines.append("I couldn't tell who that came from, so I haven't changed anything for it.")
        elif m["status"] == "superseded":
            lines.append("That information is older than what I already have, so I kept the newer value.")
        elif m["status"] == "no impact":
            lines.append("Noted. That doesn't change anything in the plan.")
    run = stn["runs"][-1]
    changed = [STEP_OF[a] for a in run.get("changed", []) if a in STEP_OF]
    ever_ok = any(not r.get("infeasible") and not r.get("failed") for r in stn["runs"][:-1])
    if p and stn.get("infeasible") and not ever_ok:
        need = missing_hints(stn)
        lines.append("Got it — I've started your plan. To finish it I still need: " +
                     ("; ".join(need) if need else friendly("; ".join(stn["infeasible"])).rstrip(".")) + ".")
    elif p and stn.get("infeasible"):
        lines.append("I recorded the change, but the plan can't work as it stands: " + friendly("; ".join(stn["infeasible"]))
                     + " I'm keeping the last workable plan until that's fixed.")
    elif p and (changed or not before):
        b, a = before or {}, engine.headline(p)
        what = ", ".join(changed) if before else "your full plan"
        tot = f" Total is Rs {N(a['total'])}" + (f" (was Rs {N(b['total'])})" if b.get("total") not in (None, 0, a["total"]) else "")
        lines.append(f"Done — I updated {what}.{tot}, with Rs {N(a['remaining'])} left in the budget.")
    elif not p:
        need = missing_hints(stn)
        lines.append("Got it. To build the plan I still need: " + "; ".join(need) + "." if need else "Got it.")
    return " ".join(lines) or "Noted — nothing in the plan needed to change."


# ---------- the seven planning steps, computed from real planner data ----------
STEPS = ["Event Details", "Venue & Capacity", "Schedule & Activities", "Food & Catering", "Team & Judging Setup",
         "Budget & Expenses", "Final Event Plan"]
STEP_OF = {"venue": "Venue", "schedule": "Schedule", "food": "Food", "judging": "Judging", "budget": "Budget"}
AREA_IDX = {"venue": 1, "schedule": 2, "food": 3, "judging": 4, "budget": 5}


def missing_hints(stx):
    Sx, D = gather(stx)
    ks = lambda k: [d for d in D if d["_k"] == k]
    need = []
    ev = [n for k, n in (("students", "how many people attend"), ("team_size", "team size"),
                         ("duration_min", "how long the event runs"), ("budget", "the total budget")) if k not in Sx]
    if ev:
        need.append(", ".join(ev))
    if not ks("venue"):
        need.append("venue options with seats and price")
    if not ks("food"):
        need.append("catering price per person")
    if "judges_available" not in Sx:
        need.append("how many judges are available")
    return need


def table(rows, total=None):
    t = "".join(f"<tr><td>{E(str(a))}</td><td>{E(str(b))}</td></tr>" for a, b in rows)
    if total:
        t += f"<tr class='tot'><td>{E(total[0])}</td><td>{E(total[1])}</td></tr>"
    return f"<table>{t}</table>"


def steps_view(stx, working=(), flash=()):
    p = stx.get("plan") if stx else None
    probs = (stx or {}).get("infeasible") or []
    Sx, D = gather(stx) if stx else ({}, [])
    ks = lambda k: [d for d in D if d["_k"] == k]
    out = []

    def attn(words):
        return [x for x in probs if re.search(words, x, re.I)]

    for i, name in enumerate(STEPS):
        status, hint, body = "wait", "Waiting", "<span class='muted'>Nothing yet.</span>"
        if p:
            F, B, V, FD, SC = p["figures"], p["budget"], p["venue"], p["food"], p["schedule"]
            if i == 0:
                hint = f"{F['students']} people · {F['duration_min'] / 60:g} h · Rs {N(F['budget'])}"
                body = table([("Participants", F["students"]), ("Team size", F["team_size"]), ("Teams", F["teams"]),
                              ("Staff", F["staff"]), ("Duration", f"{F['duration_min']} min"),
                              ("Start", SC["start"] + (" (assumed)" if SC["assumed"] else "")), ("Budget", f"Rs {N(F['budget'])}")])
            elif i == 1:
                hint = f"{V.get('name')} · {V.get('seats')} seats"
                body = table([("Chosen venue", V.get("name")), ("Seats", V.get("seats")), ("People to seat", F["headcount"]),
                              ("Cost", f"Rs {N(V.get('cost'))}")] + ([("Must have", ", ".join(V["required"]))] if V["required"] else [])) + \
                    "".join(f"<div class='muted' style='margin-top:.35rem'>Not chosen: {E(r['name'])} — {E(r['why'])}</div>" for r in V["rejected"])
            elif i == 2:
                hint = f"{len(SC['blocks'])} blocks · starts {SC['start']}"
                body = table([(b["time"], f"{b['name']} · {b['min']} min") for b in SC["blocks"]])
            elif i == 3:
                hint = f"{FD.get('name')} · {FD.get('boxes')} meals"
                body = table([("Option", FD.get("name")), ("Meals", f"{FD.get('boxes')} (everyone attending)"),
                              ("Price per person", f"Rs {N(FD.get('pph'))}")] + ([("Delivery / fee", f"Rs {N(FD['fee'])}")] if FD.get("fee") else [])
                             + [(f"Diet: {d['type']}", d.get("n") or f"{d.get('pct')}%") for d in FD["diet"]],
                             ("Food cost", f"Rs {N(FD.get('cost'))}"))
            elif i == 4:
                hint = f"{F['teams']} teams · {F['judges_used']} judges"
                body = table([("Teams", F["teams"]), ("Judges needed", F["judges_used"]), ("Judges available", F["judges_available"]),
                              ("On standby", F["standby"]), ("Judging", f"{F['rounds']} rounds × {F['min_per_team']} min = {F['judging_min']} min")])
            elif i == 5:
                hint = f"Rs {N(B['total'])} of Rs {N(B['budget'])}"
                body = table([(l["line"].replace("Committed: ", ""), f"Rs {N(l['amount'])}") for l in B["lines"]]
                             + ([("Kept in reserve", f"Rs {N(B['reserve'])}")] if B["reserve"] else []),
                             ("Total", f"Rs {N(B['total'])}")) + f"<div class='muted' style='margin-top:.35rem'>Remaining: Rs {N(B['remaining'])}</div>"
            else:
                ok = sum(c["ok"] for c in stx["checks"] or [])
                hint = f"{ok} of 6 checks passed"
                plain = {"Correct figures": "All numbers add up", "Within budget": "Stays within budget",
                         "Venue fits": "Venue fits everyone", "Schedule valid": "Schedule fits the time",
                         "Enough judges": "Enough judges", "All areas covered": "Every part is planned"}
                body = table([(plain.get(c["name"], c["name"]), "✓" if c["ok"] else "✗") for c in stx["checks"] or []])
            status = "done"
            words = [None, r"venue", r"schedule|window|late", r"food", r"judge", r"budget", None][i]
            a = attn(words) if words else ([] if i != 6 else probs)
            if a:
                status, hint = "attn", "Needs attention"
                body = "".join(f"<div class='note'>{E(friendly(x))}</div>" for x in a) + body
        elif stx and stx.get("msgs"):
            known = [bool(set(Sx) & {"students", "team_size", "duration_min", "budget"}), bool(ks("venue")), False,
                     bool(ks("food")), "judges_available" in Sx, "budget" in Sx, False][i]
            need = {0: "people, team size, duration and budget", 1: "venue options: name, seats, price",
                    3: "catering price per person", 4: "judges available, fee, minutes per team"}.get(i)
            if i in (0, 1, 3, 4):
                status, hint = ("attn", "Needs details")
                body = f"<div class='note'>Tell me: {E(need)}.</div>" + (
                    "<span class='muted'>Some details received.</span>" if known else "")
        if i in working:
            status, hint = "work", "Planning…"
        label = {"done": "Completed", "attn": "Needs attention", "work": "Planning", "wait": "Waiting"}[status]
        icon = "✓" if status == "done" else str(i + 1)
        out.append(f"<div class='step {status}'><div class='dot'>{icon}</div><details {'open' if i in flash or (status == 'attn' and i < 6) else ''}"
                   f" class='{'flash' if i in flash else ''}'><summary><span class='nm'>{i + 1}. {name}</span>"
                   f"<span class='pill'>{label}</span><span class='hint'>{E(hint)}</span></summary><div class='body'>{body}</div></details></div>")
    return "<div class='steps'>" + "".join(out) + "</div>"


def kpis(p):
    if not p:
        return ""
    F, B = p["figures"], p["budget"]
    items = [(F["headcount"], "people to host"), (p["venue"].get("name"), "venue"),
             (f"Rs {N(B['total'])}", "total cost"), (f"Rs {N(B['remaining'])}", "remaining")]
    return "<div class='kpis'>" + "".join(f"<div class='kpi'><b>{E(str(a))}</b><span>{b}</span></div>" for a, b in items) + "</div>"


def slides(p, stx):
    F, B, V, FD, SC = p["figures"], p["budget"], p["venue"], p["food"], p["schedule"]
    return [("Your event", table([("People", F["headcount"]), ("Teams", F["teams"]), ("Duration", f"{F['duration_min']} min"),
                                  ("Budget", f"Rs {N(F['budget'])}")])),
            ("Venue", table([("Venue", V.get("name")), ("Seats", V.get("seats")), ("Cost", f"Rs {N(V.get('cost'))}")])),
            ("Schedule", table([(b["time"], b["name"]) for b in SC["blocks"]])),
            ("Catering", table([("Option", FD.get("name")), ("Meals", FD.get("boxes")), ("Cost", f"Rs {N(FD.get('cost'))}")])),
            ("Judging", table([("Judges", F["judges_used"]), ("Rounds", f"{F['rounds']} × {F['min_per_team']} min")])),
            ("Budget", table([(l["line"].replace("Committed: ", ""), f"Rs {N(l['amount'])}") for l in B["lines"]],
                             ("Total", f"Rs {N(B['total'])}")))]


# ---------- layout ----------
stx = S.load(PACK)
p = stx.get("plan") if stx else None
top_l, top_r = st.columns([3, 2])
top_l.markdown("<h1 class='title'>Event Planner</h1><p class='sub'>Describe your event, paste messages from vendors, "
               "or ask for changes — in English or Roman Urdu.</p>", unsafe_allow_html=True)
with top_r:
    b1, b2, b3 = st.columns(3)
    if b1.button("View Plan Slides" if not st.session_state.get("slides") else "Close Slides", disabled=not p,
                 use_container_width=True):
        st.session_state.slides = not st.session_state.get("slides")
        st.session_state.slide = 0
        st.rerun()
    b2.download_button("plan.md", report.plan_md(stx) if stx else "", file_name="plan.md", disabled=not p,
                       use_container_width=True)
    if b3.button("New plan", use_container_width=True):
        for f in (PACK, S.path_for(PACK), CHAT):
            Path(f).unlink(missing_ok=True)
        st.session_state.clear()
        st.rerun()

if st.session_state.get("slides") and p:
    sl = slides(p, stx)
    k = st.session_state.get("slide", 0) % len(sl)
    st.markdown(f"<div class='slide'><div class='muted' style='font-size:.8rem'>{k + 1} / {len(sl)}</div><h2>{E(sl[k][0])}</h2>{sl[k][1]}</div>",
                unsafe_allow_html=True)
    c1, c2, _, c4 = st.columns([1, 1, 4, 1])
    if c1.button("← Previous", use_container_width=True):
        st.session_state.slide = k - 1
        st.rerun()
    if c2.button("Next →", use_container_width=True):
        st.session_state.slide = k + 1
        st.rerun()
    if c4.button("Close", use_container_width=True):
        st.session_state.slides = False
        st.rerun()
    st.stop()

left, right = st.columns([2, 3], gap="large")
with left:
    st.markdown("<div class='colhead'>Chat</div>", unsafe_allow_html=True)
    box = st.container(height=560, border=False)
    with box:
        if not st.session_state.chat:
            st.markdown("<div class='muted' style='padding:.4rem .2rem'>Start by describing your event, for example how many "
                        "people, how long, the budget, and any venue or catering quotes you have. You can also paste "
                        "messages you received from vendors, one at a time.</div>", unsafe_allow_html=True)
        for m in st.session_state.chat:
            with st.chat_message(m["role"]):
                st.markdown(m["text"])
    if not st.session_state.chat and (ROOT / "tests" / "sample_pack.txt").exists():
        if st.button("Try the example event", help="Loads tests/sample_pack.txt as the first message"):
            st.session_state.pending = (ROOT / "tests" / "sample_pack.txt").read_text(encoding="utf-8")
            st.rerun()
    prompt = st.chat_input("Message the planner…")
    if prompt or st.session_state.get("pending"):
        prompt = prompt or st.session_state.pop("pending")
        st.session_state.chat.append(dict(role="user", text=prompt if len(prompt) < 600 else prompt[:600] + " …"))
        st.session_state.run_text = prompt
        save_chat(st.session_state.chat)
        st.rerun()

with right:
    st.markdown("<div class='colhead'>Your Event Plan</div>", unsafe_allow_html=True)
    kp = st.empty()
    kp.markdown(kpis(p), unsafe_allow_html=True)
    holder = st.empty()
    text = st.session_state.pop("run_text", None)
    if text:
        # Real processing: steps show "Planning…" only while engine.run() is actually executing.
        holder.markdown(steps_view(stx, working=range(7) if not p else ()), unsafe_allow_html=True)
        with st.spinner("Planning…"):
            before = engine.headline(p) if p else None
            n0 = len(stx["msgs"]) if stx else 0
            old = PACK.read_text(encoding="utf-8") if PACK.exists() else ""
            with open(PACK, "a", encoding="utf-8") as fh:
                fh.write(("\n\n" if old and not old.endswith("\n\n") else "") + as_message(text) + "\n")
            stx = engine.run(str(PACK), echo=False)
        p = stx.get("plan")
        run = stx["runs"][-1] if stx["runs"] else {}
        flash = {AREA_IDX[a] for a in run.get("changed", []) if a in AREA_IDX} | ({6} if run.get("changed") else set())
        st.session_state.flash = sorted(flash) if before else []
        st.session_state.chat.append(dict(role="assistant", text=reply(before, stx, n0)))
        save_chat(st.session_state.chat)
        st.rerun()
    holder.markdown(steps_view(stx, flash=st.session_state.pop("flash", [])), unsafe_allow_html=True)

    with st.expander("Technical details", expanded=False):
        if stx:
            v = guardian.verify(stx.get("audit", []))
            st.caption(f"AI model calls: {stx['calls']} · tokens reported by the API: {stx['tokens']:,} · "
                       f"security audit: {'intact' if v['ok'] else 'BROKEN'} ({len(stx.get('audit', []))} entries)")
            rows = report.token_rows(stx)
            st.dataframe([{"#": r[0], "Model": r[2], "Area": r[3], "Prompt": str(r[4]), "Completion": str(r[5]),
                           "Total": str(r[6])} for r in rows], hide_index=True)
            st.dataframe([{"Msg": m["n"], "From": m["frm"], "Decision": (m.get("guardian") or {}).get("decision", m["status"]),
                           "Why": (m.get("guardian") or {}).get("reason", m["reason"])[:160]} for m in stx["msgs"]], hide_index=True)
            st.caption("Full trace: out/trace.txt · developer dashboards: `streamlit run ui/app.py`, `python ui/studio.py`")
        else:
            st.caption("No runs yet.")
