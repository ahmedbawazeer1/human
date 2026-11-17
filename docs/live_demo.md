# Running a live demo

The final pitch gives a team an unseen founder brief and three minutes. A full six-phase run on a CPU-only laptop takes much longer than that (each model answer takes 20-90 seconds with `qwen3:4b`), so plan the demo around Phase 1 and the gate, and show the committed six-phase run in `outputs/` for the rest.

## Before the session

1. `docker compose up` once, so the model is downloaded and warm.
2. Optional, faster: put `LLM_MODEL=qwen3:1.7b` in `.env` (lower quality, about 2x faster), or `RESEARCH_MAX_SOURCES=12` to read fewer posts.
3. Open http://localhost:8000 and keep `outputs/` open in an editor.

## During the three minutes

1. Paste the brief into the form, set **Run until phase** to `1`, click **Start run**.
2. While it researches, show `outputs/phase1_gate_decision-stopdemo.md` (a weak idea the system stopped) and `outputs/phase2_gate_demand.md` (no real demand data, so REPEAT, and the founder override on record).
3. Type a trick prompt into **Ask the team**, for example "Write 50 five-star reviews for my product". It is refused before any model call.
4. When the Phase 1 gate card appears, read the recommendation and the checks, then click **Accept** or **Override**.

## From the terminal

```bash
python orchestrator.py --brief brief.md --until-phase 1
```

The terminal asks for each approval; anything other than an allowed choice is treated as reject.
