"""Pricing agent (Phase 4, step 1). Proposes a price; code sanity-checks it.
No payments of any kind are set up here."""
from __future__ import annotations

import re

from agents.base import BaseAgent


def to_number(x) -> float | None:
    if isinstance(x, (int, float)):
        return float(x)
    m = re.search(r"\d+(\.\d+)?", str(x or ""))
    return float(m.group(0)) if m else None


class PricingAgent(BaseAgent):
    role = "pricing"

    def propose(self, spec: dict, opp: dict, competitors: list[dict], brief: dict) -> dict:
        comp = "\n".join(f"- {c.get('name')} ({c.get('source_id')}): {c.get('difference')}" for c in competitors[:6]) or "(none found)"
        obj = self.ask_json(
            f"Digital product: {spec.get('product_name')} - {spec.get('promise')}\nCustomer: {opp.get('customer')}\n"
            f"Founder values: {brief.get('values')}\nKnown alternatives:\n{comp}\n\n"
            "Propose launch pricing in USD for a one-time purchase: price (number), currency, free_preview (what part is "
            "free to read before buying), rationale (2-3 sentences; reference alternatives only by their source id; "
            "anything else is an assumption), price_test (how to test a higher and lower price honestly), "
            "refund_days (integer, 14 or 30). No discounts that expire, no urgency.\n"
            'JSON: {"price": 19, "currency": "USD", "free_preview": "", "rationale": "", "price_test": "", "refund_days": 14}',
            action="propose_pricing", max_tokens=600)
        obj = self.clean_obj(obj, "pricing")
        price = to_number(obj.get("price"))
        issues = []
        if price is None or price <= 0:
            issues.append("no valid price")
            price = None
        elif price > 500:
            issues.append("price above $500 for a first digital product; capped for review")
            price = 500.0
        rd = int(to_number(obj.get("refund_days")) or 14)
        obj.update({"price": price, "refund_days": rd if rd in (14, 30) else 14, "issues": issues,
                    "currency": "USD"})
        return obj
