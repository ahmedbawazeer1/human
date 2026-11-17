"""Legal agent (Phase 4, step 2): drafts terms, privacy and refund policies."""
from __future__ import annotations

from agents.base import BaseAgent


class LegalAgent(BaseAgent):
    """Phase 4, step 2: fills policy templates in code (no model, no legal advice)."""
    role = "legal"

    def drafts(self, product_name: str, refund_days: int, templates_dir) -> dict:
        out = {}
        for name in ("terms", "privacy", "refunds"):
            text = (templates_dir / f"{name}.md").read_text(encoding="utf-8")
            text = text.replace("{{product}}", product_name).replace("{{refund_days}}", str(refund_days))
            out[name] = text
        self.ctx.log.append("legal", "draft_policies_from_templates", model=None, cost=0,
                            detail="terms, privacy, refunds drafted from open templates; DRAFT, needs founder sign-off")
        return out
