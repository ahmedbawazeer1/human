"""Test doubles: a scripted model and offline research results. Used only by tests."""
from __future__ import annotations

import json
import re

from llm import LLMClient
from tools.research import Source

PAIN_TEXT = ("I keep losing hours every week because clients ask for extra pages after we agreed the scope "
             "and I never know how to say no without losing the client")


class FakeLLM(LLMClient):
    def __init__(self, pain: bool = True):
        super().__init__(base_url="http://fake", model="fake-model")
        self.pain = pain

    def ping(self):
        return True

    def chat(self, system, user, max_tokens=900, json_mode=False):
        self.usage.calls += 1
        self.usage.prompt_tokens += len(user) // 4
        out = self._answer(user)
        self.usage.completion_tokens += len(out) // 4
        return out, 0.0

    def _answer(self, u: str) -> str:
        j = json.dumps
        if "Extract the founder brief" in u:
            return j({"idea": "x", "skills": "y", "budget": "$1", "time": "1h", "target_market": "z", "values": "v",
                      "keywords": ["scope creep"]})
        if "search queries" in u:
            return j({"problem_queries": ["scope creep clients"], "product_queries": ["scope template"]})
        if "POSTS:" in u:
            ids = re.findall(r"^\[(S\d+)\]", u, flags=re.M)
            return j({"signals": [{"id": i, "relevant": self.pain, "is_pain": self.pain, "quote": PAIN_TEXT[:80]} for i in ids]})
        if "Sharpen the FOUNDER'S OWN idea" in u:
            r = 4 if self.pain else 1
            return j({"opportunities": [
                {"title": "Scope Kit", "one_liner": "Stop scope creep", "customer": "freelance devs", "format": "toolkit",
                 "signal_ids": [], "ratings": {"founder_fit": r, "feasibility": r, "differentiation": r, "values_fit": r},
                 "reasons": {"founder_fit": "ok"}}]})
        if "Propose TWO different alternative" in u:
            return j({"opportunities": [
                {"title": "Alt", "one_liner": "alt", "customer": "c", "format": "guide", "signal_ids": ["S1"],
                 "ratings": {"founder_fit": 1, "feasibility": 1, "differentiation": 1, "values_fit": 1}}]})
        if "Define the market" in u:
            return j({"icp": "Solo devs", "segments": ["solo"], "competitors": [{"name": "P1", "source_id": "S1", "difference": "d"}],
                      "claims": [{"claim": "Devs complain about scope creep", "source_ids": ["S1"]},
                                 {"claim": "Market is big", "source_ids": []}], "size_note": "count freelancers"})
        if "Mom Test customer interview plan" in u:
            return j({"who_to_talk_to": "devs", "questions": ["Tell me about the last project that grew."],
                      "signals_to_listen_for": ["lost hours"], "commitments_to_ask_for": ["follow-up call"]})
        if "Apply the Mom Test" in u:
            return j({"has_problem": True, "workaround": "email", "spent_time_or_money": True, "commitment": None,
                      "compliments_only": False, "quote": None})
        if "Fill a Lean Canvas" in u:
            return j({k: [{"text": "t", "source_ids": ["S1"]}] for k in ["problem", "customer_segments", "unique_value_proposition",
                      "solution", "channels", "revenue_streams", "cost_structure", "key_metrics", "unfair_advantage"]})
        if "landing page copy" in u:
            return j({"headline": "Stop scope creep", "subheadline": "s", "benefits": ["a"], "how_it_works": ["b"],
                      "cta": "Join the waitlist", "faq": [{"q": "q", "a": "a"}]})
        if "Suggest 4 honest" in u:
            return j({"channels": [{"channel": "own network", "how": "ask"}], "measure": ["signups"]})
        if "smallest useful version" in u:
            return j({"product_name": "Scope Kit", "promise": "A clear scoping process.", "out_of_scope": ["apps"],
                      "sections": [{"title": "Scoping questionnaire", "purpose": "p", "must_include": "questionnaire"},
                                   {"title": "Change requests", "purpose": "p", "must_include": "change request"}]})
        if "Write the section" in u:
            phrase = re.search(r'MUST contain the phrase "([^"]+)"', u).group(1)
            return f"## Section\n\nUse this {phrase}. " + ("Write down each step clearly for your client. " * 25)
        if "user documentation" in u:
            return "## Quick start\n\nOpen the files.\n\n## What's inside\n\nTemplates.\n\n## How to get help\n\nReply.\n\n## Refunds\n\n14 days."
        if "launch pricing" in u:
            return j({"price": 19, "currency": "USD", "free_preview": "questionnaire", "rationale": "r", "price_test": "t",
                      "refund_days": 14})
        if "store page copy" in u:
            return j({"headline": "h", "description": "d", "whats_inside": ["a"], "who_its_for": "f", "who_its_not_for": "n"})
        if "Draft 3 launch posts" in u:
            return j({"posts": [{"channel": "LinkedIn", "text": "I made a scoping kit."},
                                {"channel": "Community", "text": "I made this."}, {"channel": "Email", "text": "Hi"}]})
        if "support material" in u:
            return j({"faq": [{"q": "q", "a": "a"}], "reply_templates": [{"name": "n", "text": "t"}]})
        if "persevere-or-pivot memo" in u:
            return "## Situation\n\nNo real data.\n\n## Recommendation\n\nRepeat."
        if "Founder request" in u:
            return "Here is a draft."
        return "{}"


def fake_sources(pain: bool):
    text = PAIN_TEXT if pain else "My plant is green."
    posts = [Source(id="", url=f"https://news.ycombinator.com/item?id={1000 + i}", title=f"post {i}", text=text,
                    origin="hackernews") for i in range(8)]
    prods = [Source(id="", url="https://github.com/example/scope", title="example/scope", text="scope tool", origin="github")]
    return posts, prods


def patch_research(monkeypatch, pain: bool = True):
    import tools.research as r
    posts, prods = fake_sources(pain)
    monkeypatch.setattr(r, "search_hn", lambda q, n=8: list(posts))
    monkeypatch.setattr(r, "search_stackexchange", lambda q, sites=None, n=5: [])
    monkeypatch.setattr(r, "search_show_hn", lambda q, n=6: [])
    monkeypatch.setattr(r, "search_github", lambda q, n=5: list(prods))
