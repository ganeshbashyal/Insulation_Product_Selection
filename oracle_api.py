"""Owner-only local Oracle routes, isolated from customer and research sessions."""
from __future__ import annotations

import hmac
import ipaddress
import json
import secrets
import uuid
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from oracle_assistant import ENVIRONMENTS, SCOPES, OracleAssistant, OracleKnowledge, installed_models
from oracle_store import DEFAULT_DB, OracleStore

ROOT = Path(__file__).resolve().parent
COOKIE = "oracle_owner_session"
router = APIRouter()
_store_instance: OracleStore | None = None
_assistant_instance: OracleAssistant | None = None


def store() -> OracleStore:
    global _store_instance
    if _store_instance is None:
        _store_instance = OracleStore(DEFAULT_DB)
    return _store_instance


def assistant() -> OracleAssistant:
    global _assistant_instance
    if _assistant_instance is None:
        _assistant_instance = OracleAssistant(OracleKnowledge(ROOT))
    return _assistant_instance


def local_request(request: Request) -> None:
    address = request.client.host if request.client else ""
    try:
        is_local = ipaddress.ip_address(address).is_loopback
    except ValueError:
        is_local = False
    hostname = request.url.hostname or ""
    if not is_local or not _loopback_hostname(hostname):
        raise HTTPException(404, "Not found")


def _loopback_hostname(hostname: str) -> bool:
    if hostname.casefold() == "localhost":
        return True
    try:
        return ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        return False


def same_origin(request: Request) -> None:
    origin = request.headers.get("Origin")
    try:
        parsed = urlsplit(origin or "")
    except ValueError:
        raise HTTPException(403, "Same-origin Oracle requests are required")
    if (not origin or not _loopback_hostname(parsed.hostname or "")
            or origin.rstrip("/") != f"{request.url.scheme}://{request.url.netloc}"):
        raise HTTPException(403, "Same-origin Oracle requests are required")


def owner(request: Request, *, write: bool = False) -> dict:
    local_request(request)
    session = store().session(request.cookies.get(COOKIE, ""))
    if not session:
        raise HTTPException(401, "Unlock Oracle with the dedicated owner passphrase")
    if write:
        same_origin(request)
        if not hmac.compare_digest(request.headers.get("X-Oracle-CSRF", ""), session["csrf"]):
            raise HTTPException(403, "Invalid Oracle CSRF token")
    return session


def response(data, status: int = 200) -> JSONResponse:
    return JSONResponse(data, status_code=status, headers={
        "Cache-Control": "no-store", "Referrer-Policy": "no-referrer",
        "X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY",
    })


class OwnerLogin(BaseModel):
    passphrase: str = Field(min_length=1, max_length=256)


class NewConversation(BaseModel):
    scope: str = "all"
    environment: str = "local"
    model: str = Field(default="", max_length=120)
    context: dict = Field(default_factory=dict)


class Message(BaseModel):
    message: str = Field(min_length=1, max_length=4000)


class BriefRequest(BaseModel):
    conversation_id: str = Field(min_length=1, max_length=80)


class Note(BaseModel):
    note_id: str | None = Field(default=None, max_length=80)
    title: str = Field(min_length=1, max_length=160)
    content: str = Field(min_length=1, max_length=20000)
    source_refs: list[dict] = Field(default_factory=list, max_length=30)


class Task(BaseModel):
    task_id: str | None = Field(default=None, max_length=80)
    title: str = Field(min_length=1, max_length=160)
    details: str = Field(default="", max_length=10000)
    status: str = "open"
    due_date: str | None = Field(default=None, max_length=40)
    source_refs: list[dict] = Field(default_factory=list, max_length=30)


@router.get("/oracle", response_class=HTMLResponse)
def oracle_page(request: Request):
    local_request(request)
    path = ROOT / "templates" / "oracle.html"
    return HTMLResponse(path.read_text(encoding="utf-8"), headers={
        "Cache-Control": "no-store", "Referrer-Policy": "no-referrer",
        "X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY",
        "Content-Security-Policy": "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'; img-src 'self' data:",
    })


@router.get("/api/oracle/session")
def oracle_session(request: Request):
    local_request(request)
    if not store().configured():
        return response({"configured": False, "authenticated": False})
    try:
        session = owner(request)
    except HTTPException as exc:
        if exc.status_code == 401:
            return response({"configured": True, "authenticated": False})
        raise
    return response({"configured": True, "authenticated": True, "csrf": session["csrf"]})


