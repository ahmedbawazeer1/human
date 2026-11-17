"""Gates between steps. Thresholds are fixed BEFORE evidence is collected and
written into the intake output, so results cannot be spun afterwards.

Every gate returns one of: go / repeat / pivot / stop, with the checks behind it.
The founder then accepts the recommendation or overrides it (the override is
logged). The system recommends STOP when evidence is weak; it never rounds up.
"""
from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

GO, REPEAT, PIVOT, STOP = "go", "repeat", "pivot", "stop"

DEFAULT_THRESHOLDS = {
    # Phase 1: Discover (desk research + Mom Test interviews)
    "p1_min_pain_signals": 5,          # verified, sourced posts where people describe the problem
    "p1_stop_below_pain_signals": 2,   # fewer than this -> STOP
    "p1_min_opportunity_score": 60,    # 0-100
    "p1_stop_below_score": 45,
    "p1_min_interviews": 5,            # real customer conversations supplied by the founder
    "p1_min_interview_pain_ratio": 0.6,  # share of interviewees describing the problem from past behaviour
    # Phase 2: Validate (landing page demand test)
    "p2_target_signups": 100,
    "p2_window_days": 14,
    "p2_repeat_ratio": 0.5,            # >= 50% of target -> repeat (iterate page), below 25% -> stop
    "p2_stop_ratio": 0.25,
    "p2_min_visitors_for_signal": 200,
    # Phase 3: Build
    "p3_max_build_attempts": 3,
    # Phase 5: Launch
    "p5_required_payment_tests": ["paid_delivers", "duplicate_webhook_ignored", "refund_revokes", "reconciliation_balances"],
    # Phase 6: Operate
    "p6_min_paying_customers_to_persevere": 10,
}


def load_thresholds() -> dict:
    t = dict(DEFAULT_THRESHOLDS)
    path = Path(os.getenv("GATES_CONFIG", "config/gates.json"))
    if path.exists():
        t.update(json.loads(path.read_text(encoding="utf-8")))
    return t


@dataclass
class Check:
    name: str
    value: object
    threshold: object
    passed: bool
    note: str = ""


@dataclass
class GateResult:
    gate: str
    outcome: str
    checks: list[Check] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    next_step: str = ""

    def to_dict(self):
        return asdict(self)

    def to_markdown(self) -> str:
        lines = [f"**Recommendation: {self.outcome.upper()}**", "", "| Check | Value | Threshold (set in advance) | Result |",
                 "|---|---|---|---|"]
        for c in self.checks:
            lines.append(f"| {c.name} | {c.value} | {c.threshold} | {'PASS' if c.passed else 'FAIL'}{(' - ' + c.note) if c.note else ''} |")
        lines += ["", "Why:"] + [f"- {r}" for r in self.reasons]
        if self.next_step:
            lines += ["", f"Next step: {self.next_step}"]
        return "\n".join(lines)


def policy_gate(screen) -> GateResult:
    if screen.allowed:
        return GateResult("policy", GO, [Check("excluded category", "none", "none allowed", True)],
                          ["The idea is a digital product outside the excluded categories."])
    return GateResult("policy", STOP, [Check("excluded category", screen.rule, "none allowed", False)],
                      [screen.reason, "Physical goods, financial/crypto, and health or legal advice products are out of scope."],
                      "Choose a different digital product idea.")


def evidence_gate(t: dict, *, pain_signals: int, score: float, interviews: int,
                  interview_pain_ratio: float | None, best_alternative: dict | None,
                  founder_idea_score: float) -> GateResult:
    checks = [
        Check("verified pain signals (sourced)", pain_signals, f">= {t['p1_min_pain_signals']}", pain_signals >= t["p1_min_pain_signals"]),
        Check("opportunity score (0-100)", round(score, 1), f">= {t['p1_min_opportunity_score']}", score >= t["p1_min_opportunity_score"]),
        Check("customer interviews supplied", interviews, f">= {t['p1_min_interviews']}", interviews >= t["p1_min_interviews"],
              "" if interviews else "none supplied yet"),
    ]
    if interviews:
        checks.append(Check("interviewees with the problem (past behaviour)", f"{interview_pain_ratio:.0%}",
                            f">= {t['p1_min_interview_pain_ratio']:.0%}", (interview_pain_ratio or 0) >= t["p1_min_interview_pain_ratio"]))
    reasons = []
    # STOP rules: weak evidence is not rounded up.
    if pain_signals < t["p1_stop_below_pain_signals"] or score < t["p1_stop_below_score"]:
        reasons.append(f"Only {pain_signals} verified public pain signal(s) and a score of {score:.0f}/100. "
                       "That is too weak to justify building anything.")
        if interviews and (interview_pain_ratio or 0) < t["p1_min_interview_pain_ratio"]:
            reasons.append("Interviews did not show the problem either.")
        return GateResult("evidence", STOP, checks, reasons,
                          "Do not launch this idea. Start again from a problem people already spend time or money on.")
    if interviews and (interview_pain_ratio or 0) < t["p1_min_interview_pain_ratio"] / 2:
        reasons.append("Real interviews contradict the desk research: most interviewees do not have this problem.")
        return GateResult("evidence", STOP, checks, reasons, "Do not launch. Re-interview a different segment or drop the idea.")
    if best_alternative and best_alternative.get("score", 0) >= founder_idea_score + 10:
        reasons.append(f"An alternative scores clearly higher ({best_alternative['score']:.0f} vs {founder_idea_score:.0f}): "
                       f"\"{best_alternative.get('title')}\".")
        return GateResult("evidence", PIVOT, checks, reasons, "Pivot to the higher-scoring opportunity and re-run Discover.")
    if pain_signals < t["p1_min_pain_signals"] or score < t["p1_min_opportunity_score"]:
        reasons.append("Some evidence exists but it is below the thresholds set in advance.")
        return GateResult("evidence", REPEAT, checks, reasons,
                          "Repeat Discover: run the Mom Test interviews and narrow the customer segment.")
    reasons.append(f"{pain_signals} verified sourced pain signals and a score of {score:.0f}/100 pass the desk-research thresholds.")
    if interviews < t["p1_min_interviews"]:
        reasons.append(f"Interview evidence is missing ({interviews}/{t['p1_min_interviews']}). Desk research alone is weaker evidence; "
                       "the founder should run the Mom Test script before spending real money.")
        return GateResult("evidence", GO, checks, reasons,
                          "GO to Validate (cheap test only). Run the interviews in parallel.")
    reasons.append("Interviews confirm the problem.")
    return GateResult("evidence", GO, checks, reasons, "GO to Validate.")


