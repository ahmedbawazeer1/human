"""Validator agent (Phase 2): Lean Canvas, landing page, demand test plan."""
from __future__ import annotations

import html
from pathlib import Path
from string import Template

from agents.base import BaseAgent, as_list

TEMPLATES = Path(__file__).resolve().parent.parent / "templates"
CANVAS_BOXES = ["problem", "customer_segments", "unique_value_proposition", "solution", "channels",
                "revenue_streams", "cost_structure", "key_metrics", "unfair_advantage"]


def esc(x) -> str:
    return html.escape(str(x or ""))


class ValidatorAgent(BaseAgent):
    role = "validator"

    def lean_canvas(self, brief: dict, opp: dict, market: dict, signals: list[dict]) -> dict:
        sig_text = "\n".join(f"[{s['id']}] \"{s['quote']}\"" for s in signals[:8]) or "(none)"
        obj = self.ask_json(
            f"Opportunity: {opp.get('title')} - {opp.get('one_liner')}\nCustomer: {opp.get('customer')}\n"
            f"Format: {opp.get('format')}\nFounder budget: {brief.get('budget')}; time: {brief.get('time')}\n"
            f"ICP: {market.get('icp')}\n\nPAIN SIGNALS:\n{sig_text}\n\n"
            f"Fill a Lean Canvas. Keys: {', '.join(CANVAS_BOXES)}. Each value is a list of 1-3 items; each item is "
            '{"text": "...", "source_ids": []} with source ids only where a pain signal above directly supports it.\n'
            'JSON: {"problem": [{"text": "", "source_ids": []}], ...}',
            action="lean_canvas", sources=[s["url"] for s in signals], max_tokens=1300)
        return {k: [i if isinstance(i, dict) else {"text": str(i), "source_ids": []} for i in as_list(obj.get(k))]
                for k in CANVAS_BOXES} | {}

    def landing_copy(self, opp: dict, market: dict) -> dict:
        obj = self.ask_json(
            f"Product: {opp.get('title')} - {opp.get('one_liner')}\nCustomer: {opp.get('customer')}\nFormat: {opp.get('format')}\n"
            f"ICP: {market.get('icp')}\n\n"
            "Write honest landing page copy for a WAITLIST demand test (the product does not exist yet; say so). "
            "No testimonials, no user counts, no ratings, no urgency, no income promises. "
            'JSON: {"headline": "", "subheadline": "", "benefits": ["", "", ""], "how_it_works": ["", "", ""], '
            '"cta": "Join the waitlist", "faq": [{"q": "", "a": ""}]}',
            action="write_landing_copy", max_tokens=900)
        return self.clean_obj(obj, "landing_page")

    def render_landing(self, copy: dict, run_id: str, product_name: str) -> str:
        tpl = Template((TEMPLATES / "landing.html").read_text(encoding="utf-8"))
        benefits = "".join(f"<li>{esc(b)}</li>" for b in as_list(copy.get("benefits")))
        steps = "".join(f"<li>{esc(b)}</li>" for b in as_list(copy.get("how_it_works")))
        faq = "".join(f"<dt>{esc(f.get('q'))}</dt><dd>{esc(f.get('a'))}</dd>"
                      for f in as_list(copy.get("faq")) if isinstance(f, dict))
        return tpl.substitute(title=esc(product_name), headline=esc(copy.get("headline")),
                              subheadline=esc(copy.get("subheadline")), benefits=benefits, steps=steps, faq=faq,
                              cta=esc(copy.get("cta") or "Join the waitlist"), run_id=esc(run_id))

    def demand_plan(self, opp: dict, t: dict) -> dict:
        obj = self.ask_json(
            f"Product: {opp.get('title')}\nCustomer: {opp.get('customer')}\n"
            f"The pre-set target is {t['p2_target_signups']} real waitlist sign-ups in {t['p2_window_days']} days.\n"
            "Suggest 4 honest, free or low-cost ways for the founder to get the landing page in front of the right people "
            "(communities where self-promotion is allowed, the founder's own network, content). No spam, no buying lists, "
            "no fake accounts. Also list 3 things to measure.\n"
            'JSON: {"channels": [{"channel": "", "how": ""}], "measure": []}',
            action="plan_demand_test", max_tokens=700)
        return self.clean_obj(obj, "demand_plan")
