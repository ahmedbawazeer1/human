"""Builder agent (Phase 3): MVP spec, the product itself, and user docs.

The MVP is a digital toolkit (guide + checklists + templates) written as
Markdown, which a small local model can produce reliably and a buyer can use
the same day. Each section has acceptance criteria that QA checks in code.
"""
from __future__ import annotations

import re

from agents.base import BaseAgent, as_list


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (s or "product").lower()).strip("-")[:40] or "product"


class BuilderAgent(BaseAgent):
    role = "builder"

    def spec(self, opp: dict, canvas: dict) -> dict:
        uvp = "; ".join(i.get("text", "") for i in canvas.get("unique_value_proposition", []))
        obj = self.ask_json(
            f"Product idea: {opp.get('title')} - {opp.get('one_liner')}\nCustomer: {opp.get('customer')}\n"
            f"Value proposition: {uvp}\n\n"
            "Specify the smallest useful version (MVP) as a digital toolkit in Markdown: product_name (2-4 words, must not "
            "use another company's brand), promise (one sentence, no income claims), sections (4-5 sections, each with "
            "title, purpose, and must_include: one short keyword phrase that the section must contain), out_of_scope (3 items).\n"
            'JSON: {"product_name": "", "promise": "", "sections": [{"title": "", "purpose": "", "must_include": ""}], '
            '"out_of_scope": []}',
            action="write_mvp_spec", max_tokens=900)
        obj = self.clean_obj(obj, "mvp_spec")
        obj["sections"] = [s for s in as_list(obj.get("sections")) if isinstance(s, dict) and s.get("title")][:5]
        return obj

    def rename(self, spec: dict, taken: list[str]) -> str:
        obj = self.ask_json(
            f"The product name \"{spec.get('product_name')}\" is already used by an existing product. "
            f"Existing product names to avoid: {', '.join(taken[:15])}.\n"
            f"Suggest a new, plain, descriptive product name (2-4 words) for: {spec.get('promise')}. "
            "It must not contain any of the existing names or another company's brand.\n"
            'JSON: {"product_name": ""}', action="rename_product_to_avoid_brand_clash", max_tokens=100)
        return str(obj.get("product_name") or "").strip()

    def write_section(self, spec: dict, section: dict, feedback: str = "") -> str:
        text = self.ask_text(
            f"Product: {spec.get('product_name')} - {spec.get('promise')}\n"
            f"Write the section \"{section.get('title')}\" (purpose: {section.get('purpose')}).\n"
            f"It MUST contain the phrase \"{section.get('must_include')}\".\n"
            "Format: Markdown, 180-350 words, practical steps, a checklist or a fill-in template. Start with a level-2 heading "
            "of the section title. No statistics or percentages unless you write 'ASSUMPTION' next to them. "
            "No testimonials, no income promises." + (f"\nFix these problems from the last attempt: {feedback}" if feedback else ""),
            action=f"build_section:{slug(section.get('title'))}", max_tokens=700)
        return text

    def user_docs(self, spec: dict, refund_days: int = 14) -> str:
        return self.ask_text(
            f"Write short user documentation for the digital product \"{spec.get('product_name')}\" ({spec.get('promise')}). "
            f"Sections in this order, as level-2 headings: Quick start, What's inside, How to get help, Refunds. "
            f"In Refunds say buyers can ask for a refund within {refund_days} days and access is removed when a refund is made. "
            "In How to get help, tell users to reply to their delivery email. 150-300 words. Markdown.",
            action="write_user_docs", max_tokens=600)
