"""Web UI: paste a founder brief, watch the agents work, approve or reject
every gate and every outbound action.

    uvicorn app:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

import hashlib
import html
import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse

from agents.assistant import AssistantAgent
from agents.base import RunContext
from approval import WebApprover
from decision_log import DecisionLog
from gates import load_thresholds
from llm import LLMClient
from orchestrator import ROOT, Pipeline

app = FastAPI(title="Open Venture Builder")
RUNS: dict[str, dict] = {}
RUNS_DIR = ROOT / "runs"
EXAMPLES = {p.stem: p.read_text(encoding="utf-8") for p in sorted((ROOT / "briefs").glob("*.md"))}

CSS = """
:root{--bg:#f7f7f8;--card:#fff;--ink:#1d1d1f;--muted:#666;--line:#e3e3e6;--accent:#1d4ed8;--warn:#fff4ce;--warnline:#e0c060;--ok:#0a7a3d;--bad:#b42318}
@media (prefers-color-scheme: dark){:root{--bg:#141416;--card:#1d1d20;--ink:#ececee;--muted:#a0a0a8;--line:#333338;--accent:#7aa2ff;--warn:#3a3214;--warnline:#8a7428;--ok:#4ade80;--bad:#f87171}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif}
main{max-width:980px;margin:0 auto;padding:16px}h1{font-size:1.5rem;margin:.3em 0}h2{font-size:1.1rem;margin:1.2em 0 .4em}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px;margin:12px 0}
textarea,input,select{width:100%;padding:8px;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--ink);font:inherit}
textarea{min-height:150px}button{padding:8px 14px;border:0;border-radius:6px;background:var(--accent);color:#fff;font-weight:600;cursor:pointer}
button.secondary{background:var(--muted)}button.bad{background:var(--bad)}.row{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.mock{background:var(--warn);border:1px solid var(--warnline);border-radius:6px;padding:6px 10px;font-size:13px}
pre{white-space:pre-wrap;word-break:break-word;background:var(--bg);padding:10px;border-radius:6px;border:1px solid var(--line);font-size:13px}
.muted{color:var(--muted)}.ok{color:var(--ok)}.bad{color:var(--bad)}table{border-collapse:collapse;width:100%;font-size:13px}
td,th{border-bottom:1px solid var(--line);padding:4px 6px;text-align:left;vertical-align:top}a{color:var(--accent)}
.pill{display:inline-block;padding:1px 8px;border-radius:99px;border:1px solid var(--line);font-size:12px}
"""


def page(title: str, body: str) -> HTMLResponse:
    return HTMLResponse(f"<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' "
                        f"content='width=device-width,initial-scale=1'><title>{html.escape(title)}</title><style>{CSS}</style>"
                        f"</head><body><main>{body}</main></body></html>")


MOCK_TABLE = """<table><tr><th>Part</th><th>Status</th></tr>
<tr><td>Research (Hacker News, Stack Exchange, GitHub)</td><td class='ok'>Working (real public sources)</td></tr>
<tr><td>Agents, scoring, gates, founder approvals, decision log</td><td class='ok'>Working</td></tr>
<tr><td>Customer interviews</td><td>Founder-supplied notes only (never simulated)</td></tr>
<tr><td>Publishing pages and posts</td><td><b>MOCKED</b>: written to a local outbox after approval</td></tr>
<tr><td>Payments, checkout, payouts</td><td><b>MOCKED</b>: in-memory provider, test buyers only</td></tr>
<tr><td>Delivery emails</td><td><b>MOCKED</b>: written to the log, not sent</td></tr></table>"""


@app.get("/", response_class=HTMLResponse)
def home():
    llm = LLMClient()
    status = (f"<span class='ok'>model reachable</span> <code>{html.escape(llm.model)}</code> at <code>{html.escape(llm.base_url)}</code>"
              if llm.ping() else f"<span class='bad'>model not reachable</span> at <code>{html.escape(llm.base_url)}</code> "
                                 "(still downloading? see the terminal)")
    opts = "".join(f"<option value='{html.escape(k)}'>{html.escape(k)}</option>" for k in EXAMPLES)
    runs = "".join(f"<tr><td><a href='/runs/{rid}'>{rid}</a></td><td>{html.escape(r['pipeline'].status)}</td></tr>"
                   for rid, r in sorted(RUNS.items(), reverse=True)) or "<tr><td colspan=2 class='muted'>No runs yet</td></tr>"
    ex_json = json.dumps(EXAMPLES).replace("</", "<\\/")
    body = f"""
<h1>Open Venture Builder</h1>
<p class='muted'>A team of open-source agents that takes a founder brief through Discover, Validate, Build, Commercial setup,
Launch, and Operate, with a gate after every step. It recommends STOP when the evidence is weak. Nothing is published, sent,
spent or signed without your approval.</p>
<p class='mock'>Payments, publishing and delivery emails are <b>MOCKED</b>. No money moves and nothing leaves this machine.</p>
<div class='card'>Model: {status}</div>
<form class='card' method='post' action='/runs'>
  <h2>1. Founder brief</h2>
  <div class='row'><select id='ex' style='max-width:260px'><option value=''>Load an example brief...</option>{opts}</select></div>
  <p><textarea name='brief' id='brief' required placeholder='Idea: ...&#10;Skills: ...&#10;Budget: ...&#10;Time: ...&#10;Target market: ...&#10;Values: ...'></textarea></p>
  <h2>2. Real evidence you already have (optional)</h2>
  <p class='muted'>Interview notes from real conversations, one "## Interview" heading per person. The system never invents interviews.</p>
  <p><textarea name='interviews' style='min-height:80px'></textarea></p>
  <p class='muted'>Real demand numbers as JSON, e.g. {{"landing_page_published": true, "visitors": 340, "signups": 12, "source": "Plausible export"}}</p>
  <p><input name='metrics' placeholder='{{}}'></p>
  <div class='row'><label style='width:auto'>Run until phase</label><select name='until' style='width:auto'>
  {''.join(f"<option {'selected' if i == 6 else ''}>{i}</option>" for i in range(1, 7))}</select>
  <button type='submit'>Start run</button></div>
</form>
<form class='card' method='post' action='/ask'>
  <h2>Ask the team</h2><p class='muted'>Free-form requests. Rule-breaking requests (fake reviews, fake urgency, impersonation...) are refused.</p>
  <p><textarea name='q' style='min-height:60px' required></textarea></p><button>Ask</button>
</form>
<div class='card'><h2>Runs</h2><table>{runs}</table></div>
<div class='card'><h2>What works and what is mocked</h2>{MOCK_TABLE}</div>
<script>const EX={ex_json};document.getElementById('ex').onchange=e=>{{if(EX[e.target.value])document.getElementById('brief').value=EX[e.target.value]}}</script>
"""
    return page("Open Venture Builder", body)


@app.post("/runs")
def start_run(brief: str = Form(...), interviews: str = Form(""), metrics: str = Form(""), until: int = Form(6)):
    try:
        m = json.loads(metrics) if metrics.strip() else None
    except json.JSONDecodeError:
        raise HTTPException(400, "metrics must be JSON")
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:4]
    rdir = RUNS_DIR / run_id
    approver = WebApprover()
    p = Pipeline(brief, approver=approver, out_dir=rdir / "outputs", log_path=rdir / "decision_log.json",
                 interviews=interviews or None, metrics=m, until_phase=until, run_dir=rdir, run_id=run_id)
    t = threading.Thread(target=p.run, daemon=True)
    RUNS[run_id] = {"pipeline": p, "approver": approver, "thread": t}
    t.start()
    return RedirectResponse(f"/runs/{run_id}", status_code=303)


@app.get("/runs/{run_id}", response_class=HTMLResponse)
def run_page(run_id: str):
    if run_id not in RUNS:
        raise HTTPException(404)
    body = f"""<p><a href='/'>&larr; Home</a></p><h1>Run {html.escape(run_id)}</h1>
<p class='mock'>Payments, publishing and delivery emails in this run are <b>MOCKED</b>.</p>
<div class='card'><b>Status:</b> <span id='status'>...</span><br><span class='muted' id='current'></span></div>
<div id='approvals'></div>
<div class='card'><h2>Outputs</h2><ul id='files'></ul></div>
<div class='card'><h2>Gates</h2><table id='gates'></table></div>
<div class='card'><h2>Progress</h2><pre id='events'></pre></div>
<div class='card'><h2>Decision log</h2><p><a href='/api/runs/{run_id}/log'>decision_log.json</a></p></div>
<script>
const rid={json.dumps(run_id)};
function esc(s){{return String(s??'').replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]))}}
async function answer(id,choice){{const reason=document.getElementById('r_'+id).value;
 await fetch('/api/runs/'+rid+'/approvals/'+id,{{method:'POST',headers:{{'Content-Type':'application/json'}},body:JSON.stringify({{choice,reason}})}});tick()}}
