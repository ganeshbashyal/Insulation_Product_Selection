"""Loopback-only API and UI for the isolated internal Neo sales assistant."""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import secrets
import time
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from neo_assistant import NeoAssistant, NeoKnowledge
from neo_store import DEFAULT_DB, NeoStore
from oracle_assistant import installed_models

ROOT = Path(__file__).resolve().parent
COOKIE = "neo_local_session"
SESSION_SECONDS = 8 * 3600
router = APIRouter()
_store: NeoStore | None = None
_assistant: NeoAssistant | None = None


def store() -> NeoStore:
    global _store
    if _store is None:
        _store = NeoStore(DEFAULT_DB)
    return _store


def assistant() -> NeoAssistant:
    global _assistant
    if _assistant is None:
        _assistant = NeoAssistant(NeoKnowledge(ROOT))
    return _assistant


def local_request(request: Request) -> None:
    address = request.client.host if request.client else ""
    try:
        allowed = ipaddress.ip_address(address).is_loopback
    except ValueError:
        allowed = False
    if not allowed or not loopback_hostname(request.url.hostname or ""):
        raise HTTPException(404, "Not found")


def loopback_hostname(hostname: str) -> bool:
    if hostname.casefold() == "localhost":
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


def same_origin(request: Request) -> None:
    origin = request.headers.get("Origin", "")
    try:
        parsed = urlsplit(origin)
    except ValueError:
        raise HTTPException(403, "Same-origin Neo requests are required")
    if (not loopback_hostname(parsed.hostname or "")
            or origin.rstrip("/") != f"{request.url.scheme}://{request.url.netloc}"):
        raise HTTPException(403, "Same-origin Neo requests are required")


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def session(request: Request, *, write: bool = False) -> dict:
    local_request(request)
    current = store().session(token_hash(request.cookies.get(COOKIE, "")))
    if not current:
        raise HTTPException(401, "Start a local Neo session")
    if write:
        same_origin(request)
        if not hmac.compare_digest(request.headers.get("X-Neo-CSRF", ""), current["csrf"]):
            raise HTTPException(403, "Invalid Neo CSRF token")
    return current


def response(data, status_code: int = 200) -> JSONResponse:
    return JSONResponse(data, status_code=status_code, headers={
        "Cache-Control": "no-store", "Referrer-Policy": "no-referrer",
        "X-Content-Type-Options": "nosniff", "X-Frame-Options": "SAMEORIGIN",
    })


class NewConversation(BaseModel):
    model: str = Field(default="", max_length=120)


