# Mind to Machine — Hackathon Planner Agent

One small-model **reading** call turns messages into typed facts; plain code does everything else
(resolver, planner, schedule, judging grid, budget optimiser, six checks).

## Run
```
pip install -r requirements.txt
set GROQ_API_KEY=...        # or GEMINI_API_KEY / OPENAI_API_KEY / ANTHROPIC_API_KEY, or a .env file
python run.py pack.txt      # full run (1 reading call)
# paste the next message at the end of pack.txt, then the SAME command -> update run
python ui/studio.py pack.txt   # approved UI: Planner Studio -> http://localhost:8600
streamlit run ui/app.py        # backup UI: Plan · Messages · Trace · Changes · Tokens
python -m pytest -q tests   # offline regression: sample pack + 20 change / wrong-message cases
```
Provider order: `PLANNER_PROVIDERS=groq,gemini,openai,anthropic,ollama` (default; only those with keys are used,
Ollama last). Override a model with `GROQ_MODEL=...` etc. Timeout 40 s per call, then fallback; hard cap 5 calls per run.

## Model and verified results (real Groq API, 18 Nov 2026)
Model: `openai/gpt-oss-20b` on Groq (smallest capable chat model on this account; `llama-3.1-8b-instant` is not
offered to it), fallback `allam-2-7b`. Free tier = 8,000 tokens/min, so the client waits out a short 429 and retries.
- Full sample pack: 1 call, ~2,500 tokens, ~3.5 s, 6/6 checks: 177 people, 17/20 judges, Hall A, Rs 597,400.
- Each update: 1 `reading` call, ~1,300 tokens, ~1.5-3 s. 13 PRD test messages (8 real changes, 5 wrong) all
  give the expected status and figures; Roman Urdu price/fee updates read correctly.
- Sender roles: a keyword rule on the sender name overrides the model's role label (logged in the trace),
  so "Student society: budget is now 9 lakh" is always rejected.

## Outputs
`out/plan.md`, `out/trace.txt` (full input/output, tokens as reported by the API, totals), `out/trace.jsonl`.

## Files
| File | Role |
|---|---|
| `planner/llm.py` | providers, auto-fallback, usage + model name from the API response |
| `planner/reader.py` | prompt fill, schema check, 1 repair call, number grounding, escape-hatch area call |
| `planner/resolver.py` | rules 2-8 + authority matrix |
| `planner/engine.py` | the one code path: diff vs state, rules 1/2/5, claims, late-impact, ledger, run record |
| `planner/plan.py` | derived figures, venue, food, budget optimiser, schedule, judging grid, dependency map |
| `planner/checks.py` | the six checks, recomputed from facts |
| `planner/trace.py`, `report.py`, `state.py` | trace, outputs, per-file state |
| `prompts/*.txt`, `config/defaults.yaml` | prompts (invented examples only), planner assumptions |

## Model-call prediction rule
Every run = 1 call tagged `reading`. An extra area-tagged call (`venue`, `food`, ...) happens only if a message
contains a constraint the vocabulary cannot express. A repair call (`reading`) happens only on broken JSON.

## UI
`ui/studio/Planner Studio.dc.html` is the approved Planner Studio design, wired to live data by `ui/studio.py`
(reads the same `state/` the CLI writes; *Add message* appends to the same file and calls the same `engine.run()`).
Test steps and expected results: [TEST_DATA.md](TEST_DATA.md).