let shown='';
async function tick(){{const r=await (await fetch('/api/runs/'+rid)).json();
 document.getElementById('status').textContent=r.status;document.getElementById('current').textContent=r.current;
 document.getElementById('events').textContent=r.events.join('\\n');
 document.getElementById('files').innerHTML=r.files.map(f=>`<li><a target=_blank href='/runs/${{rid}}/files/${{encodeURIComponent(f)}}'>${{esc(f)}}</a></li>`).join('')||'<li class=muted>none yet</li>';
 document.getElementById('gates').innerHTML='<tr><th>Phase</th><th>Gate</th><th>Recommended</th><th>Final</th></tr>'+r.gates.map(g=>`<tr><td>${{g.phase}}</td><td>${{esc(g.gate)}}</td><td><b>${{esc(g.recommendation).toUpperCase()}}</b></td><td>${{esc(g.final).toUpperCase()}}</td></tr>`).join('');
 const key=JSON.stringify(r.pending.map(p=>p.id));
 if(key!==shown){{shown=key;document.getElementById('approvals').innerHTML=r.pending.map(p=>`<div class='card' style='border-color:var(--accent)'>
  <h2>Founder approval needed <span class=pill>${{esc(p.kind)}}</span></h2>
  ${{p.recommendation?`<p>System recommendation: <b>${{esc(p.recommendation).toUpperCase()}}</b></p>`:''}}
  <pre>${{esc(p.summary).slice(0,6000)}}</pre>
  <p><input id='r_${{p.id}}' placeholder='Reason (recorded in the decision log)'></p>
  <div class=row>${{p.options.map(o=>`<button class='${{o==='reject'?'bad':(o==='override_go'?'secondary':'')}}' onclick="answer('${{p.id}}','${{o}}')">${{esc(o.replace('_',' '))}}</button>`).join('')}}</div></div>`).join('')}}
 if(!r.status.startsWith('running'))return; setTimeout(tick,2500)}}
