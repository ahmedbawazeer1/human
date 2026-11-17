"""Outbound actions: publish, send. All MOCKED, and all refuse to run without
a founder approval whose payload hash matches the content.

MOCKED means: nothing leaves this machine. "Publishing" writes the approved
content to the run's local outbox folder so the founder can post it by hand
from their own accounts.
"""
from __future__ import annotations

import json
from pathlib import Path

from approval import Decision, require_approved
from decision_log import DecisionLog, now_iso

MOCK_LABEL = "MOCKED"


class Outbox:
    def __init__(self, folder: str | Path, log: DecisionLog):
        self.folder = Path(folder)
        self.log = log

    def _write(self, kind: str, name: str, payload: dict, decision: Decision) -> Path:
        require_approved(decision, payload)
        self.folder.mkdir(parents=True, exist_ok=True)
        path = self.folder / f"{kind}_{name}.json"
        path.write_text(json.dumps({"status": MOCK_LABEL, "kind": kind, "queued_at": now_iso(),
                                    "approved_by": decision.by, "approval_reason": decision.reason,
                                    "payload": payload}, indent=2, ensure_ascii=False), encoding="utf-8")
        self.log.append("outbox", f"{kind}:{name} ({MOCK_LABEL}, not sent)", approved_by="founder",
                        detail=f"written to {path.name}; nothing left the machine")
        return path

    def publish_page(self, name: str, payload: dict, decision: Decision) -> Path:
        return self._write("publish_page", name, payload, decision)

    def publish_post(self, name: str, payload: dict, decision: Decision) -> Path:
        return self._write("publish_post", name, payload, decision)

    def send_message(self, name: str, payload: dict, decision: Decision) -> Path:
        return self._write("send_message", name, payload, decision)

    def open_store(self, payload: dict, decision: Decision) -> Path:
        return self._write("open_store", "store", payload, decision)
