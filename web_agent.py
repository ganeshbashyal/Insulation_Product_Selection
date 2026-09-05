"""Deployable website agent: serves the insulation enquiry bot over HTTP.

Self-hosted FastAPI app. Reuses:
  - agent_core for the conversation flow (bot_engine ranking + gating)
  - interaction_store for conversation logging and reviewer outcomes
  - llm_client for optional local-LLM phrasing (safe fallback when offline)

Run locally:
    pip install fastapi uvicorn python-docx
    uvicorn web_agent:app --host 0.0.0.0 --port 8000

Embed on a website with an iframe:
    <iframe src="https://your-server/chat" style="width:420px;height:640px;border:0"></iframe>

Endpoints:
    GET  /chat                     embedded chat UI
    POST /api/conversations        start a conversation -> {conversation_id, reply}
    POST /api/conversations/{id}/messages   send a message -> {reply, done}
    GET  /api/learning/families    per-family recommendation/outcome stats
    GET  /api/learning/pending     conversations awaiting a reviewer outcome
    POST /api/learning/outcomes    record approved/edited/rejected (+ corrected family)
    GET  /api/learning/rejections  recent rejected/edited conversations for tuning
"""
from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

import agent_core
import interaction_store

app = FastAPI(title="Insulation Enquiry Agent", version="1.0.0")

# in-memory conversation state; fine for a single-process deploy, swap for a
# shared store if you scale beyond one process
_SESSIONS: dict[str, agent_core.Conversation] = {}
USE_LLM = os.getenv("AGENT_USE_LLM", "false").casefold() == "true"


class StartResponse(BaseModel):
    conversation_id: str
    reply: str


class MessageRequest(BaseModel):
    message: str
    manufacturer_scope: str | None = None


class MessageResponse(BaseModel):
    reply: str
    done: bool


class OutcomeRequest(BaseModel):
    conversation_id: str
    outcome: str
    reviewer: str
    corrected_family_id: str | None = None
    note: str = ""


CHAT_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Insulation Enquiry</title>
<style>
:root{--teal:#087f7a;--ink:#17232c;--line:#dce3df}
*{box-sizing:border-box}body{margin:0;font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;background:#f6f1e8;color:var(--ink)}
header{background:#102b32;color:#fff;padding:14px 18px}
header h1{font-size:1.05rem;margin:0}
header p{margin:.2rem 0 0;font-size:.78rem;color:#9fc9c4}
#log{height:calc(100vh - 170px);overflow-y:auto;padding:14px;display:flex;flex-direction:column;gap:8px}
.msg{max-width:82%;padding:10px 13px;border-radius:14px;line-height:1.4;font-size:.92rem;white-space:pre-wrap}
.bot{background:#fff;border:1px solid var(--line);border-top-left-radius:4px;align-self:flex-start}
.user{background:var(--teal);color:#fff;border-top-right-radius:4px;align-self:flex-end}
form{display:flex;gap:8px;padding:12px;border-top:1px solid var(--line);background:#fff}
input{flex:1;padding:11px 13px;border:1px solid var(--line);border-radius:10px;font-size:.95rem}
button{padding:11px 18px;border:0;border-radius:10px;background:var(--teal);color:#fff;font-weight:700;cursor:pointer}
</style></head><body>
<header><h1>Insulation Enquiry</h1><p>Evidence-led family recommendation &middot; human review before quoting</p></header>
<div id="log"></div>
<form id="f"><input id="in" autocomplete="off" placeholder="Type your answer&hellip;"><button>Send</button></form>
<script>
let convo=null;
const log=document.getElementById('log');
function add(text,cls){const d=document.createElement('div');d.className='msg '+cls;d.textContent=text;log.appendChild(d);log.scrollTop=log.scrollHeight;}
async function start(){const r=await fetch('/api/conversations',{method:'POST'});const j=await r.json();convo=j.conversation_id;add(j.reply,'bot');}
document.getElementById('f').addEventListener('submit',async e=>{e.preventDefault();const i=document.getElementById('in');const m=i.value.trim();if(!m||!convo)return;i.value='';add(m,'user');
const r=await fetch('/api/conversations/'+convo+'/messages',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({message:m})});const j=await r.json();add(j.reply,'bot');if(j.done){i.placeholder='Enquiry sent for review';}});
start();
</script></body></html>"""


@app.get("/chat", response_class=HTMLResponse)
def chat() -> str:
    return CHAT_HTML


@app.post("/api/conversations", response_model=StartResponse)
def start_conversation() -> StartResponse:
    conversation = agent_core.Conversation()
    _SESSIONS[conversation.conversation_id] = conversation
    opening = agent_core.QUESTIONS[0][1]
    if USE_LLM:
        opening = agent_core._phrase(opening, True)
    return StartResponse(conversation_id=conversation.conversation_id, reply=opening)


@app.post("/api/conversations/{conversation_id}/messages", response_model=MessageResponse)
def send_message(conversation_id: str, body: MessageRequest) -> MessageResponse:
    conversation = _SESSIONS.get(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="conversation not found")
    reply = agent_core.reply(conversation, body.message, use_llm=USE_LLM, manufacturer_scope=body.manufacturer_scope)
    return MessageResponse(reply=reply, done=conversation.done)


@app.get("/api/learning/families")
def learning_families() -> list[dict]:
    return interaction_store.family_stats()


@app.get("/api/learning/pending")
def learning_pending() -> list[dict]:
    return interaction_store.pending_review()


@app.post("/api/learning/outcomes")
def learning_outcome(body: OutcomeRequest) -> dict:
    try:
        interaction_store.record_outcome(
            conversation_id=body.conversation_id,
            outcome=body.outcome,
            reviewer=body.reviewer,
            corrected_family_id=body.corrected_family_id,
            note=body.note,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"status": "recorded"}


@app.get("/api/learning/rejections")
def learning_rejections() -> list[dict]:
    return interaction_store.rejection_report()
