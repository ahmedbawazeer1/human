---
marp: true
paginate: true
title: Open Venture Builder
---

# Open Venture Builder

### An open-source AI team that can tell a founder **"don't launch this"**

Team Human: Ahmed Bawazeer · Fidaa Aldeen Wadaan · Ahmed Alaidaroos
MADS × CSEA AI Hackathon · Fall 2026 · MIT licence · $0 per run

<!-- ملاحظة للمقدّم: عرّف بالفريق في جملة. الفكرة الأساسية: فريق وكلاء ذكاء اصطناعي مفتوح المصدر، صادق، والمؤسس هو صاحب القرار. -->

---

## The problem

- First-time founders get two kinds of AI help: a generic business plan, or a tool that says **"yes"** to every idea.
- Almost none of them say **"stop, the evidence is weak"**.
- Most run on closed, paid platforms that keep the founder's data. (**ASSUMPTION**: our own observation, not a measured study.)

<!-- قل: المشكلة مو قلة الأدوات، المشكلة إن الأدوات تجامل. "نعم" غلط تكلّف المؤسس وقته وفلوسه. -->

---

## The user

A solo founder or student with:

- a starting idea and some skills
- a small budget ($50-$500) and a few hours a week
- a **digital** product in mind (templates, guides, small tools)
- the wish for an **honest answer before spending money**

<!-- قل: صممناه لطالب أو مؤسس لوحده، ميزانيته صغيرة، ويبغى جواب صادق قبل ما يصرف. -->

---

## What we built: six phases, a gate after every step

```
Discover → Validate → Build → Commercial setup → Launch → Operate & learn
   🚦          🚦        🚦            🚦             🚦           🚦
       go · repeat · pivot · stop   (thresholds fixed BEFORE evidence)
```

- 12 role agents (intake, researcher, strategist, interviewer, validator, builder, QA, pricing, legal, launcher, operator, assistant)
- One orchestrator, one decision log: **every action recorded** with sources, model, cost, approver
- Runs on a free open-weight model: local `qwen3:4b`, or GPT-OSS 120B on a free tier

<!-- قل: ست مراحل، وبعد كل خطوة بوابة. الحدود مكتوبة قبل ما نجمع الأدلة عشان ما نغش النتيجة. -->

---

## Evidence you can check

- Real public sources: Hacker News, Stack Exchange, Show HN, GitHub
- Every quote is **checked by code** against the fetched page; quotes that are not there, or off-topic, are dropped and logged
- Any claim without a source is printed as **ASSUMPTION**
- Market size is never invented

<!-- قل: النموذج ممكن يخترع، فخلّينا الكود يتحقق من كل اقتباس إنه موجود حرفياً في المصدر. -->

---

## Real results from our demo run (`outputs/`)

| Founder brief | What the system did |
|---|---|
| Crypto trading-signals channel | **STOP**: excluded category, cannot be overridden |
| "Motivational quotes from your houseplant" app | **STOP**: 1 verified pain signal, score 31/100 |
| Scope-creep toolkit for freelance web developers | 3 verified signals, score 59.9/100 → **REPEAT**; founder override logged; product built and tested; sale-to-cash test passed |

Final memo: *no real sales yet, do not invest more until real demand exists.*

<!-- أهم شريحة. قل: النظام قال لا مرتين، وفي الثالثة قال "كرر" وما جامل حتى بعد ما بنينا المنتج. -->

---

## The founder stays in control

- Nothing is **published, sent, spent or signed** without founder approval
- Each approval is **bound to the exact content** (hash): change one word → approve again
- No founder available → **default is reject**
- Overrides are allowed (except excluded categories) and always logged

<!-- قل: الموافقة مربوطة بالنص نفسه، لو تغيّر حرف لازم موافقة جديدة. ومافيه وضع "موافقة تلقائية". -->

---

## Safety: tested against trick prompts

- "Write 50 five-star reviews" → **refused before any model call**
- Fake sign-ups, countdown timers, impersonation, income promises, moving money, storing cards → refused
- Model output is scanned: promises, fake social proof and fake urgency are removed
- **50/50** guardrail checks pass (`evals/results.md`), 42 smoke tests pass

<!-- اعرض مباشرة: اكتب في Ask the team طلب التقييمات المزيفة وخلهم يشوفون الرفض. -->

---

## Sale to cash (MOCKED, no real money)

```
checkout → signed payment webhook → automatic delivery
duplicate webhook → ignored        forged webhook → rejected
founder-approved refund → access revoked → books reconcile
```

12/12 steps passed: gross − fees − refunds = payouts

<!-- قل: الدفع وهمي بالكامل حسب الشروط، بس المنطق حقيقي ومجرّب: ما يوصل المنتج مرتين، والاسترجاع يقفل الرابط. -->

---

## Why open beats closed

- **Trust:** every decision is in `decision_log.json`, with its sources, model, cost and approver
- **Cost:** open-weight models, $0 per run, no paid API
- **Control:** thresholds and prompts are plain files the founder can read and change
- **Safety by design:** the rules that matter are code, not prompts

<!-- قل: الأداة المغلقة تقول "ثق فيني"، احنا نوريك شغلنا خطوة خطوة. -->

---

## What the system will NOT do

- Promise income or success
- Write fake reviews, testimonials, sign-ups, countdowns
- Pose as the founder, a customer or another brand
- Hold, move or refund money, create accounts, store passwords or cards
- Simulate customers, interviews or demand data
- Build physical goods, financial/crypto, health or legal advice products

<!-- اقرأها بثقة. هذي من شروط المسابقة ومطبّقة في الكود. -->

---

## Realistic roadmap

| When | What |
|---|---|
| Month 1 | Resume a run from any gate with new real evidence (interviews, sign-ups) |
| Month 2 | Publish from the founder's own accounts, behind the same approval check |
| Month 3 | More evidence sources with quote checks; more product formats |
| Month 4+ | Payment-provider adapter in test mode behind the existing webhook and reconcile code |

<!-- قل: خطة واقعية شهر بشهر، ونبدأ بالأهم: نكمل التشغيل من أي بوابة بأدلة جديدة. -->

---

## How the project stays alive

- **Maintainers:** Ahmed Bawazeer, Fidaa Aldeen Wadaan, Ahmed Alaidaroos
- **Community:** prompts, thresholds and trick prompts are plain files anyone can improve
- **Funding:** MIT licence and $0 running cost; sponsorships, open-source AI grants, paid setup help for incubators; never a paywall on core features

<!-- قل: ما يحتاج فلوس عشان يعيش، لأن تكلفته صفر، وأي أحد يقدر يساهم. -->

---

## Honest limits, and the ask

- Demand testing needs real traffic; the system says **REPEAT** instead of inventing numbers
- Publishing, payments and delivery emails are MOCKED
- On a CPU-only laptop a full run takes about 20 minutes; on a free tier, minutes

**Try it:** `docker compose up` → http://localhost:8000
**Repo:** github.com/ahmedbawazeer1/human

<!-- اختم بثقة: نظام صادق يقول لا، والمؤسس صاحب القرار. اشكرهم واطلب أسئلتهم. -->
