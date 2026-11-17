"""Orchestrator: runs the six phases with a gate after each one.

    python orchestrator.py --brief briefs/example.md                  # asks the founder in the terminal
    python orchestrator.py --brief b.md --decisions founder.json      # founder's pre-written decisions
    python orchestrator.py --brief b.md --interviews notes.md --metrics metrics.json

Gate outcomes: go / repeat / pivot / stop. The founder accepts the
recommendation or overrides it; overrides are logged. A policy STOP
(excluded product category) cannot be overridden.
"""
from __future__ import annotations

import argparse
import re
import json
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import reconcile as reconcile_mod
import webhooks
from checkout import start_checkout
from agents.base import RunContext, as_list, cite
from agents.builder import BuilderAgent
from agents.interviewer import InterviewerAgent
from agents.intake import IntakeAgent
from agents.launcher import LauncherAgent
from agents.legal import LegalAgent
from agents.operator import OperatorAgent
from agents.pricing import PricingAgent
from agents.qa import test_product
from agents.researcher import ResearcherAgent
from agents.strategist import StrategistAgent
from agents.validator import ValidatorAgent
from approval import (ApprovalGate, ApprovalRequest, Approver, CLIApprover, DenyApprover, FileApprover)
from decision_log import DecisionLog, now_iso
from gates import GO, REPEAT, STOP, GateResult, demand_gate, evidence_gate, load_thresholds, \
    operate_gate, payment_gate, policy_gate, test_gate
from llm import LLMClient
from outbox import Outbox
from payments import Ledger, MockPaymentProvider

ROOT = Path(__file__).resolve().parent
CHANNELS = {"file": "the founder's own decisions file passed with --decisions; anything not listed is rejected",
            "cli": "the terminal", "web": "the web UI", "default-deny": "no founder present"}
PHASES = {1: "Discover", 2: "Validate", 3: "Build", 4: "Commercial setup", 5: "Launch", 6: "Operate and learn"}


class StopRun(Exception):
    def __init__(self, phase: int, outcome: str, reason: str):
        super().__init__(reason)
        self.phase, self.outcome, self.reason = phase, outcome, reason


