"""Strategist agent (Phase 1, steps 1-3): sharpen the idea, score it against
alternatives, and define the market.

Scoring is mostly done in code so the number can be audited:
  evidence (40 pts)  = verified pain signals linked to the opportunity, capped at 8
  founder fit, feasibility within budget/time, differentiation, values fit
                     = 15 pts each, from the model's 1-5 ratings with a written reason
"""
from __future__ import annotations

from agents.base import BaseAgent, as_list

WEIGHTS = {"founder_fit": 15, "feasibility": 15, "differentiation": 15, "values_fit": 15}
EVIDENCE_POINTS = 40
EVIDENCE_CAP = 8


def score_opportunity(ratings: dict, evidence_count: int) -> dict:
    parts = {"evidence": round(min(evidence_count, EVIDENCE_CAP) / EVIDENCE_CAP * EVIDENCE_POINTS, 1)}
    for k, w in WEIGHTS.items():
        try:
            r = float(ratings.get(k, 1))
        except (TypeError, ValueError):
            r = 1.0
        r = max(1.0, min(5.0, r))
        parts[k] = round((r - 1) / 4 * w, 1)
    return {"parts": parts, "total": round(sum(parts.values()), 1)}


class StrategistAgent(BaseAgent):
    role = "strategist"

    def opportunities(self, brief: dict, signals: list[dict], products: list) -> list[dict]:
        sig_text = "\n".join(f"[{s['id']}] \"{s['quote']}\"" for s in signals[:14]) or "(no verified pain signals found)"
        prod_text = "\n".join(f"[{p.id}] {p.title}: {p.short(120)}" for p in products[:10]) or "(none found)"
        obj = self.ask_json(
            f"FOUNDER BRIEF:\nIdea: {brief.get('idea')}\nSkills: {brief.get('skills')}\nBudget: {brief.get('budget')}\n"
            f"Time: {brief.get('time')}\nTarget market: {brief.get('target_market')}\nValues: {brief.get('values')}\n\n"
            f"VERIFIED PAIN SIGNALS:\n{sig_text}\n\nEXISTING PRODUCTS:\n{prod_text}\n\n"
            "Propose 3 DIGITAL product opportunities: #1 is a sharpened version of the founder's own idea, #2 and #3 are "
            "alternatives that fit the same founder's skills and market. No physical goods, no financial/crypto, no health or "
            "legal advice products. For each give: title, one_liner, customer (specific), format (e.g. template kit, "
            "guide, small web tool, course), signal_ids (ids of the pain signals above that support it; [] if none), "
            "ratings (1-5 integers for founder_fit, feasibility, differentiation, values_fit), and rating_reasons (one short "
            "sentence per rating). Be strict: rate against the founder's actual skills, budget and time; 5 is rare.\n"
            'JSON: {"opportunities": [{"title": "", "one_liner": "", "customer": "", "format": "", "signal_ids": [], '
            '"ratings": {"founder_fit": 3, "feasibility": 3, "differentiation": 3, "values_fit": 3}, "rating_reasons": {}}]}',
            action="find_opportunities", sources=[s["url"] for s in signals], max_tokens=1800)
        valid_ids = {s["id"] for s in signals}
        opps = []
        for i, o in enumerate(as_list(obj.get("opportunities"))[:3]):
            if not isinstance(o, dict):
                continue
            ids = [x for x in as_list(o.get("signal_ids")) if str(x) in valid_ids]
            if i == 0:
                ids = sorted(valid_ids, key=lambda x: int(x[1:]))  # the founder's own problem: all verified signals
            sc = score_opportunity(o.get("ratings") or {}, len(ids))
            o = self.clean_obj(o, "opportunities")
            o.update({"signal_ids": ids, "score": sc["total"], "score_parts": sc["parts"], "is_founder_idea": i == 0})
            opps.append(o)
        self.ctx.log.append("strategist", "score_opportunities", model=None, cost=0,
                            detail="; ".join(f"{o.get('title')}: {o['score']}" for o in opps))
        return opps

    def market(self, brief: dict, opp: dict, signals: list[dict], products: list) -> dict:
        prod_text = "\n".join(f"[{p.id}] {p.title}: {p.short(150)}" for p in products[:10]) or "(none found)"
        sig_text = "\n".join(f"[{s['id']}] \"{s['quote']}\"" for s in signals[:10]) or "(none)"
        obj = self.ask_json(
            f"OPPORTUNITY: {opp.get('title')} - {opp.get('one_liner')}\nCustomer: {opp.get('customer')}\n"
            f"Founder target market: {brief.get('target_market')}\n\nPAIN SIGNALS:\n{sig_text}\n\nEXISTING PRODUCTS:\n{prod_text}\n\n"
            "Define the market. Give: icp (one paragraph: who exactly, their situation, trigger moment), segments (2-3 short "
            "strings), competitors (from EXISTING PRODUCTS only: name, source_id, how ours differs), claims (3-6 market claims, "
            "each with source_ids that directly support it, or [] if it is your assumption), and size_note (how the founder "
            "could estimate market size; do NOT invent numbers).\n"
            'JSON: {"icp": "", "segments": [], "competitors": [{"name": "", "source_id": "", "difference": ""}], '
            '"claims": [{"claim": "", "source_ids": []}], "size_note": ""}',
            action="define_market", sources=[p.url for p in products] + [s["url"] for s in signals], max_tokens=1200)
        return self.clean_obj(obj, "market")
