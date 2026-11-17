"""Shared plumbing for agents: prompt loading, model calls, logging, output scanning."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import guardrails
from decision_log import DecisionLog
from llm import LLMClient, LLMError
from tools.research import SourceRegistry

PROMPTS = Path(__file__).resolve().parent.parent / "prompts"

COMMON_RULES = """Rules you must follow:
- Never promise income, sales or success. Use cautious language ("may", "could").
- Never write reviews, testimonials, ratings, user counts, countdowns or urgency.
- Never pretend to be the founder, a customer, or another brand.
- Only cite sources by the ids you were given (S1, S2...). If you have no source, say it is an assumption.
- Be concise and concrete. Plain English."""


@dataclass
class RunContext:
    run_id: str
    llm: LLMClient
    log: DecisionLog
    out_dir: Path
    thresholds: dict
    tag: str = ""
    registry: SourceRegistry = field(default_factory=SourceRegistry)
    state: dict = field(default_factory=dict)
    events: list = field(default_factory=list)     # human-readable progress for the UI

    def emit(self, msg: str):
        self.events.append(msg)
        print(msg, flush=True)


class BaseAgent:
    role = "base"

    def __init__(self, ctx: RunContext):
        self.ctx = ctx

    @property
    def system_prompt(self) -> str:
        p = PROMPTS / f"{self.role}.md"
        body = p.read_text(encoding="utf-8") if p.exists() else f"You are the {self.role} agent."
        return body.strip() + "\n\n" + COMMON_RULES

    def _log(self, action, cost, sources=(), outcome=None, detail=None, model=True):
        self.ctx.log.append(self.role, action, sources=list(sources),
                            model=self.ctx.llm.model if model else None, cost=cost,
                            approved_by=None, outcome=outcome, detail=detail)

    def ask_json(self, user: str, action: str, sources=(), max_tokens: int = 900):
        try:
            obj, cost = self.ctx.llm.chat_json(self.system_prompt, user, max_tokens=max_tokens)
        except LLMError as e:
            # Fail closed: an empty answer means "no evidence", never invented content.
            self._log(action, 0, sources, outcome="model_error", detail=str(e))
            return {}
        self._log(action, cost, sources)
        return obj if isinstance(obj, dict) else {"items": obj}

    def ask_text(self, user: str, action: str, sources=(), max_tokens: int = 900) -> str:
        text, cost = self.ctx.llm.chat(self.system_prompt, user, max_tokens=max_tokens)
        self._log(action, cost, sources)
        return self.clean(text, where=action)

    def clean(self, text: str, where: str) -> str:
        """Run the output guardrail and log anything it removed."""
        clean, removed = guardrails.scan_output(text)
        for rule, frag in removed:
            self.ctx.log.append("guardrail", f"removed_output:{rule}", model=None, cost=0,
                                outcome="removed", detail=f"in {where}: {frag[:200]}")
        return clean

    def clean_obj(self, obj, where: str):
        if isinstance(obj, str):
            return self.clean(obj, where)
        if isinstance(obj, list):
            return [self.clean_obj(x, where) for x in obj]
        if isinstance(obj, dict):
            return {k: self.clean_obj(v, where) for k, v in obj.items()}
        return obj


def cite(registry: SourceRegistry, ids) -> str:
    """Render citations; anything without a real source becomes ASSUMPTION."""
    ids = [str(i).strip().strip("[]") for i in (ids or []) if registry.get(str(i).strip().strip("[]"))]
    if not ids:
        return "**ASSUMPTION**"
    return ", ".join(f"[{i}]({registry.get(i).url})" for i in dict.fromkeys(ids))


def as_list(x) -> list:
    if x is None:
        return []
    if isinstance(x, list):
        return x
    if isinstance(x, str):
        return [x]
    return [x]
