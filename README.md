# Mind to Machine — Hackathon Planner Agent

One small-model **reading** call turns messages into typed facts; plain code does everything else
(resolver, planner, schedule, judging grid, budget optimiser, six checks).

## Run
```
pip install -r requirements.txt
set GROQ_API_KEY=...        # or GEMINI_API_KEY / OPENAI_API_KEY / ANTHROPIC_API_KEY, or a .env file
python run.py pack.txt      # full run (1 reading call)
# paste the next message at the end of pack.txt, then the SAME command -> update run
streamlit run ui/app.py     # Plan · Messages · Trace · Changes · Tokens
python -m pytest -q tests   # offline regression: sample pack + 20 change / wrong-message cases
```
Provider order: `PLANNER_PROVIDERS=groq,gemini,openai,anthropic,ollama` (default; only those with keys are used,
Ollama last). Override a model with `GROQ_MODEL=...` etc. Timeout 40 s per call, then fallback; hard cap 5 calls per run.

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
