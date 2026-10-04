"""Public, site-scoped chat capability; never grants operator or research access."""
from __future__ import annotations

import hashlib
import secrets
import sqlite3
import time
import threading
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent
TOKEN_SECONDS = 3600


class ChatTokens:
    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.execute("""CREATE TABLE IF NOT EXISTS widget_tokens(
                token_hash TEXT PRIMARY KEY, site_id TEXT NOT NULL,
                session_id TEXT NOT NULL, expires REAL NOT NULL)""")

    def connect(self):
        return sqlite3.connect(self.path, timeout=5)

    def issue(self, site_id: str, session_id: str) -> str:
        token = secrets.token_urlsafe(32)
        with self.connect() as conn:
            conn.execute("DELETE FROM widget_tokens WHERE expires <= ?", (time.time(),))
            conn.execute("INSERT INTO widget_tokens VALUES(?,?,?,?)",
                         (hashlib.sha256(token.encode()).hexdigest(), site_id, session_id,
                          time.time() + TOKEN_SECONDS))
        return token

    def verify(self, token: str, site_id: str, session_id: str) -> bool:
        if not token or len(token) > 200:
            return False
        with self.connect() as conn:
            row = conn.execute("""SELECT 1 FROM widget_tokens
                WHERE token_hash=? AND site_id=? AND session_id=? AND expires>?""",
                (hashlib.sha256(token.encode()).hexdigest(), site_id, session_id, time.time())).fetchone()
        return row is not None


class WidgetMessage(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


def public_origin(value: str) -> str:
    if not isinstance(value,str) or any(char.isspace() for char in value) or any(char in value for char in (";", "'", '"', "\\")):
        raise ValueError("Origin contains invalid characters")
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("A literal HTTP(S) origin is required")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise ValueError("Origin cannot contain a path, query or fragment")
    try:
        parsed.port
    except ValueError as exc:
        raise ValueError("Invalid origin port") from exc
    return f"{parsed.scheme}://{parsed.netloc}"


def build_router(runtime) -> APIRouter:
    """Runtime is the existing web module; imports stay acyclic and initialization lazy."""
    import os

    router = APIRouter()
    tokens = None
    turn_lock = threading.Lock()

    def token_store():
        nonlocal tokens
        if tokens is None:
            base = Path(os.getenv("AURORA_STATE_DIR", str(ROOT / "data" / "local")))
            tokens = ChatTokens(base / "widget_tokens.sqlite3")
        return tokens

    def site(key):
        if key not in runtime.sites:
            raise HTTPException(404, "Unknown storefront")
        return runtime.sites[key]

    def same_origin(request):
        expected = f"{request.url.scheme}://{request.url.netloc}"
        if request.headers.get("Origin", "").rstrip("/") != expected:
            raise HTTPException(403, "Widget requests must originate from the bot frame")

    def rate(request, key):
        if not runtime.auth_middleware.check_rate_limit(key, request.client.host if request.client else "unknown"):
            raise HTTPException(429, "Too many requests")

    @router.get("/widget.js")
    def script():
        return Response((ROOT / "templates" / "widget.js").read_text(encoding="utf-8"),
                        media_type="application/javascript",
                        headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "public, max-age=300"})

    @router.get("/widget")
    def frame(request: Request, site_id: str, parent_origin: str):
        config = site(site_id)
        try:
            parent = public_origin(parent_origin)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        allowed = []
        for origin in config.allowed_origins:
            try:
                allowed.append(public_origin(origin))
            except ValueError as exc:
                raise HTTPException(503, "Storefront needs literal allowed origins") from exc
        if parent not in allowed:
            raise HTTPException(403, "Embedding host is not allowed")
        return HTMLResponse((ROOT / "templates" / "storefront_chat.html").read_text(encoding="utf-8"),
                            headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer",
                                     "X-Content-Type-Options": "nosniff",
                                     "Content-Security-Policy": "frame-ancestors " + " ".join(allowed)})

    @router.post("/api/widget/conversations")
    def start(request: Request, site_id: str):
        import agent_core
        import uuid

        config = site(site_id)
        same_origin(request)
        rate(request, site_id)
        conversation = agent_core.Conversation()
        session_id = str(uuid.uuid4())
        runtime.session_store.create(session_id, site_id, {**conversation.to_dict(), "messages": []})
        token = token_store().issue(site_id, session_id)
        return JSONResponse({"conversation_id": session_id, "token": token,
                             "reply": agent_core.OPENING,
                             "branding": runtime.widget_provider.get_widget_config(site_id)},
                            headers={"Cache-Control": "no-store"})

    @router.post("/api/widget/conversations/{session_id}/messages")
    def message(session_id: str, body: WidgetMessage, request: Request, site_id: str):
        import agent_core
        import json

        site(site_id)
        same_origin(request)
        if not token_store().verify(request.headers.get("X-Chat-Token", ""), site_id, session_id):
            raise HTTPException(401, "Chat session expired or invalid; start a new enquiry")
        rate(request, site_id)
        with turn_lock:
            return process_message(session_id, body.message, site_id)

    def process_message(session_id, message, site_id):
        import agent_core
        import json

        session = runtime.session_store.get(session_id, site_id)
        if session is None:
            raise HTTPException(404, "Chat session not found")
        data = json.loads(session.conversation_json)
        if len(data["messages"]) >= 200:
            raise HTTPException(409, "Conversation limit reached; start a new enquiry")
        conversation = agent_core.Conversation.from_dict(data)
        result = runtime.conversation_service.handle(conversation, message, site_id=site_id)
        runtime.session_store.update(session_id, site_id, {
            **conversation.to_dict(), "messages": data["messages"] + [
                {"role": "user", "content": message}, {"role": "assistant", "content": result.reply}]})
        return JSONResponse({"reply": result.reply, "done": result.done,
                             "human_review_required": result.human_review_required},
                            headers={"Cache-Control": "no-store"})

    return router