class Pipeline:
    def __init__(self, brief_text: str, *, approver: Approver | None = None, llm: LLMClient | None = None,
                 out_dir: str | Path = "outputs", log_path: str | Path | None = None, tag: str = "",
                 interviews: str | None = None, metrics: dict | None = None, until_phase: int = 6,
                 run_dir: str | Path | None = None, run_id: str | None = None):
        self.run_id = run_id or datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
        self.brief_text = brief_text
        self.out_dir = Path(out_dir)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.run_dir = Path(run_dir or ROOT / "runs" / self.run_id)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.log = DecisionLog(log_path, run_id=self.run_id)
        self.ctx = RunContext(run_id=self.run_id, llm=llm or LLMClient(), log=self.log, out_dir=self.out_dir,
                              thresholds=load_thresholds(), tag=tag)
        self.approvals = ApprovalGate(approver or DenyApprover(), self.log)
        self.outbox = Outbox(self.run_dir / "outbox", self.log)
        self.interviews = interviews
        self.metrics = metrics or {}
        self.until_phase = until_phase
        self.files: list[str] = []
        self.gates: list[dict] = []
        self.status = "running"
        self.current = ""

    # ---- helpers -----------------------------------------------------------
    def emit(self, msg):
        self.current = msg
        self.ctx.emit(f"[{self.run_id}] {msg}")

    def write(self, phase: int, step: int | str, name: str, content: str, ext: str = "md") -> Path:
        suffix = f"-{self.ctx.tag}" if self.ctx.tag else ""
        stem = f"phase{phase}_gate_{name}" if step == "gate" else f"phase{phase}_step{step}_{name}"
        path = self.out_dir / f"{stem}{suffix}.{ext}"
        path.write_text(content.rstrip() + "\n", encoding="utf-8")
        self.files.append(path.name)
        return path

    def header(self, phase: int, title: str) -> str:
        return (f"# Phase {phase} ({PHASES[phase]}): {title}\n\n"
                f"Run `{self.run_id}` | generated {now_iso()} | model `{self.ctx.llm.model}`\n\n")

    def gate(self, phase: int, name: str, result: GateResult, *, overridable: bool = True) -> str:
        """Log the gate, ask the founder, write the decision file. Returns the final outcome."""
        self.log.append("gate", f"{result.gate}_gate", model=None, cost=0, outcome=result.outcome,
                        detail="; ".join(result.reasons)[:300])
        if result.outcome == GO:
            options = ["accept", "reject"]
        elif overridable:
            options = ["accept", "override_go"]
        else:
            options = ["accept"]
        req = ApprovalRequest(key=f"gate:phase{phase}:{name}", kind="gate",
                              summary=f"Phase {phase} gate ({result.gate}).\n\n{result.to_markdown()}",
                              payload={"gate": result.to_dict()}, recommendation=result.outcome, options=options)
        decision = self.approvals.request(req, agent="founder")
        if result.outcome == GO:
            final = GO if decision.approved else STOP
        elif decision.choice == "override_go" and decision.approved:
            final = "override_go"
        else:
            final = result.outcome
        body = self.header(phase, f"gate: {result.gate}") + result.to_markdown()
        body += (f"\n\n## Founder decision\n\n- Choice: **{decision.choice}** (decided by {decision.by or 'nobody: default reject'}, via {CHANNELS.get(decision.channel, decision.channel)})\n"
                 f"- Reason: {decision.reason}\n- Final outcome: **{final.upper()}**\n")
        if final == "override_go":
            body += ("\n> The founder chose to continue against the system's recommendation. The recommendation above "
                     "stands on the record; later phases run on weaker evidence.\n")
        body += self.cost_block()
        self.write(phase, "gate", name, body)
        self.gates.append({"phase": phase, "gate": result.gate, "recommendation": result.outcome, "final": final})
        if final not in (GO, "override_go"):
            raise StopRun(phase, final, result.next_step or "; ".join(result.reasons))
        return final

    def cost_block(self) -> str:
        u = self.ctx.llm.usage
        cost = sum(e.get("cost", 0) for e in self.log.entries(self.run_id))
        return (f"\n## Run cost so far\n\n- Model calls: {u.calls}, tokens: {u.total:,} "
                f"({u.prompt_tokens:,} in / {u.completion_tokens:,} out), model time: {u.seconds:.0f}s\n"
                f"- Cost: **${cost:.4f}** (local open-weight model `{self.ctx.llm.model}`)\n")

    # ---- run ---------------------------------------------------------------
    def run(self) -> dict:
        try:
            self.phase1()
            for p, fn in ((2, self.phase2), (3, self.phase3), (4, self.phase4), (5, self.phase5), (6, self.phase6)):
                if p > self.until_phase:
                    break
                fn()
            self.status = "completed"
            outcome, at = "completed", self.until_phase
        except StopRun as s:
            self.status = f"stopped:{s.outcome}"
            outcome, at = s.outcome, s.phase
            self.emit(f"Stopped at phase {s.phase} with outcome {s.outcome.upper()}: {s.reason}")
        u = self.ctx.llm.usage
        cost = round(sum(e.get("cost", 0) for e in self.log.entries(self.run_id)), 6)
        summary = {"run_id": self.run_id, "status": self.status, "outcome": outcome, "phase": at, "gates": self.gates,
                   "files": self.files, "model": self.ctx.llm.model, "model_calls": u.calls, "tokens": u.total,
                   "model_seconds": round(u.seconds), "cost_usd": cost}
        (self.run_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        self.emit(f"Done: {self.status}. {u.calls} model calls, {u.total:,} tokens, ${cost:.4f}.")
        return summary

    # ---- Phase 1: Discover -------------------------------------------------
    def phase1(self):
        t = self.ctx.thresholds
        self.emit("Phase 1 / step 0: reading the founder brief and checking the rules")
        intake = IntakeAgent(self.ctx).run(self.brief_text)
        brief, screen = intake["brief"], intake["screen"]
        self.ctx.state["brief"] = brief
        md = self.header(1, "founder brief and pre-registered thresholds")
        md += "## Founder brief (as understood)\n\n" + "\n".join(
            f"- **{k.replace('_', ' ').title()}:** {v if v else '_missing_'}" for k, v in brief.items()
            if k not in ("missing_fields", "refused_requests", "keywords")) + "\n"
        if brief.get("refused_requests"):
            md += "\n## Refused parts of the brief\n\n" + "\n".join(f"- {r}" for r in brief["refused_requests"]) + "\n"
        md += ("\n## Thresholds fixed before any evidence was collected\n\n"
               "These are written down now so that results cannot be re-interpreted later.\n\n"
               + "\n".join(f"- `{k}`: {v}" for k, v in t.items()) + "\n")
        self.write(1, 0, "intake", md)
        pol = policy_gate(screen)
        if pol.outcome == STOP:
            self.gate(1, "policy", pol, overridable=False)

        self.emit("Phase 1 / step 1: searching public sources for the problem")
        R = ResearcherAgent(self.ctx)
        pq, prodq = R.make_queries(brief)
        found = R.gather(pq, prodq)
        self.emit(f"  {len(found['pain_sources'])} posts and {len(found['product_sources'])} products found; verifying quotes")
        signals = R.extract_pain_signals(brief, found["pain_sources"])
        self.ctx.state["signals"] = signals
        self.ctx.state["products"] = found["product_sources"]
        S = StrategistAgent(self.ctx)
        opps = S.opportunities(brief, signals, found["product_sources"])
        if not opps or not opps[0].get("is_founder_idea"):
            from agents.strategist import score_opportunity
            sc = score_opportunity({}, len(signals))  # model rating unavailable: evidence points only, ratings at minimum
            opps.insert(0, {"title": brief.get("idea"), "one_liner": brief.get("idea"), "customer": brief.get("target_market"),
                            "format": "not rated (model error)", "signal_ids": [s["id"] for s in signals],
                            "score": sc["total"], "score_parts": sc["parts"], "is_founder_idea": True,
                            "rating_reasons": {"note": "the model returned no usable rating; scored on evidence only"}})
        B1 = BuilderAgent(self.ctx)
        for o in opps:  # never carry a name that an existing product already uses
            o["title"] = self.unique_product_name(B1, {"product_name": o.get("title"), "promise": o.get("one_liner")})
        md = self.header(1, "opportunities")
        md += (f"Search queries (problem): {', '.join(pq)}\n\nSearch queries (existing products): {', '.join(prodq)}\n\n"
               f"## Verified pain signals ({len(signals)})\n\nEach quote below was checked by code against the fetched text "
               "of the source. Quotes the model could not match were dropped.\n\n")
        md += "\n".join(f"- [{s['id']}]({s['url']}) ({s['origin']}, {s['date']}): \"{s['quote']}\"" for s in signals) or "_None found._"
        md += "\n\n## Existing products found\n\n" + ("\n".join(
            f"- [{p.id}]({p.url}) {p.title}: {p.short(140)}" for p in found["product_sources"][:12]) or "_None found._")
        md += "\n\n## Opportunities\n\n"
        for i, o in enumerate(opps, 1):
            md += (f"### {i}. {o.get('title')}{' (founder idea, sharpened)' if o.get('is_founder_idea') else ''}\n\n"
                   f"{o.get('one_liner')}\n\n- Customer: {o.get('customer')}\n- Format: {o.get('format')}\n"
                   f"- Evidence: {cite(self.ctx.registry, o.get('signal_ids'))}\n\n")
        self.write(1, 1, "opportunities", md)

        self.emit("Phase 1 / step 2: scoring the idea against alternatives")
        md = self.header(1, "scoring against alternatives")
        md += ("Score = evidence (40 pts: verified pain signals, capped at 8) + founder fit, feasibility within budget and "
               "time, differentiation, values fit (15 pts each, from 1-5 ratings with reasons). Ratings are model judgement "
               "(**ASSUMPTION**); the evidence points are counted by code.\n\n")
        md += "| Opportunity | Evidence | Founder fit | Feasibility | Differentiation | Values | **Total** |\n|---|---|---|---|---|---|---|\n"
        for o in opps:
            p = o.get("score_parts", {})
            md += (f"| {o.get('title')} | {p.get('evidence', 0)} | {p.get('founder_fit', 0)} | {p.get('feasibility', 0)} | "
                   f"{p.get('differentiation', 0)} | {p.get('values_fit', 0)} | **{o.get('score')}** |\n")
        md += "\n### Rating reasons\n\n" + "\n".join(
            f"- **{o.get('title')}:** " + "; ".join(f"{k}: {v}" for k, v in (o.get("rating_reasons") or {}).items())
            for o in opps if isinstance(o.get("rating_reasons"), dict))
        self.write(1, 2, "scoring", md)

        founder = opps[0]
        alts = sorted(opps[1:], key=lambda o: -o.get("score", 0))
        self.emit("Phase 1 / step 3: defining the market")
        market = S.market(brief, founder, signals, found["product_sources"])
        self.ctx.state.update({"opportunity": founder, "market": market, "opportunities": opps})
        md = self.header(1, "market definition")
        md += f"## Ideal customer\n\n{market.get('icp')}\n\n## Segments\n\n" + "\n".join(
            f"- {s}" for s in as_list(market.get("segments")))
        md += "\n\n## Existing alternatives\n\n" + ("\n".join(
            f"- {c.get('name')} ({cite(self.ctx.registry, [c.get('source_id')])}): {c.get('difference')}"
            for c in as_list(market.get("competitors")) if isinstance(c, dict)) or "_None identified from sources._")
        md += "\n\n## Market claims\n\nEvery claim cites a fetched source or is labelled ASSUMPTION.\n\n" + "\n".join(
            f"- {c.get('claim')} - {cite(self.ctx.registry, c.get('source_ids'))}"
            for c in as_list(market.get("claims")) if isinstance(c, dict))
        md += f"\n\n## Market size\n\n**ASSUMPTION / not estimated.** {market.get('size_note')}\n"
        self.write(1, 3, "market", md)

        self.emit("Phase 1 / step 4: Mom Test interview script and interview evidence")
        I = InterviewerAgent(self.ctx)
        script = I.script(founder)
        iv = I.analyse(self.interviews, founder) if self.interviews else I.empty()
        md = self.header(1, "customer interviews (Mom Test)")
        md += f"## Who to talk to\n\n{script.get('who_to_talk_to')}\n\n## Questions (about past behaviour, never pitching)\n\n"
        md += "\n".join(f"{i}. {q}" for i, q in enumerate(as_list(script.get("questions")), 1))
        md += "\n\n## Signals to listen for\n\n" + "\n".join(f"- {s}" for s in as_list(script.get("signals_to_listen_for")))
        md += "\n\n## Commitments to ask for\n\n" + "\n".join(f"- {s}" for s in as_list(script.get("commitments_to_ask_for")))
        md += "\n\n## Interview evidence\n\n"
        if iv["count"]:
            md += (f"{iv['count']} interview(s) supplied by the founder; {iv['with_problem']} described the problem from past "
                   f"behaviour. Commitments: {iv['commitments'] or 'none'}.\n\n")
            md += "\n".join(f"- #{i}: problem={r.get('has_problem')}, workaround={r.get('workaround')}, "
                            f"quote={r.get('quote')!r}" for i, r in enumerate(iv["results"], 1))
        else:
            md += ("**No interviews supplied.** The system does not simulate customers. Run the script above with 5+ real "
                   "people and re-run with `--interviews notes.md`.\n")
        self.write(1, 4, "interviews", md)

        result = evidence_gate(t, pain_signals=len(signals), score=founder.get("score", 0), interviews=iv["count"],
                               interview_pain_ratio=iv["pain_ratio"], best_alternative=alts[0] if alts else None,
                               founder_idea_score=founder.get("score", 0))
        self.gate(1, "decision", result)

    # ---- Phase 2: Validate -------------------------------------------------
    def phase2(self):
        t, st = self.ctx.thresholds, self.ctx.state
        V = ValidatorAgent(self.ctx)
        self.emit("Phase 2 / step 1: Lean Canvas")
        canvas = V.lean_canvas(st["brief"], st["opportunity"], st["market"], st["signals"])
        st["canvas"] = canvas
        md = self.header(2, "Lean Canvas")
        for box, items in canvas.items():
            md += f"## {box.replace('_', ' ').title()}\n\n" + ("\n".join(
                f"- {i.get('text')} - {cite(self.ctx.registry, i.get('source_ids'))}" for i in items) or "- _empty_") + "\n\n"
        self.write(2, 1, "lean_canvas", md)

        self.emit("Phase 2 / step 2: landing page for the demand test")
        copy = V.landing_copy(st["opportunity"], st["market"])
        page = V.render_landing(copy, self.run_id, st["opportunity"].get("title") or "Waitlist")
        self.write(2, 2, "landing_page", page, ext="html")
        (self.run_dir / "landing.html").write_text(page, encoding="utf-8")
        req = ApprovalRequest(key="publish:landing_page", kind="publish",
                              summary="Publish the waitlist landing page (MOCKED: written to the local outbox only).",
                              payload={"html": page})
        dec = self.approvals.request(req, agent="founder")
        published_mock = False
        if dec.approved:
            self.outbox.publish_page("landing_page", {"html": page}, dec)
            published_mock = True

        self.emit("Phase 2 / step 3: demand test plan and real results")
        plan = V.demand_plan(st["opportunity"], t)
        waitlist = self.local_waitlist()
        m = self.metrics
        real_published = bool(m.get("landing_page_published"))
        visitors = m.get("visitors")
        signups = m.get("signups", waitlist if real_published else None)
        md = self.header(2, "demand test")
        md += (f"## Target (set before the test)\n\n{t['p2_target_signups']} real waitlist sign-ups in {t['p2_window_days']} days.\n\n"
               "## How to reach the right people (no spam, no paid lists)\n\n" + "\n".join(
                   f"- **{c.get('channel')}**: {c.get('how')}" for c in as_list(plan.get("channels")) if isinstance(c, dict))
               + "\n\n## What to measure\n\n" + "\n".join(f"- {x}" for x in as_list(plan.get("measure"))))
        md += ("\n\n## Results\n\n"
               f"- Landing page approved by founder: {'yes' if dec.approved else 'no'} "
               f"({'MOCKED publish: written to local outbox, not on the internet' if published_mock else 'not published'})\n"
               f"- Real publication reported by founder: {'yes' if real_published else 'no'}\n"
               f"- Visitors: {visitors if visitors is not None else 'no data'}\n"
               f"- Sign-ups: {signups if signups is not None else 'no data'} (local waitlist count: {waitlist})\n"
               f"- Data source: {m.get('source', 'none supplied; the system does not simulate sign-ups')}\n")
        self.write(2, 3, "demand_test", md)
        self.gate(2, "demand", demand_gate(t, visitors=visitors, signups=signups, published=real_published))

    def local_waitlist(self) -> int:
        f = self.run_dir / "waitlist.json"
        return len(json.loads(f.read_text())) if f.exists() else 0

    # ---- Phase 3: Build ----------------------------------------------------
    def phase3(self):
        t, st = self.ctx.thresholds, self.ctx.state
        B = BuilderAgent(self.ctx)
        self.emit("Phase 3 / step 1: MVP spec")
        spec = B.spec(st["opportunity"], st.get("canvas", {}))
        spec["product_name"] = self.unique_product_name(B, spec)
        st["spec"] = spec
        md = self.header(3, "MVP spec")
        md += (f"**Product:** {spec.get('product_name')}\n\n**Promise:** {spec.get('promise')}\n\n## Sections and acceptance tests\n\n"
               + "\n".join(f"- **{s.get('title')}**: {s.get('purpose')} (must include: \"{s.get('must_include')}\")"
                           for s in spec["sections"])
               + "\n\n## Out of scope\n\n" + "\n".join(f"- {x}" for x in as_list(spec.get("out_of_scope"))))
        self.write(3, 1, "mvp_spec", md)

        sections: dict[str, str] = {}
        docs = ""
        feedback: dict[str, str] = {}
        attempt, result = 0, None
        while True:
            attempt += 1
            self.emit(f"Phase 3 / step 2: building the product (attempt {attempt})")
            for s in spec["sections"]:
                if s["title"] not in sections or s["title"] in feedback:
                    sections[s["title"]] = B.write_section(spec, s, feedback.get(s["title"], ""))
            if not docs or "__docs__" in feedback:
                docs = B.user_docs(spec)
            self.emit("Phase 3 / step 4: running product tests")
            results = test_product(spec, sections, docs)
            self.log.append("qa", f"run_product_tests:attempt_{attempt}", model=None, cost=0,
                            outcome="pass" if all(r["passed"] for r in results) else "fail",
                            detail=f"{sum(r['passed'] for r in results)}/{len(results)} passed")
            result = test_gate(results, attempt, t["p3_max_build_attempts"])
            if result.outcome != REPEAT:
                break
            feedback = {}
            for r in results:
                if not r["passed"]:
                    key = r["section"] or spec["sections"][0]["title"]
                    feedback[key] = (feedback.get(key, "") + f" {r['name']}: {r.get('detail')}.").strip()
            self.gates.append({"phase": 3, "gate": "tests", "recommendation": REPEAT, "final": REPEAT, "attempt": attempt})
        product = f"# {spec.get('product_name')}\n\n> {spec.get('promise')}\n\n" + "\n\n".join(sections.values())
        self.write(3, 2, "product", product)
        self.write(3, 3, "user_docs", f"# {spec.get('product_name')}: user guide\n\n{docs}")
        st.update({"product": product, "docs": docs})
        md = self.header(3, "QA report") + f"Attempts: {attempt}\n\n| Test | Result | Detail |\n|---|---|---|\n"
        md += "\n".join(f"| {r['name']} | {'PASS' if r['passed'] else 'FAIL'} | {r.get('detail', '')} |" for r in results)
        self.write(3, 4, "qa_report", md)
        self.gate(3, "tests", result)

    def unique_product_name(self, B: BuilderAgent, spec: dict) -> str:
        """Never ship under a name an existing product already uses (no posing as another brand)."""
        def norm(x):
            return re.sub(r"[^a-z0-9]", "", str(x or "").lower())
        taken = []
        for p in self.ctx.state.get("products", []):
            taken.append(p.title.split("/")[-1].replace("Show HN:", "").split(" – ")[0].split(" - ")[0].strip())
        taken_n = {norm(t) for t in taken if len(norm(t)) >= 6}  # skip generic short words like "scope"

        def clashes(name):
            n = norm(name)
            return not n or any(t == n or t in n for t in taken_n)
        name = spec.get("product_name") or ""
        for _ in range(2):
            if not clashes(name):
                return name
            self.log.append("builder", "product_name_clash", model=None, cost=0, outcome="renamed",
                            detail=f"'{name}' matches an existing product found in research")
            name = B.rename(spec, taken)
        fallback = "Working title: " + " ".join(str(spec.get("promise") or "toolkit").split()[:4])
        return name if not clashes(name) else fallback

    # ---- Phase 4: Commercial setup -----------------------------------------
    def phase4(self):
        st = self.ctx.state
        self.emit("Phase 4 / step 1: pricing")
        pricing = PricingAgent(self.ctx).propose(st["spec"], st["opportunity"],
                                                 [c for c in as_list(st["market"].get("competitors")) if isinstance(c, dict)],
                                                 st["brief"])
        st["pricing"] = pricing
        md = self.header(4, "pricing")
        md += (f"- **Price:** ${pricing.get('price')} {pricing.get('currency')} one-time\n- **Free preview:** {pricing.get('free_preview')}\n"
               f"- **Refund window:** {pricing.get('refund_days')} days\n\n## Rationale (**ASSUMPTION** unless a source id is cited)\n\n"
               f"{pricing.get('rationale')}\n\n## Honest price test\n\n{pricing.get('price_test')}\n\n"
               "No payment of any kind is set up in this phase.\n")
        if pricing["issues"]:
            md += "\n## Issues found by code\n\n" + "\n".join(f"- {i}" for i in pricing["issues"])
        self.write(4, 1, "pricing", md)
        self.emit("Phase 4 / step 2: draft terms, privacy and refund policies")
        drafts = LegalAgent(self.ctx).drafts(st["spec"].get("product_name") or "the product", pricing["refund_days"],
                                             ROOT / "templates")
        st["policies"] = drafts
        self.write(4, 2, "policies", self.header(4, "draft policies") + "\n\n---\n\n".join(drafts.values()))
        ok = pricing.get("price") and not pricing["issues"]
        result = GateResult("commercial", GO if ok else REPEAT, reasons=[
            "Price and draft policies are ready for founder sign-off." if ok else f"Pricing issues: {pricing['issues']}"],
            next_step="Founder signs off price and policies." if ok else "Repeat pricing.")
        self.gate(4, "signoff", result)

    # ---- Phase 5: Launch ---------------------------------------------------
    def phase5(self):
        t, st = self.ctx.thresholds, self.ctx.state
        L = LauncherAgent(self.ctx)
        self.emit("Phase 5 / step 1: store page")
        copy = L.store_copy(st["spec"], st["pricing"])
        store = L.render_store(copy, st["spec"], st["pricing"], st["pricing"]["refund_days"])
        self.write(5, 1, "store_page", store, ext="html")
        self.emit("Phase 5 / step 2: launch posts (drafts, each needs founder approval)")
        posts = L.posts(st["spec"], st["opportunity"])
        md = self.header(5, "launch posts") + ("Drafts in the founder's own voice. Each one is published only after the "
                                                "founder approves it, and publishing is MOCKED (local outbox).\n\n")
        for i, p in enumerate(posts, 1):
            payload = {"channel": p.get("channel"), "text": p.get("text")}
            dec = self.approvals.request(ApprovalRequest(key=f"publish:post_{i}", kind="publish",
                                                         summary=f"Publish launch post #{i} on {p.get('channel')}:\n\n{p.get('text')}",
                                                         payload=payload), agent="founder")
            state = "rejected, not published"
            if dec.approved:
                self.outbox.publish_post(f"post_{i}", payload, dec)
                state = "approved; MOCKED publish to local outbox"
            md += f"## {i}. {p.get('channel')} ({state})\n\n{p.get('text')}\n\n"
        self.write(5, 2, "launch_posts", md)

        self.emit("Phase 5 / step 3: sale-to-cash test (MOCKED payments and delivery)")
        results, log_md = self.sale_to_cash_test(st["spec"].get("product_name") or "product", st["pricing"].get("price") or 10)
        suffix = f"-{self.ctx.tag}" if self.ctx.tag else ""
        (self.out_dir / f"payment_test_log{suffix}.md").write_text(log_md, encoding="utf-8")
        self.files.append(f"payment_test_log{suffix}.md")
        self.write(5, 3, "delivery_test", self.header(5, "automatic delivery test") +
                   "See `payment_test_log.md` for every event.\n\n" + "\n".join(
                       f"- {k}: {'PASS' if v else 'FAIL'}" for k, v in results.items()))
        self.gate(5, "launch", payment_gate(t, results))
        dec = self.approvals.request(ApprovalRequest(
            key="publish:open_store", kind="publish",
            summary="Open the store with automatic delivery after payment (MOCKED: no real checkout exists).",
            payload={"store_html": store, "auto_delivery": True}), agent="founder")
        if dec.approved:
            self.outbox.open_store({"store_html": store, "auto_delivery": True}, dec)

    def sale_to_cash_test(self, product: str, price: float) -> tuple[dict, str]:
        ledger = Ledger(self.run_dir / "ledger.sqlite")
        prov = MockPaymentProvider(ledger)
        lines = ["# Payment and delivery test log", "",
                 f"Run `{self.run_id}` | {now_iso()} | provider: **MOCKED** (no real or sandbox payment service; test buyers only)", "",
                 "| # | Step | Result |", "|---|---|---|"]
        mails = []

        def mailer(to, text):
            mails.append((to, text))

        def step(name, res):
            lines.append(f"| {len(lines) - 5} | {name} | {res} |")
            self.log.append("payments", f"mock:{name}", model=None, cost=0, outcome=str(res))
            return res

        a = start_checkout(prov, product, price, "test-buyer-a@example.invalid")
        step("create checkout A (MOCKED)", a)
        body, sig = prov.complete_test_payment(a)
        r1 = step("payment webhook A", webhooks.handle(prov, ledger, body, sig, mailer))
        r2 = step("same webhook A delivered again", webhooks.handle(prov, ledger, body, sig, mailer))
        body2, sig2 = prov.complete_test_payment(a)
        r2b = step("second payment event for order A", webhooks.handle(prov, ledger, body2, sig2, mailer))
        r3 = step("forged webhook (bad signature)", webhooks.handle(prov, ledger, body, "bad", mailer))
        b = start_checkout(prov, product, price, "test-buyer-b@example.invalid")
        step("create checkout B (MOCKED)", b)
        bb, bs = prov.complete_test_payment(b)
        step("payment webhook B", webhooks.handle(prov, ledger, bb, bs, mailer))
        token_b = ledger.q("SELECT token FROM grants WHERE order_id=?", b)[0]["token"]
        dec = self.approvals.request(ApprovalRequest(key="refund:test_order", kind="spend",
                                                     summary=f"Approve refund of TEST order {b} (${price}, MOCKED provider).",
                                                     payload={"refund_order": b}), agent="founder")
        refund_ok = False
        if dec.approved:
            rb, rs = prov.refund(b, dec)
            step("refund B (founder approved, MOCKED provider)", webhooks.handle(prov, ledger, rb, rs, mailer))
            refund_ok = True
        else:
            step("refund B", "not approved by founder; nothing refunded")
        import delivery as delivery_mod
        token_a = ledger.q("SELECT token FROM grants WHERE order_id=?", a)[0]["token"]
        can_a = delivery_mod.can_download(ledger, token_a)
        can_b = delivery_mod.can_download(ledger, token_b)
        step("buyer A can download", can_a)
        step("buyer B can download after refund", can_b)
        pb, ps = prov.payout()
        step("payout (MOCKED)", webhooks.handle(prov, ledger, pb, ps, mailer))
        rec = reconcile_mod.reconcile(ledger)
        step("reconciliation", "balanced" if rec["balanced"] else f"issues: {rec['issues']}")
        deliveries = ledger.q("SELECT COUNT(*) AS n FROM deliveries WHERE order_id=?", a)[0]["n"]
        results = {
            "paid_delivers": r1 == "delivered" and can_a,
            "duplicate_webhook_ignored": r2 == "ignored:duplicate_event" and r2b == "ignored:order_already_paid" and deliveries == 1
            and r3 == "rejected:bad_signature",
            "refund_revokes": refund_ok and not can_b,
            "reconciliation_balanced": rec["balanced"],
        }
        results["reconciliation_balances"] = results.pop("reconciliation_balanced")
        lines += ["", "## Reconciliation", "", "| Gross | Fees (MOCKED schedule, ASSUMPTION) | Refunds | Payouts | Expected payout | Balanced |",
                  "|---|---|---|---|---|---|",
                  f"| {rec['gross']} | {rec['fees']} | {rec['refunds']} | {rec['payouts']} | {rec['expected_payout']} | {rec['balanced']} |",
                  "", "## Delivery emails (MOCKED, not sent)", ""] + [f"- to {to}: {text}" for to, text in mails]
        lines += ["", "## Checks", ""] + [f"- {k}: {'PASS' if v else 'FAIL'}" for k, v in results.items()]
        return results, "\n".join(lines) + "\n"

    # ---- Phase 6: Operate and learn ----------------------------------------
    def phase6(self):
        t, st = self.ctx.thresholds, self.ctx.state
        O = OperatorAgent(self.ctx)
        self.emit("Phase 6 / step 1: support material")
        sup = O.support(st["spec"], st["pricing"]["refund_days"])
        md = self.header(6, "support") + "Replies are drafts; the founder sends them.\n\n## FAQ\n\n"
        md += "\n".join(f"**{f.get('q')}**\n\n{f.get('a')}\n" for f in as_list(sup.get("faq")) if isinstance(f, dict))
        md += "\n## Reply templates\n\n" + "\n".join(f"### {r.get('name')}\n\n{r.get('text')}\n"
                                                    for r in as_list(sup.get("reply_templates")) if isinstance(r, dict))
        self.write(6, 1, "support", md)
        self.emit("Phase 6 / step 2: metrics")
        m = self.metrics
        metrics = {"real_paying_customers": m.get("paying_customers", 0), "real_waitlist_signups": m.get("signups"),
                   "real_visitors": m.get("visitors"), "real_refunds": m.get("refunds", 0),
                   "mock_test_orders": "2 (MOCKED test buyers, excluded from decisions)",
                   "gates_so_far": self.gates}
        md = self.header(6, "metrics") + "| Metric | Value |\n|---|---|\n" + "\n".join(
            f"| {k} | {v if v is not None else 'no data'} |" for k, v in metrics.items() if k != "gates_so_far")
        md += "\n\nMOCKED test orders are never counted as customers.\n"
        self.write(6, 2, "metrics", md)
        result = operate_gate(t, paying_customers=int(m.get("paying_customers") or 0), signups=m.get("signups"),
                              refunds=int(m.get("refunds") or 0))
        self.emit("Phase 6 / step 3: persevere-or-pivot memo")
        history = "\n".join(f"- phase {g['phase']} {g['gate']}: recommended {g['recommendation']}, final {g['final']}"
                            for g in self.gates)
        memo = O.memo({k: v for k, v in metrics.items() if k != "gates_so_far"}, result.to_markdown(), history)
        self.write(6, 3, "persevere_pivot_memo", self.header(6, "persevere-or-pivot memo") + memo)
        self.gate(6, "next", result)


def load_text(path: str | None) -> str | None:
    return Path(path).read_text(encoding="utf-8") if path else None


def main(argv=None):
    ap = argparse.ArgumentParser(description="Open Venture Builder: six phases, gates, founder in control.")
    ap.add_argument("--brief", required=True, help="founder brief (markdown or text file)")
    ap.add_argument("--decisions", help="founder's pre-written decisions (JSON). Without it you are asked in the terminal.")
    ap.add_argument("--interviews", help="real interview notes (markdown, '## Interview' per person)")
    ap.add_argument("--metrics", help="real demand/sales metrics (JSON)")
    ap.add_argument("--out", default="outputs")
    ap.add_argument("--log", default=None, help="decision log path (default decision_log.json)")
    ap.add_argument("--tag", default="", help="suffix for output file names")
    ap.add_argument("--until-phase", type=int, default=6)
    a = ap.parse_args(argv)
    approver = FileApprover(a.decisions) if a.decisions else CLIApprover()
    if not a.decisions and not sys.stdin.isatty():
        approver = DenyApprover()
    p = Pipeline(load_text(a.brief), approver=approver, out_dir=a.out, log_path=a.log, tag=a.tag,
                 interviews=load_text(a.interviews), metrics=json.loads(load_text(a.metrics)) if a.metrics else None,
                 until_phase=a.until_phase)
    if not p.ctx.llm.ping():
        print(f"Model server not reachable at {p.ctx.llm.base_url}. Start Ollama (`ollama serve` + `ollama pull "
              f"{p.ctx.llm.model}`) or set LLM_BASE_URL.", file=sys.stderr)
        return 2
    print(json.dumps(p.run(), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
