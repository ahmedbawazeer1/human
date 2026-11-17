# Open Venture Builder

An open-source team of AI agents that takes a founder's brief toward a validated, sellable **digital** product, through six phases (Discover, Validate, Build, Commercial setup, Launch, Operate and learn) with a gate after every step. It cites real sources or labels claims `ASSUMPTION`, keeps the founder in control of everything that goes out, and **recommends STOP when the evidence is weak**. Runs on a local open-weight model; costs $0 per run. Pitch: [docs/pitch.md](docs/pitch.md).

## Quickstart

```bash
docker compose up
```

Then open **http://localhost:8000**, load an example brief (or paste your own), and click **Start run**. The first start downloads the open-weight model (`qwen3:4b`, about 2.5 GB). When a gate or an outbound action needs you, an **Approve / Reject** (or **Accept / Override**) card appears on the run page.

Command-line alternative (needs Python 3.11+ and a running Ollama):

```bash
pip install -r requirements.txt
```

```bash
python orchestrator.py --brief briefs/scope_creep_toolkit.md
```

Smoke tests (offline, no model needed):

```bash
pytest -q
```

## What works and what is mocked

| Step | Status |
|---|---|
| Phase 1 Discover: brief intake and excluded-category screen | **Working** |
| Phase 1 Discover: find opportunities (real Hacker News, Stack Exchange, Show HN, GitHub data; quotes verified by code) | **Working** |
| Phase 1 Discover: score idea vs alternatives, define market | **Working** |
| Phase 1 Discover: Mom Test script and analysis of founder's real interview notes | **Working** (interviews are never simulated) |
| Phase 1 evidence gate (go / repeat / pivot / stop) | **Working** |
| Phase 2 Validate: Lean Canvas, landing page, demand-test plan | **Working** |
| Phase 2: publishing the landing page | **MOCKED** (approved pages go to a local outbox) |
| Phase 2: real traffic and sign-up numbers | **STUBBED** (founder supplies real numbers with `--metrics`; local waitlist form works) |
| Phase 3 Build: MVP spec, product (Markdown toolkit), user docs, QA tests, rebuild loop | **Working** |
| Phase 4 Commercial: pricing, draft terms / privacy / refund policies, founder sign-off | **Working** (no payments of any kind) |
| Phase 5 Launch: store page and launch posts, each approved by the founder | **Working** (drafts) |
| Phase 5: publishing posts, opening the store | **MOCKED** |
| Phase 5: checkout, payment provider, payouts | **MOCKED** (in-process mock, test buyers only) |
| Phase 5: automatic delivery, idempotency, refund revokes access, reconciliation | **Working** against the **MOCKED** provider |
| Phase 5: delivery emails | **MOCKED** (logged, not sent) |
| Phase 6 Operate: support FAQ and replies, metrics, persevere-or-pivot memo | **Working** |
| Founder approval for every publish / send / spend / sign (CLI, web UI, decisions file) | **Working**, enforced in code |
| Guardrails against trick prompts (fake reviews, urgency, impersonation, income promises, moving money) | **Working** |
| Decision log (`decision_log.json`, one entry per agent action) | **Working** |

## Architecture

One orchestrator (`orchestrator.py`) runs single-purpose agents (`agents/*.py`) phase by phase. After each phase a gate (`gates.py`) compares the evidence with thresholds that were written down before the evidence was collected, and recommends go, repeat, pivot or stop; the founder accepts or overrides, and both are logged. The trust-critical parts are plain code, not model output: quote verification against fetched sources, scoring arithmetic, gate rules, product tests, guardrails (`guardrails.py`), the approval check (`approval.py`, hash-bound to the exact content), and the sale-to-cash logic (`payments.py`, `webhooks.py`, `delivery.py`, `refunds.py`, `reconcile.py`). Full design with diagrams: [ARCHITECTURE.md](ARCHITECTURE.md).

## Models and free resources

- **Default model:** `qwen3:4b` (Apache-2.0 open weights) via **Ollama**, started by `docker compose up`. No API key, no account, no paid service.
- **Smaller / bigger laptops:** set `LLM_MODEL=qwen3:1.7b` (faster) or `LLM_MODEL=qwen3:8b` (better) in `.env`.
- **Any OpenAI-compatible server works:** llama.cpp server, vLLM, LM Studio, or a free hosted tier serving open-weight models such as GPT-OSS 20B/120B. Set `LLM_BASE_URL`, `LLM_MODEL` and (in an untracked `.env`) `LLM_API_KEY`. Nothing requires payment.
- **Research sources:** Hacker News Algolia API, Stack Exchange API, GitHub search API: free and keyless.
- The demo run in `outputs/` used `qwen3:4b` (Q4_K_M GGUF, the same weights Ollama serves) on a 4-core CPU with no GPU.

## Cost per run

**About $0.00 per run** (local open-weight model; the full six-phase demo run used 19,616 tokens over 23 model calls, about 20 minutes of model time on a 4-core CPU with no GPU). Exact per-run token counts and cost are printed at the end of each run and written into every gate file; each model call's cost is in `decision_log.json`. If you point the system at a metered endpoint, set `LLM_COST_IN_PER_1K` / `LLM_COST_OUT_PER_1K` and the same figures are computed in dollars.

## Demo video

Recording of the prototype running: link will be added here (3 minutes at most).

## What our system will NOT do

- Promise income, sales or success. The output scanner removes such claims and the QA gate fails a product that contains them.
- Write fake reviews, testimonials, ratings, user counts, sign-ups, countdown timers or scarcity. Requests for them are refused (see `evals/trick_prompts.txt`).
- Pose as the founder, a customer, another brand or a real person. Launch posts are drafts in the founder's own voice for the founder to post.
- Publish, send, spend or sign anything without an explicit founder approval bound to the exact content. With no founder present, everything is rejected.
- Hold, move or refund money, create accounts, or store passwords or card numbers. Payments are MOCKED; refunds are approved by the founder and executed by the provider.
- Simulate customers, interviews or demand data. No data means the gate says "repeat", not "go".
- Build physical goods, financial/investment/crypto products, or health or legal advice products. That stop cannot be overridden.
- Hide core features behind a paywall: the whole system is MIT-licensed and free to self-host.

## How the project stays alive after the hackathon

- **Maintainers:** the founding team maintains `main`; contributions via pull requests with the smoke tests required to pass.
- **Roadmap:** real publishing connectors behind the same approval check, more evidence sources with quote verification, more product formats, resuming a run from any gate (see [ARCHITECTURE.md](ARCHITECTURE.md#roadmap)).
- **Community:** prompts live in `prompts/` and thresholds in `config/gates.json`, so people can improve them without touching code; trick prompts in `evals/` grow with every new attack we see.
- **Funding:** the tool stays free and open (MIT). Running cost is $0 on local models, so the project does not depend on API credits. Possible support: sponsorships, grants for open-source AI tooling, and paid help setting it up for incubators, never a paywall on core features.
