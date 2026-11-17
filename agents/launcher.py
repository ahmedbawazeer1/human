"""Launcher agent (Phase 5): store page and launch posts. Drafts only;
each one is published (MOCKED) only after the founder approves it."""
from __future__ import annotations

from pathlib import Path
from string import Template

from agents.base import BaseAgent, as_list
from agents.validator import esc

TEMPLATES = Path(__file__).resolve().parent.parent / "templates"


class LauncherAgent(BaseAgent):
    role = "launcher"

    def store_copy(self, spec: dict, pricing: dict) -> dict:
        obj = self.ask_json(
            f"Product: {spec.get('product_name')} - {spec.get('promise')}\nSections: "
            f"{', '.join(s.get('title', '') for s in spec.get('sections', []))}\nPrice: ${pricing.get('price')}\n"
            f"Free preview: {pricing.get('free_preview')}\n\n"
            "Write honest store page copy: headline, description (2-3 sentences), whats_inside (list matching the sections), "
            "who_its_for, who_its_not_for. No reviews, ratings, user counts, urgency or income promises.\n"
            'JSON: {"headline": "", "description": "", "whats_inside": [], "who_its_for": "", "who_its_not_for": ""}',
            action="write_store_page", max_tokens=800)
        return self.clean_obj(obj, "store_page")

    def render_store(self, copy: dict, spec: dict, pricing: dict, refund_days: int) -> str:
        tpl = Template((TEMPLATES / "store.html").read_text(encoding="utf-8"))
        inside = "".join(f"<li>{esc(x)}</li>" for x in as_list(copy.get("whats_inside")))
        return tpl.substitute(title=esc(spec.get("product_name")), headline=esc(copy.get("headline")),
                              description=esc(copy.get("description")), inside=inside,
                              for_=esc(copy.get("who_its_for")), not_for=esc(copy.get("who_its_not_for")),
                              price=esc(f"{pricing.get('price'):.2f}" if pricing.get("price") else "TBD"),
                              preview=esc(pricing.get("free_preview")), refund_days=refund_days)

    def posts(self, spec: dict, opp: dict) -> list[dict]:
        obj = self.ask_json(
            f"Product: {spec.get('product_name')} - {spec.get('promise')}\nCustomer: {opp.get('customer')}\n\n"
            "Draft 3 launch posts written in the FOUNDER's own voice, to be posted by the founder from their own accounts "
            "after they review them: one for LinkedIn, one for a relevant community that allows self-promotion threads, and "
            "one short email to people who joined the waitlist. Be transparent that the founder made it. No hype, no urgency, "
            "no income promises, no fake numbers.\n"
            'JSON: {"posts": [{"channel": "", "text": ""}]}',
            action="draft_launch_posts", max_tokens=900)
        return [p for p in self.clean_obj(as_list(obj.get("posts")), "launch_posts") if isinstance(p, dict)][:3]
