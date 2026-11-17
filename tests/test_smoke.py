"""Smoke tests: pipeline steps, gates, founder approval, guardrails, sale to cash.
Run: pytest -q   (offline, no model needed)"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import guardrails  # noqa: E402
from approval import (ApprovalGate, ApprovalRequest, ApprovalRequired, Decision, DenyApprover,  # noqa: E402
                      FileApprover, payload_hash)
from decision_log import DecisionLog, validate_entries  # noqa: E402
from fakes import FakeLLM, patch_research  # noqa: E402
from gates import DEFAULT_THRESHOLDS as T, demand_gate, evidence_gate  # noqa: E402
from orchestrator import Pipeline  # noqa: E402
from outbox import Outbox  # noqa: E402

BRIEF = (ROOT / "briefs" / "scope_creep_toolkit.md").read_text()
NAME_RE = re.compile(r"^(phase\d+_step\d+_[\w-]+|phase\d+_gate_[\w-]+|payment_test_log[\w-]*)\.(md|json|csv|txt|html)$")


# --- pipeline -----------------------------------------------------------------
def test_full_pipeline_runs_all_six_phases(tmp_path, monkeypatch):
    patch_research(monkeypatch, pain=True)
    dec = tmp_path / "d.json"
    dec.write_text((ROOT / "demo" / "founder_decisions.json").read_text())
    p = Pipeline(BRIEF, approver=FileApprover(dec), llm=FakeLLM(pain=True), out_dir=tmp_path / "out",
                 log_path=tmp_path / "log.json", run_dir=tmp_path / "run")
    s = p.run()
    assert {g["phase"] for g in s["gates"]} == {1, 2, 3, 4, 5, 6}
    names = [f.name for f in (tmp_path / "out").iterdir()]
    assert all(NAME_RE.match(n) for n in names), names
    for must in ("phase1_gate_decision.md", "phase2_gate_demand.md", "phase3_step2_product.md", "payment_test_log.md"):
        assert must in names
    # Phase 2 had no real data, so the system recommended REPEAT; the founder's override is on record.
    g2 = next(g for g in s["gates"] if g["phase"] == 2)
    assert g2["recommendation"] == "repeat" and g2["final"] == "override_go"
    entries = json.loads((tmp_path / "log.json").read_text())
    assert entries and not validate_entries(entries)
    assert "PASS" in (tmp_path / "out" / "phase5_step3_delivery_test.md").read_text()
    assert "Scope Kit" in (tmp_path / "out" / "phase1_step2_scoring.md").read_text()


def test_weak_idea_is_stopped(tmp_path, monkeypatch):
    patch_research(monkeypatch, pain=False)
    p = Pipeline((ROOT / "briefs" / "plant_quotes_app.md").read_text(), approver=DenyApprover(), llm=FakeLLM(pain=False),
                 out_dir=tmp_path, log_path=tmp_path / "log.json", run_dir=tmp_path / "run")
    s = p.run()
    assert s["outcome"] == "stop" and s["phase"] == 1
    assert "Recommendation: STOP" in (tmp_path / "phase1_gate_decision.md").read_text()
    assert not (tmp_path / "phase2_step1_lean_canvas.md").exists()


def test_excluded_category_cannot_be_overridden(tmp_path, monkeypatch):
    patch_research(monkeypatch)
    dec = tmp_path / "d.json"
    dec.write_text(json.dumps({"gate:phase1:policy": {"choice": "override_go"}}))
    p = Pipeline((ROOT / "briefs" / "crypto_signals.md").read_text(), approver=FileApprover(dec), llm=FakeLLM(),
                 out_dir=tmp_path, log_path=tmp_path / "log.json", run_dir=tmp_path / "run")
    s = p.run()
    assert s["outcome"] == "stop" and s["phase"] == 1
    assert (tmp_path / "phase1_gate_policy.md").exists()


# --- gates ----------------------------------------------------------------------
def test_evidence_gate_outcomes():
    weak = evidence_gate(T, pain_signals=0, score=30, interviews=0, interview_pain_ratio=None, best_alternative=None,
                         founder_idea_score=30)
    assert weak.outcome == "stop"
    strong = evidence_gate(T, pain_signals=8, score=75, interviews=6, interview_pain_ratio=0.8, best_alternative=None,
                           founder_idea_score=75)
    assert strong.outcome == "go"
    pivot = evidence_gate(T, pain_signals=6, score=62, interviews=0, interview_pain_ratio=None,
                          best_alternative={"title": "B", "score": 80}, founder_idea_score=62)
    assert pivot.outcome == "pivot"


def test_demand_gate_12_of_100_recommends_stop_not_spin():
    r = demand_gate(T, visitors=400, signups=12, published=True)
    assert r.outcome == "stop"
    assert demand_gate(T, visitors=None, signups=None, published=False).outcome == "repeat"


# --- founder approval -----------------------------------------------------------
def test_nothing_goes_out_without_founder_approval(tmp_path):
    log = DecisionLog(tmp_path / "log.json")
    box = Outbox(tmp_path / "outbox", log)
    with pytest.raises(ApprovalRequired):
        box.publish_post("x", {"text": "hello"}, None)
    rejected = ApprovalGate(DenyApprover(), log).request(ApprovalRequest("publish:x", "publish", "s", {"text": "hello"}))
    assert not rejected.approved
    with pytest.raises(ApprovalRequired):
        box.publish_post("x", {"text": "hello"}, rejected)
    ok = Decision("publish:x", "approved", "approve", "founder", "r", "cli", payload_hash({"text": "hello"}))
    with pytest.raises(ApprovalRequired):  # content changed after approval
        box.publish_post("x", {"text": "hello, edited"}, ok)
    assert box.publish_post("x", {"text": "hello"}, ok).exists()


def test_decisions_file_defaults_to_reject(tmp_path):
    f = tmp_path / "d.json"
    f.write_text("{}")
    d = ApprovalGate(FileApprover(f), DecisionLog(tmp_path / "l.json")).request(
        ApprovalRequest("publish:anything", "publish", "s", {"a": 1}))
    assert d.status == "rejected"


# --- guardrails -----------------------------------------------------------------
@pytest.mark.parametrize("prompt", [p for p in (ROOT / "evals" / "trick_prompts.txt").read_text().splitlines()
                                    if p.strip() and not p.startswith("#")])
def test_trick_prompts_are_refused(prompt):
    assert not guardrails.screen_request(prompt).allowed, prompt


@pytest.mark.parametrize("prompt", ["Write a LinkedIn post announcing my scoping toolkit",
                                    "Draft a polite email asking past clients for honest feedback",
                                    "Suggest three names for a template pack for freelance designers"])
def test_normal_requests_are_allowed(prompt):
    assert guardrails.screen_request(prompt).allowed


def test_output_scanner_removes_fake_proof_and_promises():
    clean, removed = guardrails.scan_output("Great kit. Trusted by 10,000 happy customers. You will earn $5,000 a month. "
                                            "Only 3 left! We do not guarantee income.")
    assert {r for r, _ in removed} >= {"fake_social_proof", "income_promise", "fake_urgency"}
    assert "do not guarantee income" in clean


def test_excluded_categories():
    assert not guardrails.screen_brief("A crypto trading signals channel").allowed
    assert not guardrails.screen_brief("Handmade candles shop").allowed
    assert not guardrails.screen_brief("An AI symptom checker that gives medical advice").allowed
    assert guardrails.screen_brief("A Notion template kit for freelance designers").allowed


# --- decision log ---------------------------------------------------------------
def test_committed_decision_log_is_valid():
    entries = json.loads((ROOT / "decision_log.json").read_text())
    assert entries, "demo decision log is empty"
    assert not validate_entries(entries)


def test_json_repair_handles_small_model_mistakes():
    from llm import extract_json
    assert extract_json('{"ids": [S8, S18], "id": S3}') == {"ids": ["S8", "S18"], "id": "S3"}
    assert extract_json('Sure: {"a": [1, 2,], "b": "x') == {"a": [1, 2]}  # a cut-off last field is dropped, not guessed
