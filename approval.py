"""Founder approval, enforced in code.

Anything that would be published, sent, spent or signed goes through
`ApprovalGate.request(...)`. The returned `Decision` is checked again by
`require_approved(...)` right before the outbound function runs, and the
payload hash must match, so an approval for one text cannot be reused to
publish a different text.

Approvers:
- CLIApprover:   asks the founder in the terminal (approve / reject + reason).
- WebApprover:   the web UI shows Approve / Reject buttons; the pipeline waits.
- FileApprover:  the founder's pre-written decisions file (JSON). Anything not
                 listed in the file is rejected.
- DenyApprover:  default when nobody is there to ask: everything is rejected.

There is no auto-approve mode.
"""
from __future__ import annotations

import hashlib
import json
import sys
import threading
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path

from decision_log import DecisionLog, now_iso


class ApprovalRequired(PermissionError):
    """Raised when an outbound action runs without a matching founder approval."""


def payload_hash(payload) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


@dataclass
class ApprovalRequest:
    key: str                  # stable id, e.g. "publish:landing_page" or "gate:phase1"
    kind: str                 # "publish" | "send" | "spend" | "sign" | "gate"
    summary: str              # what the founder is asked to approve
    payload: dict = field(default_factory=dict)
    recommendation: str | None = None      # for gates: go / repeat / pivot / stop
    options: list = field(default_factory=lambda: ["approve", "reject"])
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:10])
    created: str = field(default_factory=now_iso)

    @property
    def hash(self) -> str:
        return payload_hash(self.payload)


@dataclass
class Decision:
    request_key: str
    status: str               # "approved" | "rejected"
    choice: str               # the option picked (approve / reject / accept / override_go ...)
    by: str | None            # "founder" or None when no human decided
    reason: str
    channel: str              # cli / web / file / default-deny
    payload_hash: str
    timestamp: str = field(default_factory=now_iso)

    @property
    def approved(self) -> bool:
        return self.status == "approved" and self.by == "founder"


class Approver:
    channel = "base"

    def decide(self, req: ApprovalRequest) -> tuple[str, str]:
        raise NotImplementedError


class DenyApprover(Approver):
    channel = "default-deny"

    def decide(self, req):
        return "reject", "No founder available to approve; default is reject."


class CLIApprover(Approver):
    channel = "cli"

    def __init__(self, stream_in=None, stream_out=None):
        self.inp = stream_in or sys.stdin
        self.out = stream_out or sys.stdout

    def decide(self, req):
        o = self.out
        o.write("\n" + "=" * 70 + "\nFOUNDER APPROVAL NEEDED\n" + "=" * 70 + "\n")
        o.write(f"{req.summary}\n")
        if req.recommendation:
            o.write(f"System recommendation: {req.recommendation.upper()}\n")
        o.write(f"Options: {', '.join(req.options)}\n> ")
        o.flush()
        choice = (self.inp.readline() or "").strip().lower()
        if choice not in req.options:
            choice = "reject" if "reject" in req.options else req.options[-1]
        o.write("Reason (optional): ")
        o.flush()
        reason = (self.inp.readline() or "").strip() or "founder decision in terminal"
        return choice, reason


class FileApprover(Approver):
    """Founder's decisions written in advance: {"<request key>": {"choice": "...", "reason": "..."}}."""
    channel = "file"

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.decisions = json.loads(self.path.read_text(encoding="utf-8"))

    def decide(self, req):
        d = self.decisions.get(req.key)
        if not d:
            return ("reject" if "reject" in req.options else "stop"), f"not in founder decisions file {self.path.name}; default reject"
        choice = d.get("choice", "reject")
        if choice == "continue":
            # "accept the recommendation if it is GO, otherwise override and continue" (recorded as an override)
            choice = "accept" if req.recommendation == "go" else ("override_go" if "override_go" in req.options else "accept")
        if choice not in req.options:
            return ("reject" if "reject" in req.options else "stop"), f"invalid choice '{choice}' in decisions file; default reject"
        return choice, d.get("reason", "founder decision from decisions file")


class WebApprover(Approver):
    """Blocks the pipeline thread until the founder clicks in the web UI."""
    channel = "web"

    def __init__(self, timeout: float = 3600):
        self.pending: dict[str, ApprovalRequest] = {}
        self.answers: dict[str, tuple[str, str]] = {}
        self.events: dict[str, threading.Event] = {}
        self.timeout = timeout
        self.lock = threading.Lock()

    def decide(self, req):
        ev = threading.Event()
        with self.lock:
            self.pending[req.id] = req
            self.events[req.id] = ev
        ev.wait(self.timeout)
        with self.lock:
            self.pending.pop(req.id, None)
            ans = self.answers.pop(req.id, None)
        if not ans:
            return ("reject" if "reject" in req.options else "stop"), "no answer before timeout; default reject"
        return ans

    def answer(self, request_id: str, choice: str, reason: str) -> bool:
        with self.lock:
            req = self.pending.get(request_id)
            if not req or choice not in req.options:
                return False
            self.answers[request_id] = (choice, reason or "founder decision in web UI")
            self.events[request_id].set()
            return True

    def list_pending(self) -> list[dict]:
        with self.lock:
            return [asdict(r) | {"hash": r.hash} for r in self.pending.values()]


APPROVING_CHOICES = {"approve", "accept", "override_go", "go"}


class ApprovalGate:
    def __init__(self, approver: Approver | None = None, log: DecisionLog | None = None):
        self.approver = approver or DenyApprover()
        self.log = log or DecisionLog()
        self.history: list[Decision] = []

    def request(self, req: ApprovalRequest, agent: str = "approval") -> Decision:
        choice, reason = self.approver.decide(req)
        human = self.approver.channel in ("cli", "web", "file")
        approved = choice in APPROVING_CHOICES and human
        decision = Decision(
            request_key=req.key,
            status="approved" if approved else "rejected",
            choice=choice,
            by="founder" if human else None,
            reason=reason,
            channel=self.approver.channel,
            payload_hash=req.hash,
        )
        self.history.append(decision)
        self.log.append(agent, f"founder_decision:{req.key}", model=None, cost=0,
                        approved_by="founder" if approved else None,
                        outcome=choice, detail=f"{decision.status} via {decision.channel}: {reason}")
        return decision


def require_approved(decision: Decision | None, payload) -> None:
    """Hard check run inside every outbound function."""
    if decision is None or not decision.approved:
        raise ApprovalRequired("Founder approval is required before anything is published, sent, spent or signed.")
    if decision.payload_hash != payload_hash(payload):
        raise ApprovalRequired("The content changed after approval; the founder must approve the new version.")
