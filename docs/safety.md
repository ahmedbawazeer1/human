# Safety and founder control

Three layers, all plain code so a small or tricked model cannot get around them.

| Layer | Where | What it does |
|---|---|---|
| Brief screen | `guardrails.screen_brief` | Stops excluded products (physical goods, financial/crypto, health or legal advice). This stop cannot be overridden by the founder. |
| Request screen | `guardrails.screen_request` | Refuses fake reviews, fake sign-ups, fake urgency, impersonation, income promises, moving money, storing credentials, paywalling core features and spam, **before** any model call. |
| Output scanner | `guardrails.scan_output` | Removes income promises, fake social proof and fake urgency from anything a model wrote, and logs each removal in `decision_log.json`. |
| Approval lock | `approval.require_approved` | Every publish, send, spend or sign checks for a founder approval whose hash matches the exact content. With nobody there to ask, the default is reject. |

Results on the trick-prompt suite: [`evals/results.md`](../evals/results.md) (re-run with `python evals/run_evals.py`).