tick();
</script>"""
    return page(f"Run {run_id}", body)


@app.get("/api/runs/{run_id}")
def run_state(run_id: str):
    r = RUNS.get(run_id)
    if not r:
        raise HTTPException(404)
    p = r["pipeline"]
    return {"status": p.status, "current": p.current, "events": p.ctx.events[-200:], "files": p.files,
            "gates": p.gates, "pending": r["approver"].list_pending()}


@app.post("/api/runs/{run_id}/approvals/{req_id}")
def approve(run_id: str, req_id: str, body: dict):
    r = RUNS.get(run_id)
    if not r:
        raise HTTPException(404)
    ok = r["approver"].answer(req_id, str(body.get("choice", "")), str(body.get("reason", ""))[:500])
    if not ok:
        raise HTTPException(400, "unknown request or invalid choice")
    return {"ok": True}


@app.get("/api/runs/{run_id}/log")
def run_log(run_id: str):
    r = RUNS.get(run_id)
    if not r:
        raise HTTPException(404)
    return JSONResponse(r["pipeline"].log.entries())


@app.get("/runs/{run_id}/files/{name}")
def run_file(run_id: str, name: str):
    r = RUNS.get(run_id)
    if not r or "/" in name or ".." in name:
        raise HTTPException(404)
    f = r["pipeline"].out_dir / name
    if not f.exists():
        raise HTTPException(404)
    text = f.read_text(encoding="utf-8")
    if name.endswith(".html"):
        return HTMLResponse(text)
    return PlainTextResponse(text)


@app.get("/lp/{run_id}", response_class=HTMLResponse)
def landing(run_id: str):
    f = RUNS_DIR / Path(run_id).name / "landing.html"
    if not f.exists():
        raise HTTPException(404)
    return HTMLResponse(f.read_text(encoding="utf-8"))


@app.post("/lp/{run_id}/waitlist", response_class=HTMLResponse)
def waitlist(run_id: str, email: str = Form(...), consent: str = Form("")):
    rdir = RUNS_DIR / Path(run_id).name
    if not (rdir / "landing.html").exists():
        raise HTTPException(404)
    if consent != "yes":
        raise HTTPException(400, "consent required")
    f = rdir / "waitlist.json"
    entries = json.loads(f.read_text()) if f.exists() else []
    h = hashlib.sha256(email.strip().lower().encode()).hexdigest()
    if h not in entries:
        entries.append(h)
        f.write_text(json.dumps(entries))
    return page("Thanks", "<h1>Thanks</h1><p>You are on the waitlist. We only store a one-way hash of your email.</p>")


@app.post("/ask", response_class=HTMLResponse)
def ask(q: str = Form(...)):
    rid = "ask-" + datetime.now(timezone.utc).strftime("%Y%m%d")
    ctx = RunContext(run_id=rid, llm=LLMClient(), log=DecisionLog(RUNS_DIR / "ask_log.json", run_id=rid),
                     out_dir=RUNS_DIR, thresholds=load_thresholds())
    res = AssistantAgent(ctx).handle(q)
    cls = "bad" if res["refused"] else "ok"
    body = (f"<p><a href='/'>&larr; Home</a></p><h1>Ask the team</h1><div class='card'><b>You asked:</b><pre>{html.escape(q)}</pre></div>"
            f"<div class='card'><b class='{cls}'>{'Refused' if res['refused'] else 'Draft'}</b><pre>{html.escape(res['text'])}</pre></div>")
    return page("Ask the team", body)


@app.get("/healthz")
def healthz():
    return {"ok": True}
