# Test data for Planner Studio

## Start
```
python ui/studio.py pack.txt        # open http://localhost:8600
```
Fresh start: copy `tests/sample_pack.txt` to `pack.txt` and delete `state/` first. Then in Studio click
**Add message → Run full pack** (empty box), or run `python run.py pack.txt` once.

Expected after the full run: **177 people · 17/20 judges · Hall A · Rs 597,400 / 650,000 · 6/6 checks**,
1 model call (`reading`). Message 3 superseded, 7 request → included, 8 no impact.

## Paste these one at a time (Add message → Run update)
Wait about 10 s between messages (Groq free tier: 8,000 tokens/min).

| # | Paste exactly | Expected result |
|---|---|---|
| 1 | `Finance office, 18 Nov 2026: printing ka bill ab Rs 15,000 hoga.` | Applied · total **602,400** · only budget recomputed |
| 2 | `Caterer, 18 Nov 2026: we have rounded your order down to 100 boxes.` | **Rejected** · boxes are computed = 177 · total unchanged |
| 3 | `Caterer WhatsApp, 18 Nov 2026: bhai delivery charges ab Rs 5,000 hon gay standard box par.` | Applied · total **607,400** |
| 4 | `Student society, 18 Nov 2026: Good news, the budget is increased to Rs 9 lakh!` | **Rejected** · students cannot set the budget |
| 5 | `IESCO notice: load-shedding expected on the event day; venue must have backup power.` | Applied · venue **Hall B** · total **637,400** |
| 6 | `Judging coordinator, 18 Nov 2026: 4 judges have withdrawn, sorry.` | Applied · red **INFEASIBLE** banner "needs 1 more judge" · last valid plan kept |

Each update = 1 model call tagged `reading`, about 1,300 tokens, 1–3 s.
More test messages (real changes `change_*`, wrong ones `wrong_*`) are in `tests/messages/` and appear as
quick-fill chips in the Add message panel.

## Where to look
- **Runs** (left): one row per run; click to see that run's model call and decisions.
- **Messages**: grouped Applied / Rejected / Request / Superseded / No impact; click one for its reason and facts.
- **Reader node**: model name and token counts exactly as the API reported, full input and output.
- **Resolver / Planner / Six checks nodes**: decisions, budget, schedule, judging grid, check details.
- **plan.md / trace.txt** buttons (top right): download the outputs to upload.