def demand_gate(t: dict, *, visitors: int | None, signups: int | None, published: bool) -> GateResult:
    target = t["p2_target_signups"]
    if not published or visitors is None or signups is None:
        return GateResult("demand", REPEAT, [
            Check("landing page published", published, True, published),
            Check("waitlist sign-ups (real)", signups if signups is not None else "no data", f">= {target} in {t['p2_window_days']} days", False),
        ], ["There is no real demand data yet. The system will not guess or simulate sign-ups."],
            f"Publish the landing page (founder approval), drive real traffic, and re-run this gate after {t['p2_window_days']} days.")
    ratio = signups / target if target else 0
    conv = signups / visitors if visitors else 0
    checks = [
        Check("waitlist sign-ups (real)", signups, f">= {target} in {t['p2_window_days']} days", signups >= target),
        Check("visitors", visitors, f">= {t['p2_min_visitors_for_signal']} for a readable signal", visitors >= t["p2_min_visitors_for_signal"]),
        Check("visitor -> sign-up conversion", f"{conv:.1%}", "reported, not gated", True),
    ]
    if signups >= target:
        return GateResult("demand", GO, checks, [f"{signups} real sign-ups met the target of {target}."], "GO to Build.")
    if visitors < t["p2_min_visitors_for_signal"]:
        return GateResult("demand", REPEAT, checks, [f"Only {visitors} visitors: not enough traffic to judge demand."],
                          "Repeat: get more of the right visitors before deciding.")
    if ratio >= t["p2_repeat_ratio"]:
        return GateResult("demand", REPEAT, checks, [f"{signups}/{target} sign-ups ({ratio:.0%}). Close, but below target."],
                          "Repeat with a sharper offer or segment.")
    if ratio >= t["p2_stop_ratio"]:
        return GateResult("demand", PIVOT, checks, [f"{signups}/{target} sign-ups ({ratio:.0%}). Demand is weak."],
                          "Pivot the segment or the offer, then re-test.")
    return GateResult("demand", STOP, checks, [f"{signups}/{target} sign-ups ({ratio:.0%}). The target set in advance was missed by a wide margin."],
                      "Recommend STOP: do not build this. Spinning this result would mislead the founder.")


def test_gate(results: list[dict], attempt: int, max_attempts: int) -> GateResult:
    checks = [Check(r["name"], "pass" if r["passed"] else r.get("detail", "fail"), "pass", r["passed"]) for r in results]
    failed = [r for r in results if not r["passed"]]
    if not failed:
        return GateResult("tests", GO, checks, [f"All {len(results)} product tests passed (attempt {attempt})."], "GO to Commercial setup.")
    if attempt < max_attempts:
        return GateResult("tests", REPEAT, checks, [f"{len(failed)} test(s) failed; rebuilding the failing parts."], "Repeat Build.")
    return GateResult("tests", STOP, checks, [f"{len(failed)} test(s) still fail after {attempt} attempts."],
                      "Stop: the MVP does not meet its own acceptance tests. Do not sell it.")


def payment_gate(t: dict, results: dict) -> GateResult:
    checks = [Check(name, "pass" if results.get(name) else "fail", "pass", bool(results.get(name)))
              for name in t["p5_required_payment_tests"]]
    if all(c.passed for c in checks):
        return GateResult("launch", GO, checks, ["Sale-to-cash test flow (MOCKED provider) passed every check."],
                          "Store can open once the founder approves.")
    return GateResult("launch", STOP, checks, ["Sale-to-cash tests failed; buyers could be charged without delivery."],
                      "Fix delivery/refund before opening the store.")


def operate_gate(t: dict, *, paying_customers: int, signups: int | None, refunds: int) -> GateResult:
    need = t["p6_min_paying_customers_to_persevere"]
    checks = [Check("real paying customers", paying_customers, f">= {need}", paying_customers >= need),
              Check("real waitlist sign-ups", signups if signups is not None else "no data", "reported", True),
              Check("refunds", refunds, "reported", True)]
    if paying_customers >= need and refunds <= paying_customers * 0.2:
        return GateResult("operate", GO, checks, ["Enough real paying customers with low refunds."], "Persevere.")
    if paying_customers == 0:
        return GateResult("operate", REPEAT, checks,
                          ["No real sales yet (the store and payments are MOCKED). There is nothing to persevere on."],
                          "Do not invest more until real demand evidence exists: publish, measure, then re-run this gate.")
    return GateResult("operate", PIVOT, checks, [f"Only {paying_customers} paying customers."], "Pivot the offer or segment.")
