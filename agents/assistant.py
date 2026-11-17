"""Assistant: free-form founder requests ("Ask the team").

Requests are screened by guardrails BEFORE any model call; rule-breaking
requests are refused and logged. Allowed requests get a draft that is scanned
again before it is shown.
"""
from __future__ import annotations

import guardrails
from agents.base import BaseAgent


class AssistantAgent(BaseAgent):
    role = "assistant"

    def handle(self, request: str) -> dict:
        screen = guardrails.screen_request(request)
        if not screen.allowed:
            self.ctx.log.append("guardrail", f"refused_request:{screen.rule}", model=None, cost=0,
                                outcome="refused", detail=request[:200])
            return {"refused": True, "rule": screen.rule, "text": guardrails.refusal_message(screen)}
        text = self.ask_text(f"Founder request:\n{request[:2000]}\n\nWrite a helpful draft.", action="founder_request",
                             max_tokens=700)
        return {"refused": False, "rule": None, "text": text + "\n\n_Draft only. Nothing has been sent or published._"}
