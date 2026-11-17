"""QA agent (Phase 3 gate): deterministic acceptance tests on the built product.
No model is involved, so the gate cannot be talked into passing."""
from __future__ import annotations

import re

import guardrails

PLACEHOLDER = re.compile(r"lorem ipsum|\bTODO\b|\[insert|\bTBD\b|xxx", re.I)
STAT = re.compile(r"\b\d{1,3}(\.\d+)?\s?%|\bstudies show\b|\bresearch shows\b", re.I)


def words(s: str) -> int:
    return len(re.findall(r"\w+", s or ""))


def test_product(spec: dict, sections: dict[str, str], docs: str) -> list[dict]:
    results = []
    for sec in spec.get("sections", []):
        title = sec.get("title")
        body = sections.get(title, "")
        n = words(body)
        results.append({"name": f"section '{title}' has 120-600 words", "section": title,
                        "passed": 120 <= n <= 600, "detail": f"{n} words"})
        must = (sec.get("must_include") or "").strip().lower()
        if must:
            ok = must in body.lower() or all(w in body.lower() for w in must.split()[:3])
            results.append({"name": f"section '{title}' covers '{must}'", "section": title, "passed": ok,
                            "detail": "missing required phrase" if not ok else ""})
        stats = [m.group(0) for line in body.splitlines() for m in STAT.finditer(line)
                 if "ASSUMPTION" not in line and not re.search(r"\[S\d+\]", line)]
        results.append({"name": f"section '{title}' has no unsourced statistics", "section": title,
                        "passed": not stats, "detail": f"unsourced: {stats[:3]}" if stats else ""})
        ph = PLACEHOLDER.search(body)
        results.append({"name": f"section '{title}' has no placeholder text", "section": title,
                        "passed": not ph, "detail": ph.group(0) if ph else ""})
    full = "\n".join(sections.values()) + "\n" + docs
    _, removed = guardrails.scan_output(full)
    leftover = "[removed by guardrail" in full
    results.append({"name": "no promises, fake proof or fake urgency", "section": None,
                    "passed": not removed and not leftover,
                    "detail": f"{len(removed)} violation(s)" if removed or leftover else ""})
    for h in ("quick start", "how to get help", "refund"):
        results.append({"name": f"user docs include '{h}'", "section": "__docs__", "passed": h in docs.lower(),
                        "detail": "" if h in docs.lower() else "missing"})
    return results
