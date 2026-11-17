# Pitch: Open Venture Builder

Team Human: Ahmed Bawazeer, Fidaa Aldeen Wadaan, Ahmed Alaidaroos. Slides in text form (one `##` per slide).

## 1. The problem

First-time founders get two kinds of help from AI tools today: a generic business plan, or a tool that says "yes" to every idea. Neither tells them **"don't build this"** when the evidence is weak, and most of them run on closed, paid platforms that lock the founder's data in.

- The cost of a wrong "yes" is weeks of the founder's time and savings spent on something nobody asked for. (**ASSUMPTION**: we did not measure this; it is the motivation, not a statistic.)

## 2. The user

A solo founder or student with a starting idea, some skills, a small budget ($50-$500) and a few hours a week, who wants to sell a **digital** product (templates, guides, small tools) and wants an honest answer before spending money.

## 3. What we built

An open-source team of agents that takes a short founder brief through six phases: **Discover, Validate, Build, Commercial setup, Launch, Operate**, with a gate after every step that recommends **go / repeat / pivot / stop**.

- Real public evidence (Hacker News, Stack Exchange, Show HN, GitHub), every quote checked by code against its source.
- Claims without a source are printed as **ASSUMPTION**.
- Nothing is published, sent, spent or signed without the founder's approval, enforced in code and bound to the exact content.
- Runs on a local open-weight model (`qwen3:4b`): **$0 per run**.

## 4. Live results from our demo run (in `outputs/`)

| Founder brief | What the system did |
|---|---|
| Crypto trading-signals channel | **STOP** at the policy gate (excluded category, cannot be overridden) |
| App with motivational quotes "from your houseplant" | **STOP**: 1 verified pain signal, score 31/100, "do not launch" |
| Scope-creep toolkit for freelance web developers | 3 verified pain signals, score 59.9/100 (threshold 60), **REPEAT** recommended; founder override logged; product built and tested; MOCKED sale-to-cash test passed 12/12 steps; final memo: no real sales yet, do not invest more until real demand exists |

Guardrails: **50/50** trick prompts and checks pass (`evals/results.md`).

## 5. Why open beats closed

- **Trust:** every decision is in `decision_log.json` with its sources, model, cost and who approved it. A closed tool asks you to trust its output; ours shows its work.
- **Cost:** a local open-weight model means $0 per run and no API key, so students and founders in any country can use it.
- **Control:** thresholds (`config/gates.json`) and prompts (`prompts/`) are plain files the founder can read and change.
- **Safety by design:** the rules that matter (quote checks, gates, approvals, no money movement) are code, not prompts, so a small or tricked model cannot get around them.

## 6. What the system will NOT do

- Promise income or success.
- Write fake reviews, testimonials, sign-ups, countdowns or scarcity.
- Pose as the founder, a customer or another brand (product names that clash with existing products are renamed automatically).
- Hold, move or refund money, create accounts, or store passwords or card numbers.
- Simulate customers, interviews or demand data.
- Build physical goods, financial/crypto, health or legal advice products.

## 7. Realistic roadmap

| When | What |
|---|---|
| Month 1 | Resume a run from any gate with new evidence (real interview notes, real sign-up numbers). |
| Month 2 | Publishing connectors that post from the founder's own accounts, still behind the same approval check. |
| Month 3 | More evidence sources with the same quote verification; more product formats (small web tools with generated tests). |
| Month 4+ | Payment-provider adapter in test mode behind the existing webhook / idempotency / reconciliation code. |

## 8. How the project stays alive

- **Maintainers:** the three of us maintain `main`; CI runs the smoke tests and guardrail evals on every push.
- **Community:** prompts, thresholds and trick prompts are plain files, so contributors can improve them without touching code.
- **Funding:** MIT licence, $0 running cost. Support from sponsorships, open-source AI grants and paid setup help for incubators; never a paywall on core features.

## 9. Honest limits today

- A CPU-only laptop needs about 20 minutes of model time for a full six-phase run (a free hosted open-weight model is much faster).
- Demand testing needs real traffic, which a demo cannot provide; the system says so and recommends REPEAT instead of inventing numbers.
- Publishing, payments and delivery emails are MOCKED.
