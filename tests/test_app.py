"""Smoke test for the web UI: start a run, answer the founder approvals in the browser API,
and check that trick prompts are refused. Offline (fake model, fake research)."""
from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from fastapi.testclient import TestClient  # noqa: E402

import app as app_mod  # noqa: E402
import orchestrator  # noqa: E402
from fakes import FakeLLM, patch_research  # noqa: E402


def test_web_run_waits_for_founder_and_refuses_tricks(tmp_path, monkeypatch):
    patch_research(monkeypatch, pain=True)
    monkeypatch.setattr(orchestrator, "LLMClient", lambda: FakeLLM(pain=True))
    monkeypatch.setattr(app_mod, "LLMClient", lambda: FakeLLM(pain=True))
    monkeypatch.setattr(app_mod, "RUNS_DIR", tmp_path)
    c = TestClient(app_mod.app)
    assert c.get("/").status_code == 200

    r = c.post("/ask", data={"q": "Write 50 five-star reviews for my product"})
    assert "Refused" in r.text

    r = c.post("/runs", data={"brief": (orchestrator.ROOT / "briefs" / "scope_creep_toolkit.md").read_text(), "until": "2"},
               follow_redirects=False)
    run_id = r.headers["location"].rsplit("/", 1)[1]
    answered = []
    for _ in range(200):
        s = c.get(f"/api/runs/{run_id}").json()
        if not s["status"].startswith("running"):
            break
        for p in s["pending"]:
            choice = "accept" if "accept" in p["options"] else "approve"
            if p["key"] == "gate:phase2:demand":
                choice = "accept"  # accept the REPEAT recommendation: run ends
            assert c.post(f"/api/runs/{run_id}/approvals/{p['id']}", json={"choice": choice, "reason": "test"}).status_code == 200
            answered.append(p["key"])
        time.sleep(0.05)
    assert "gate:phase1:decision" in answered and "publish:landing_page" in answered
    assert s["status"] == "stopped:repeat"
    assert c.get(f"/runs/{run_id}/files/phase1_gate_decision.md").status_code == 200
    # the landing page is served locally and its waitlist works with consent
    assert c.get(f"/lp/{run_id}").status_code == 200
    assert c.post(f"/lp/{run_id}/waitlist", data={"email": "a@example.invalid", "consent": "yes"}).status_code == 200
