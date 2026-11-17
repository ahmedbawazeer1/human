"""Operator agent (Phase 6): support drafts, metrics and the persevere-or-pivot memo."""
from __future__ import annotations

from agents.base import BaseAgent


class OperatorAgent(BaseAgent):
    role = "operator"

    def support(self, spec: dict, refund_days: int) -> dict:
        obj = self.ask_json(
            f"Product: {spec.get('product_name')} - {spec.get('promise')}. Refund window: {refund_days} days.\n"
            "Write support material: faq (5 Q&A pairs a buyer may ask) and reply_templates (3 short email templates: "
            "download problem, refund request, product question). Replies are drafts the founder sends. Never promise results.\n"
            'JSON: {"faq": [{"q": "", "a": ""}], "reply_templates": [{"name": "", "text": ""}]}',
            action="write_support_material", max_tokens=1000)
        return self.clean_obj(obj, "support")

    def memo(self, metrics: dict, gate_md: str, history: str) -> str:
        return self.ask_text(
            f"METRICS (real unless marked MOCKED):\n{metrics}\n\nGATE RESULT:\n{gate_md}\n\nHISTORY OF GATES:\n{history}\n\n"
            "Write a one-page persevere-or-pivot memo for the founder: Situation, What the evidence says (only from the data "
            "above; say clearly when there is no real data), Recommendation (must match the gate result), Next 3 actions, "
            "What would change our mind. Markdown with level-2 headings. No income promises.",
            action="write_persevere_pivot_memo", max_tokens=900)
