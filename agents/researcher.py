"""Researcher agent (Phase 1, step 1): finds real public evidence of the problem.

Method:
1. The model writes short search queries in the customer's words.
2. Tools fetch real posts (Hacker News, Stack Exchange) and existing products
   (Show HN launches, GitHub projects).
3. The model reads each post and, if it shows someone experiencing the problem,
   copies a short exact quote.
4. Code checks that the quote really appears in the fetched text. Quotes that
   don't match are dropped (no hallucinated evidence).
"""
from __future__ import annotations

import os

from agents.base import BaseAgent, as_list
from tools import research


class ResearcherAgent(BaseAgent):
    role = "researcher"

    def make_queries(self, brief: dict) -> list[str]:
        obj = self.ask_json(
            f"Founder idea: {brief.get('idea')}\nTarget market: {brief.get('target_market')}\n"
            f"Hint keywords: {brief.get('keywords')}\n\n"
            "Write 4 short search queries (2-4 words each) that people who HAVE this problem would type "
            "when complaining or asking for help, plus 2 queries naming the kind of product that solves it. "
            'JSON: {"problem_queries": [...], "product_queries": [...]}',
            action="plan_search_queries", max_tokens=300)
        pq = [q for q in as_list(obj.get("problem_queries")) if isinstance(q, str)][:4]
        prod = [q for q in as_list(obj.get("product_queries")) if isinstance(q, str)][:2]
        return pq or [str(brief.get("idea"))[:40]], prod or [str(brief.get("idea"))[:40]]

    def gather(self, problem_queries: list[str], product_queries: list[str]) -> dict:
        reg = self.ctx.registry
        pain_sources, product_sources = [], []
        for q in problem_queries:
            pain_sources += reg.add_all(research.search_hn(q, n=6))
            pain_sources += reg.add_all(research.search_stackexchange(q, n=3))
        for q in product_queries:
            product_sources += reg.add_all(research.search_show_hn(q, n=5))
            product_sources += reg.add_all(research.search_github(q, n=4))
        self.ctx.log.append("researcher", "fetch_public_sources", sources=[s.url for s in pain_sources + product_sources],
                            model=None, cost=0, detail=f"{len(pain_sources)} problem posts, {len(product_sources)} products; "
                                                         f"queries: {problem_queries + product_queries}")
        return {"pain_sources": pain_sources, "product_sources": product_sources}

    def extract_pain_signals(self, brief: dict, sources: list, max_sources: int | None = None) -> list[dict]:
        max_sources = max_sources or int(os.getenv("RESEARCH_MAX_SOURCES", "24"))
        sources = sorted(sources, key=lambda s: -len(s.text or ""))[:max_sources]
        verified = []
        for i in range(0, len(sources), 6):
            batch = sources[i:i + 6]
            listing = "\n\n".join(f"[{s.id}] {s.title}\n{s.short(600)}" for s in batch)
            obj = self.ask_json(
                f"PROBLEM we are testing: {brief.get('idea')} (for {brief.get('target_market')}).\n\n"
                f"POSTS:\n{listing}\n\n"
                "For each post, decide if the author (or the people they describe) actually EXPERIENCES this problem "
                "or a close variant of it (wasted time, money, frustration, asking for a solution). "
                "Ads or product launches by vendors do NOT count. If yes, copy a short EXACT quote (8-25 words) from the post.\n"
                'JSON: {"signals": [{"id": "S1", "is_pain": true, "quote": "..."}]}',
                action="extract_pain_signals", sources=[s.url for s in batch], max_tokens=900)
            for sig in as_list(obj.get("signals")):
                if not isinstance(sig, dict) or not sig.get("is_pain"):
                    continue
                src = self.ctx.registry.get(sig.get("id", ""))
                quote = (sig.get("quote") or "").strip().strip('"')
                if src and research.quote_in_source(quote, src):
                    verified.append({"id": src.id, "url": src.url, "quote": quote, "title": src.title,
                                     "origin": src.origin, "date": src.date})
                else:
                    self.ctx.log.append("researcher", "drop_unverified_quote", model=None, cost=0,
                                        sources=[src.url] if src else [], outcome="dropped",
                                        detail=f"quote not found in source {sig.get('id')}: {quote[:120]}")
        # one signal per source
        seen, uniq = set(), []
        for v in verified:
            if v["id"] not in seen:
                seen.add(v["id"])
                uniq.append(v)
        return uniq