@router.post("/api/oracle/login")
def oracle_login(body: OwnerLogin, request: Request):
    local_request(request)
    same_origin(request)
    if not store().configured():
        raise HTTPException(503, "Oracle owner is not configured; run scripts\\oracle_owner.py locally")
    try:
        session = store().login(body.passphrase, request.client.host if request.client else "")
    except ValueError as exc:
        raise HTTPException(429 if "Too many" in str(exc) else 401, str(exc)) from exc
    result = response({"authenticated": True, "csrf": session["csrf"]})
    result.set_cookie(COOKIE, session["token"], httponly=True, samesite="strict",
                      secure=request.url.scheme == "https", max_age=8 * 3600, path="/")
    return result


@router.post("/api/oracle/logout")
def oracle_logout(request: Request):
    session = owner(request, write=True)
    store().logout(request.cookies.get(COOKIE, ""))
    result = response({"logged_out": True})
    result.delete_cookie(COOKIE, path="/", httponly=True, samesite="strict",
                         secure=request.url.scheme == "https")
    return result


@router.get("/api/oracle/models")
def oracle_models(request: Request):
    owner(request)
    try:
        models = installed_models()
        return response({"available": True, "models": models, "provider": "local_ollama"})
    except RuntimeError as exc:
        return response({"available": False, "models": [], "provider": "local_ollama", "error": str(exc)})


@router.get("/api/oracle/environments")
def oracle_environments(request: Request):
    owner(request)
    return response({"environments": [{"id": "local", "label": "Local / private"}]})


@router.get("/api/oracle/conversations")
def list_conversations(request: Request):
    owner(request)
    return response({"conversations": store().conversations()})


@router.post("/api/oracle/conversations")
def create_conversation(body: NewConversation, request: Request):
    owner(request, write=True)
    if body.scope not in SCOPES:
        raise HTTPException(400, "Unknown Oracle knowledge scope")
    if body.environment not in ENVIRONMENTS:
        raise HTTPException(400, "Only the local/private Oracle environment is enabled")
    if body.model:
        try:
            models = installed_models()
        except RuntimeError as exc:
            raise HTTPException(422, str(exc)) from exc
        if body.model not in models:
            raise HTTPException(422, "Selected model is not installed locally")
    context = {key: value for key, value in body.context.items()
               if key in {"family_id", "product_name", "page_url", "page_title"} and
               isinstance(value, (str, int, float, bool))}
    conversation_id = str(uuid.uuid4())
    conversation = store().create_conversation(conversation_id, body.scope, body.environment, body.model, context)
    return response({"conversation": conversation, "messages": []}, 201)


@router.patch("/api/oracle/conversations/{conversation_id}")
def update_conversation(conversation_id: str, body: NewConversation, request: Request):
    owner(request, write=True)
    current = store().conversation(conversation_id)
    if not current:
        raise HTTPException(404, "Oracle conversation not found")
    if body.scope not in SCOPES or body.environment not in ENVIRONMENTS:
        raise HTTPException(400, "Unsupported Oracle scope or environment")
    if body.model:
        try:
            models = installed_models()
        except RuntimeError as exc:
            raise HTTPException(422, str(exc)) from exc
        if body.model not in models:
            raise HTTPException(422, "Selected model is not installed locally")
    context = {key: value for key, value in body.context.items()
               if key in {"family_id", "product_name", "page_url", "page_title"} and
               isinstance(value, (str, int, float, bool))}
    updated = store().update_conversation(conversation_id, scope=body.scope,
                                          environment=body.environment, model=body.model,
                                          context=context)
    return response({"conversation": updated})


@router.get("/api/oracle/conversations/{conversation_id}/messages")
def get_messages(conversation_id: str, request: Request):
    owner(request)
    try:
        conversation = store().conversation(conversation_id)
        if not conversation:
            raise KeyError("Oracle conversation not found")
        return response({"conversation": conversation, "messages": store().messages(conversation_id)})
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/api/oracle/conversations/{conversation_id}/messages")
def send_message(conversation_id: str, body: Message, request: Request):
    owner(request, write=True)
    conversation = store().conversation(conversation_id)
    if not conversation:
        raise HTTPException(404, "Oracle conversation not found")
    if conversation["environment"] not in ENVIRONMENTS or conversation["scope"] not in SCOPES:
        raise HTTPException(409, "Oracle conversation has an unsupported environment or scope")
    history = store().messages(conversation_id)
    store().add_message(conversation_id, "user", body.message)
    try:
        answer = assistant().answer(
            body.message, scope=conversation["scope"], context=conversation["context"],
            model=conversation["model"], history=history,
        )
    except (OSError, ValueError, RuntimeError) as exc:
        answer = {
            "answer": "I couldn't complete the local knowledge search. No external service was contacted. " +
                      f"Local error: {type(exc).__name__}.",
            "citations": [], "model_status": "local_search_error",
        }
    message = store().add_message(conversation_id, "assistant", answer["answer"], answer["citations"])
    return response({"message": message, "model_status": answer["model_status"]})


