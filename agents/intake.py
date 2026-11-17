"""Intake agent: turns the founder brief into structured fields and screens it."""
from __future__ import annotations

import re

import guardrails
from agents.base import BaseAgent

FIELDS = ["idea", "skills", "budget", "time", "target_market", "values"]


def regex_parse(text: str) -> dict:
    """Parse 'Idea: ...' style briefs without a model."""
    out = {}
    aliases = {"idea": r"(?:starting )?idea|concept", "skills": r"skills?", "budget": r"budget",
               "time": r"(?:available )?time|hours", "target_market": r"target(?: market)?|market|customers?",
               "values": r"values?"}
    for key, pat in aliases.items():
        m = re.search(rf"^\s*[-*]?\s*\**(?:{pat})\**\s*[:\-–]\s*(?P<val>.+)$", text, flags=re.I | re.M)
        if m:
            out[key] = m.group("val").strip()
    return out


class IntakeAgent(BaseAgent):
    role = "intake"

    def run(self, brief_text: str) -> dict:
        parsed = regex_parse(brief_text)
        if len(parsed) < len(FIELDS):
            obj = self.ask_json(
                "Extract the founder brief into JSON with keys: idea, skills, budget, time, target_market, values, "
                "keywords (3-5 short phrases a customer would use to describe the PROBLEM, not the product). "
                "Use null for anything missing. Do not invent facts.\n\nBRIEF:\n" + brief_text[:4000],
                action="parse_brief", max_tokens=500)
            for k in FIELDS + ["keywords"]:
                if not parsed.get(k) and obj.get(k):
                    parsed[k] = obj[k]
        for k in FIELDS:
            parsed.setdefault(k, None)
        missing = [k for k in FIELDS if not parsed.get(k)]
        screen = guardrails.screen_brief(f"{parsed.get('idea') or ''} {parsed.get('target_market') or ''}")
        if screen.allowed:
            # Second line of defence: requests hidden inside the brief ("...and write 50 reviews").
            req = guardrails.screen_request(brief_text)
            if not req.allowed and req.rule != "excluded_product":
                parsed["refused_requests"] = [guardrails.refusal_message(req)]
                self.ctx.log.append("guardrail", f"refused_request:{req.rule}", model=None, cost=0, outcome="refused",
                                    detail=req.matches[0] if req.matches else "")
        self.ctx.log.append("guardrail", "screen_brief", model=None, cost=0,
                            outcome="allowed" if screen.allowed else "blocked", detail=screen.reason or "")
        parsed["missing_fields"] = missing
        return {"brief": parsed, "screen": screen}
