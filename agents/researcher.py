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
import re

from agents.base import BaseAgent, as_list
from tools import research


STOPWORDS = set("""about after again also another because been before being between both build built could daily does doing down each
every from have help helps into just like make many more most much need only other over people really same should some such than that
their them then there these they this those through tool tools very want what when where which while with without would your yours
using used user users app apps mobile online digital product products simple easy best better small new get gets
send sends ready stop stops start keep""".split())


def keywords(*texts) -> set[str]:
    words = set()
    for t in texts:
        for w in re.findall(r"[a-z]{4,}", str(t or "").lower()):
            if w not in STOPWORDS:
                words.add(w[:-1] if w.endswith("s") and len(w) > 4 else w)
    return words


def relevance_hits(source, kws: set[str]) -> set[str]:
    text = (source.title + " " + source.text).lower()
    return {k for k in kws if re.search(rf"\b{re.escape(k)}", text)}


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
        pq = pq or [str(brief.get("idea"))[:40]]
        prod = prod or [str(brief.get("idea"))[:40]]
        self.ctx.state["queries"] = pq + prod
        return pq, prod

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
        # Code-level relevance filter: a post must mention at least 2 distinct key terms of the problem.
        kws = keywords(brief.get("idea"), brief.get("target_market"), " ".join(self.ctx.state.get("queries", [])))
        # Core terms come only from the founder's own words; the quote itself must mention one of them.
        core = keywords(brief.get("idea"), brief.get("target_market"))
        relevant = [s for s in sources if len(relevance_hits(s, kws)) >= 2]
        self.ctx.log.append("researcher", "filter_relevant_sources", model=None, cost=0,
                            sources=[s.url for s in relevant],
                            detail=f"{len(relevant)}/{len(sources)} posts mention >=2 key terms of the problem")
        sources = sorted(relevant, key=lambda s: -len(s.text or ""))[:max_sources]
        verified = []
        for i in range(0, len(sources), 6):
            batch = sources[i:i + 6]
            listing = "\n\n".join(f"[{s.id}] {s.title}\n{s.short(600)}" for s in batch)
            obj = self.ask_json(
                f"PROBLEM we are testing: {brief.get('idea')} (for {brief.get('target_market')}).\n\n"
                f"POSTS:\n{listing}\n\n"
                "For each post answer two questions. relevant: is the post about THIS specific problem for THIS kind of "
                "customer (not just a similar word)? is_pain: does the author or the people they describe actually EXPERIENCE "
                "it (wasted time or money, frustration, asking for a solution)? Ads and product launches by vendors are not pain. "
                "Most posts are NOT relevant; say false when unsure. If both are true, copy a short EXACT quote (8-25 words) "
                "from the post that shows the problem.\n"
                'JSON: {"signals": [{"id": "S1", "relevant": false, "is_pain": false, "quote": null}]}',
                action="extract_pain_signals", sources=[s.url for s in batch], max_tokens=900)
            for sig in as_list(obj.get("signals")):
                if not isinstance(sig, dict) or not sig.get("is_pain") or not sig.get("relevant"):
                    continue
                src = self.ctx.registry.get(sig.get("id", ""))
                quote = (sig.get("quote") or "").strip().strip('"')
                quote_terms = relevance_hits(research.Source("", "", "", quote, ""), core) if src else set()
                if src and research.quote_in_source(quote, src) and not quote_terms:
                    self.ctx.log.append("researcher", "drop_offtopic_quote", model=None, cost=0, sources=[src.url],
                                        outcome="dropped", detail=f"quote does not mention the problem ({sorted(core)[:8]}): {quote[:120]}")
                    continue
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