@router.delete("/api/oracle/conversations/{conversation_id}")
def clear_conversation(conversation_id: str, request: Request):
    owner(request, write=True)
    if not store().delete_conversation(conversation_id):
        raise HTTPException(404, "Oracle conversation not found")
    return response({"deleted": True, "conversation_id": conversation_id})


@router.post("/api/oracle/briefs/prepare")
def prepare_brief(body: BriefRequest, request: Request):
    owner(request, write=True)
    conversation = store().conversation(body.conversation_id)
    if not conversation:
        raise HTTPException(404, "Oracle conversation not found")
    messages = store().messages(body.conversation_id)
    owner_points = [row["content"].strip() for row in messages
                    if row["role"] == "user" and row["content"].strip()]
    source_refs = []
    for row in messages:
        if row["role"] != "assistant":
            continue
        for citation in row.get("citations", []):
            if citation.get("source_id") and citation["source_id"] not in {
                item.get("source_id") for item in source_refs
            }:
                source_refs.append(citation)
    if not owner_points:
        raise HTTPException(422, "Add owner-provided project or sales context before preparing a brief")
    content = "Owner-provided points (not independently verified):\n" + "\n".join(
        f"- {point}" for point in owner_points[-20:]
    )
    if source_refs:
        content += "\n\nLocal references discussed:\n" + "\n".join(
            f"- {row.get('path')} ({row.get('status')})" for row in source_refs
        )
    else:
        content += "\n\nNo local source citations were attached to this conversation."
    return response({"title": "Oracle brief: " + conversation["title"][:120],
                     "content": content, "source_refs": source_refs,
                     "status": "draft_from_conversation_only"})


@router.get("/api/oracle/sources")
def search_sources(request: Request, q: str = Query(..., min_length=1, max_length=1000),
                   scope: str = Query("all")):
    owner(request)
    try:
        result = assistant().knowledge.retrieve(q, scope, {})
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return response({"scope": result["scope"], "citations": result["citations"],
                     "evidence": result["evidence"], "candidates": result["candidates"]})


@router.get("/api/oracle/sources/{source_id}/open")
def open_source(source_id: str, request: Request):
    owner(request)
    try:
        local, source = assistant().knowledge.source_file(source_id) or (None, None)
    except (OSError, ValueError, RuntimeError) as exc:
        raise HTTPException(503, "Local source index unavailable") from exc
    if local is None or source is None:
        raise HTTPException(404, "Oracle source is unavailable or has changed")
    suffix = local.suffix.casefold()
    media_type = {"pdf": "application/pdf", "json": "application/json; charset=utf-8",
                  "md": "text/markdown; charset=utf-8"}.get(suffix.lstrip("."), "application/octet-stream")
    headers = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
               "Content-Security-Policy": "sandbox", "Referrer-Policy": "no-referrer"}
    return FileResponse(local, media_type=media_type, filename=local.name,
                        content_disposition_type="inline", headers=headers)


@router.get("/api/oracle/notes")
def list_notes(request: Request):
    owner(request)
    return response({"notes": store().notes()})


@router.post("/api/oracle/notes")
def save_note(body: Note, request: Request):
    owner(request, write=True)
    note_id = body.note_id or str(uuid.uuid4())
    return response({"note": store().save_note(note_id, body.title.strip(), body.content,
                                                body.source_refs)}, 201)


@router.delete("/api/oracle/notes/{note_id}")
def delete_note(note_id: str, request: Request):
    owner(request, write=True)
    if not store().delete_note(note_id):
        raise HTTPException(404, "Oracle note not found")
    return response({"deleted": True})


@router.get("/api/oracle/tasks")
def list_tasks(request: Request):
    owner(request)
    return response({"tasks": store().tasks()})


@router.post("/api/oracle/tasks")
def save_task(body: Task, request: Request):
    owner(request, write=True)
    task_id = body.task_id or str(uuid.uuid4())
    try:
        task = store().save_task(task_id, body.title.strip(), body.details,
                                 body.status, body.due_date, body.source_refs)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return response({"task": task}, 201)


@router.delete("/api/oracle/tasks/{task_id}")
def delete_task(task_id: str, request: Request):
    owner(request, write=True)
    if not store().delete_task(task_id):
        raise HTTPException(404, "Oracle task not found")
    return response({"deleted": True})
