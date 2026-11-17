"""Interviewer agent (Phase 1, step 4): Mom Test interviews.

The system never invents interviews. It writes the interview script, and if
the founder supplies real interview notes it analyses them: compliments and
hypotheticals do not count, past behaviour and commitments do.
"""
from __future__ import annotations

import re

from agents.base import BaseAgent


def split_interviews(notes: str) -> list[str]:
    parts = re.split(r"(?im)^\s*#{1,3}\s*interview\b.*$|^\s*-{3,}\s*$", notes or "")
    return [p.strip() for p in parts if p and len(p.strip()) > 40]


class InterviewerAgent(BaseAgent):
    role = "interviewer"

    def script(self, opp: dict) -> dict:
        obj = self.ask_json(
            f"Customer: {opp.get('customer')}\nProblem area: {opp.get('one_liner')}\n\n"
            "Write a Mom Test customer interview plan: who_to_talk_to (where to find 5-10 of them, no spam), "
            "questions (8 questions about their PAST behaviour and current workarounds; never pitch the idea; no "
            "'would you use/buy' questions), signals_to_listen_for (3-5), and commitments_to_ask_for (2-3 honest "
            "next steps like a follow-up call or trying an early version).\n"
            'JSON: {"who_to_talk_to": "", "questions": [], "signals_to_listen_for": [], "commitments_to_ask_for": []}',
            action="write_mom_test_script", max_tokens=900)
        return self.clean_obj(obj, "interview_script")

    def analyse(self, notes: str, opp: dict) -> dict:
        interviews = split_interviews(notes)
        results = []
        for i, text in enumerate(interviews, 1):
            obj = self.ask_json(
                f"Problem area: {opp.get('one_liner')}\n\nINTERVIEW NOTES #{i} (written by the founder):\n{text[:3000]}\n\n"
                "Apply the Mom Test. Answer: has_problem (true only if they described a real past situation, not an opinion), "
                "workaround (what they do today), spent_time_or_money (true/false), commitment (a concrete next step they "
                "agreed to, or null), compliments_only (true if they only said nice things about the idea), quote (exact words "
                "copied from the notes that best show the problem, or null).\n"
                'JSON: {"has_problem": false, "workaround": null, "spent_time_or_money": false, "commitment": null, '
                '"compliments_only": false, "quote": null}',
                action="analyse_interview", max_tokens=400)
            quote = (obj.get("quote") or "").strip().strip('"')
            if quote and quote.lower()[:40] not in text.lower():
                obj["quote"] = None  # never keep a quote that is not in the notes
            obj["has_problem"] = bool(obj.get("has_problem")) and not obj.get("compliments_only")
            results.append(obj)
        n = len(results)
        with_problem = sum(1 for r in results if r.get("has_problem"))
        return {"count": n, "with_problem": with_problem,
                "pain_ratio": (with_problem / n) if n else None,
                "commitments": [r.get("commitment") for r in results if r.get("commitment")],
                "results": results}

    @staticmethod
    def empty() -> dict:
        return {"count": 0, "with_problem": 0, "pain_ratio": None, "commitments": [], "results": []}
