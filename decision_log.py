"""Append-only decision log: one JSON entry per agent action.

Every entry carries the five required keys (action, sources, model, cost,
approved_by) plus timestamp and agent. Extra keys (run_id, outcome, detail)
are allowed.
"""
from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path

REQUIRED_KEYS = ("timestamp", "agent", "action", "sources", "model", "cost", "approved_by")
_lock = threading.Lock()


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class DecisionLog:
    def __init__(self, path: str | os.PathLike | None = None, run_id: str | None = None):
        self.path = Path(path or os.getenv("DECISION_LOG_PATH", "decision_log.json"))
        self.run_id = run_id

    def _read(self) -> list:
        if not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8") or "[]")
            return data if isinstance(data, list) else []
        except json.JSONDecodeError:
            return []

    def append(self, agent: str, action: str, *, sources=None, model=None, cost=0.0,
               approved_by=None, outcome=None, detail=None) -> dict:
        entry = {
            "timestamp": now_iso(),
            "agent": agent,
            "action": action,
            "sources": list(dict.fromkeys(sources or [])),
            "model": model,
            "cost": round(float(cost or 0), 6),
            "approved_by": approved_by,
        }
        if outcome is not None:
            entry["outcome"] = outcome
        if self.run_id:
            entry["run_id"] = self.run_id
        if detail:
            entry["detail"] = str(detail)[:300]
        with _lock:
            data = self._read()
            data.append(entry)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
        return entry

    def entries(self, run_id: str | None = None) -> list:
        data = self._read()
        if run_id:
            data = [e for e in data if e.get("run_id") == run_id]
        return data


def validate_entries(entries: list) -> list[str]:
    """Return a list of problems; empty means the log is valid."""
    problems = []
    for i, e in enumerate(entries):
        for k in REQUIRED_KEYS:
            if k not in e:
                problems.append(f"entry {i}: missing {k}")
        if not isinstance(e.get("sources"), list):
            problems.append(f"entry {i}: sources must be a list")
        if e.get("model") is not None and not isinstance(e.get("model"), str):
            problems.append(f"entry {i}: model must be a string or null")
        if not isinstance(e.get("cost"), (int, float)):
            problems.append(f"entry {i}: cost must be a number")
        if e.get("approved_by") not in (None, "founder"):
            problems.append(f"entry {i}: approved_by must be 'founder' or null")
    return problems
