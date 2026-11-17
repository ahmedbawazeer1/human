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

    RUBRIC = ("Ratings 1-5, be strict and use the founder's actual skills, budget and time: "
              "founder_fit (5 = the founder's skills are exactly what this needs), feasibility (1 = needs skills, money or "
              "time the founder does not have; 5 = shippable in 2 weeks with what they have), differentiation (5 = clearly "
              "different from the existing products listed), values_fit (5 = fully matches the founder's values). "
              "5 is rare. Give one short reason (under 20 words) per rating.")

    def _rate(self, brief, sig_text, prod_text, ask: str, action: str, sources) -> list[dict]:
        obj = self.ask_json(
            f"FOUNDER BRIEF:\nIdea: {brief.get('idea')}\nSkills: {brief.get('skills')}\nBudget: {brief.get('budget')}\n"
            f"Time: {brief.get('time')}\nTarget market: {brief.get('target_market')}\nValues: {brief.get('values')}\n\n"
            f"VERIFIED PAIN SIGNALS:\n{sig_text}\n\nEXISTING PRODUCTS:\n{prod_text}\n\n{ask}\n{self.RUBRIC}\n"
            "Digital products only: no physical goods, no financial/crypto, no health or legal advice. Keep strings short.\n"
            'JSON: {"opportunities": [{"title": "", "one_liner": "", "customer": "", "format": "", "signal_ids": [], '
            '"ratings": {"founder_fit": 1, "feasibility": 1, "differentiation": 1, "values_fit": 1}, '
            '"reasons": {"founder_fit": "", "feasibility": "", "differentiation": "", "values_fit": ""}}]}',
            action=action, sources=sources, max_tokens=1000)
        items = obj.get("opportunities") if isinstance(obj.get("opportunities"), list) else obj.get("items")
        return [o for o in as_list(items) if isinstance(o, dict) and o.get("title")]

    def opportunities(self, brief: dict, signals: list[dict], products: list) -> list[dict]:
        sig_text = "\n".join(f"[{s['id']}] \"{s['quote']}\"" for s in signals[:12]) or "(no verified pain signals found)"
        prod_text = "\n".join(f"[{p.id}] {p.title[:80]}: {p.short(100)}" for p in products[:8]) or "(none found)"
        urls = [s["url"] for s in signals]
        own = []
        for _ in range(2):  # one retry: the founder's own idea must be rated
            own = self._rate(brief, sig_text, prod_text,
                             "Sharpen the FOUNDER'S OWN idea into ONE specific digital product (keep the founder's idea; make "
                             "the customer and format concrete) and rate it.", "find_opportunities:founder_idea", urls)
            if own:
                break
        alts = self._rate(brief, sig_text, prod_text,
                          "Propose TWO different alternative digital products that fit this founder's skills and market "
                          "better, and rate them. signal_ids: only ids above that directly support each one.",
                          "find_opportunities:alternatives", urls)
        valid_ids = {s["id"] for s in signals}
        opps = []
        for i, o in enumerate(own[:1] + alts[:2]):
            founder = i == 0 and bool(own)
            ids = [str(x) if str(x).startswith("S") else f"S{x}" for x in as_list(o.get("signal_ids"))]
            ids = [x for x in ids if x in valid_ids]
            if founder:
                ids = sorted(valid_ids, key=lambda x: int(x[1:]))  # the founder's problem: every verified signal
            sc = score_opportunity(o.get("ratings") or {}, len(ids))
            o = self.clean_obj(o, "opportunities")
            o.update({"signal_ids": ids, "score": sc["total"], "score_parts": sc["parts"], "is_founder_idea": founder,
                      "rating_reasons": o.get("reasons") or o.get("rating_reasons") or {}})
            opps.append(o)
        if not own:
            self.ctx.log.append("strategist", "rate_founder_idea_failed", model=None, cost=0, outcome="model_error",
                                detail="model gave no usable rating; the founder idea is scored on evidence only")
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