class Message(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class RecordRequest(BaseModel):
    conversation_id: str = Field(min_length=1, max_length=80)
    record_type: str = Field(pattern=r"^(review_task|sales_brief)$")


@router.get("/neo", response_class=HTMLResponse)
def neo_page(request: Request):
    local_request(request)
    return HTMLResponse((ROOT / "templates" / "neo.html").read_text(encoding="utf-8"),
                        headers={
                            "Cache-Control": "no-store", "Referrer-Policy": "no-referrer",
                            "X-Content-Type-Options": "nosniff", "X-Frame-Options": "SAMEORIGIN",
                            "Content-Security-Policy":
                                "default-src 'self'; script-src 'self' 'unsafe-inline'; "
                                "style-src 'self' 'unsafe-inline'; connect-src 'self'; "
                                "img-src 'self' data:; frame-ancestors 'self'",
                        })


@router.get("/api/neo/session")
def neo_session(request: Request):
    local_request(request)
    current = store().session(token_hash(request.cookies.get(COOKIE, "")))
    if current:
        result = response({"active": True, "csrf": current["csrf"]})
        return result
    token, csrf = secrets.token_urlsafe(40), secrets.token_urlsafe(32)
    store().create_session(token_hash(token), csrf, time.time() + SESSION_SECONDS)
    result = response({"active": True, "csrf": csrf})
    result.set_cookie(COOKIE, token, httponly=True, samesite="strict",
                      secure=request.url.scheme == "https", max_age=SESSION_SECONDS, path="/")
    return result


@router.post("/api/neo/logout")
def neo_logout(request: Request):
    session(request, write=True)
    store().delete_session(token_hash(request.cookies.get(COOKIE, "")))
    result = response({"logged_out": True})
    result.delete_cookie(COOKIE, path="/", httponly=True, samesite="strict",
                         secure=request.url.scheme == "https")
    return result


@router.get("/api/neo/models")
def neo_models(request: Request):
    session(request)
    try:
        models = installed_models()
        return response({"available": True, "models": models, "provider": "local_ollama"})
    except RuntimeError as exc:
        return response({"available": False, "models": [], "provider": "local_ollama",
                         "error": str(exc)})


@router.get("/api/neo/conversations")
def list_conversations(request: Request):
    session(request)
    return response({"conversations": store().conversations()})


@router.post("/api/neo/conversations")
def create_conversation(body: NewConversation, request: Request):
    session(request, write=True)
    if body.model:
        try:
            models = installed_models()
        except RuntimeError as exc:
            raise HTTPException(422, str(exc)) from exc
        if body.model not in models:
            raise HTTPException(422, "Selected model is not installed locally")
    return response({"conversation": store().create_conversation(body.model), "messages": []}, 201)


@router.patch("/api/neo/conversations/{conversation_id}")
def update_conversation(conversation_id: str, body: NewConversation, request: Request):
    session(request, write=True)
    current = store().conversation(conversation_id)
    if not current:
        raise HTTPException(404, "Neo conversation not found")
    if body.model:
        try:
            models = installed_models()
        except RuntimeError as exc:
            raise HTTPException(422, str(exc)) from exc
        if body.model not in models:
            raise HTTPException(422, "Selected model is not installed locally")
    return response({"conversation": store().set_model(conversation_id, body.model)})


@router.get("/api/neo/conversations/{conversation_id}/messages")
def get_messages(conversation_id: str, request: Request):
    session(request)
    if not store().conversation(conversation_id):
        raise HTTPException(404, "Neo conversation not found")
    return response({"conversation": store().conversation(conversation_id),
                     "messages": store().messages(conversation_id)})


@router.post("/api/neo/conversations/{conversation_id}/messages")
def send_message(conversation_id: str, body: Message, request: Request):
    session(request, write=True)
    conversation = store().conversation(conversation_id)
    if not conversation:
        raise HTTPException(404, "Neo conversation not found")
    history = store().messages(conversation_id)
    store().add_message(conversation_id, "user", body.message)
    try:
        answer = assistant().answer(body.message, conversation["model"], history)
    except (OSError, ValueError, RuntimeError) as exc:
        answer = {
            "answer": "I couldn't complete the local product search. No external service was contacted. "
                      f"Local error: {type(exc).__name__}.",
            "citations": [], "model_status": "local_search_error",
        }
    saved = store().add_message(conversation_id, "assistant", answer["answer"], answer["citations"])
    return response({"message": saved, "model_status": answer["model_status"]})


@router.delete("/api/neo/conversations/{conversation_id}")
def delete_conversation(conversation_id: str, request: Request):
    session(request, write=True)
    if not store().delete_conversation(conversation_id):
        raise HTTPException(404, "Neo conversation not found")
    return response({"deleted": True})


@router.post("/api/neo/records")
def save_record(body: RecordRequest, request: Request):
    session(request, write=True)
    conversation = store().conversation(body.conversation_id)
    if not conversation:
        raise HTTPException(404, "Neo conversation not found")
    messages = store().messages(body.conversation_id)
    user_messages = [row["content"].strip() for row in messages if row["role"] == "user"]
    if not user_messages:
        raise HTTPException(422, "Ask Neo a product or customer question first")
    source_refs = []
    for row in messages:
        if row["role"] != "assistant":
            continue
        for citation in row["citations"]:
            if citation.get("source_id") and all(
                    item.get("source_id") != citation["source_id"] for item in source_refs):
                source_refs.append(citation)
    if body.record_type == "review_task":
        title = "Review Neo response: " + user_messages[-1][:120]
        content = "Needs human review. Customer request:\n" + user_messages[-1]
    else:
        title = "Neo sales brief: " + conversation["title"][:120]
        content = ("Internal draft; review before use.\n\nCustomer/sales context:\n"
                   + "\n".join(f"- {text}" for text in user_messages[-20:]))
    if source_refs:
        content += "\n\nLocal references:\n" + "\n".join(
            f"- {item.get('path')} ({item.get('status')})" for item in source_refs
        )
    record = store().save_record(body.record_type, title, content, source_refs)
    return response({"record": record, "production_change": False}, 201)


@router.get("/api/neo/records")
def list_records(request: Request):
    session(request)
    return response({"records": store().records()})


@router.get("/api/neo/sources/{source_id}/open")
def open_source(source_id: str, request: Request):
    session(request)
    try:
        local, source = assistant().knowledge.source_file(source_id) or (None, None)
    except (OSError, ValueError, RuntimeError) as exc:
        raise HTTPException(503, "Local source index unavailable") from exc
    if local is None or source is None:
        raise HTTPException(404, "Neo source is unavailable or has changed")
    media_type = {"pdf": "application/pdf", "json": "application/json; charset=utf-8",
                  "md": "text/markdown; charset=utf-8"}.get(local.suffix.casefold().lstrip("."),
                                                            "application/octet-stream")
    return FileResponse(local, media_type=media_type, filename=local.name,
                        content_disposition_type="inline",
                        headers={"Cache-Control": "no-store",
                                 "X-Content-Type-Options": "nosniff",
                                 "Content-Security-Policy": "sandbox"})
