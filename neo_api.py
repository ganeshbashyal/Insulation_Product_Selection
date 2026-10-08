"""Loopback-only API and UI for the isolated internal Neo sales assistant."""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import secrets
import time
from decimal import Decimal
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from neo_pricing import PricingItem as PricingCalculationItem, calculate_pricing
from neo_price_source import (
    AmbiguousPrice,
    PriceNotFound,
    PriceSourceUnavailable,
    lookup_melbourne_price,
)
from neo_assistant import NEO_CONTRACT, NeoAssistant, NeoKnowledge
from neo_store import DEFAULT_DB, NeoStore
from local_model import chat_models as installed_models
from local_operations import resident_models
import matrix_handoff_store

ROOT = Path(__file__).resolve().parent
COOKIE = "neo_local_session"
PERSONA_ID = NEO_CONTRACT.persona_id
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
        _assistant = NeoAssistant(NeoKnowledge(ROOT), contract=NEO_CONTRACT)
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


class HandoffBriefRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model: str = Field(min_length=1, max_length=120)


class PricingItemRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    description: str = Field(default="", max_length=200)
    sku: str = Field(default="", max_length=120)
    quantity: Decimal = Field(ge=Decimal("0"), allow_inf_nan=False)
    unit_type: str = Field(min_length=1, max_length=40)
    buy_price: Decimal = Field(ge=Decimal("0"), allow_inf_nan=False)
    additional_cost: Decimal = Field(default=Decimal("0"), ge=Decimal("0"),
                                     allow_inf_nan=False)
    sell_price: Decimal = Field(ge=Decimal("0"), allow_inf_nan=False)
    discount_percent: Decimal = Field(default=Decimal("0"), ge=Decimal("0"),
                                      le=Decimal("100"), allow_inf_nan=False)
    notes: str = Field(default="", max_length=1000)


class PricingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[PricingItemRequest]
    prices_include_gst: bool = False
    gst_rate: Decimal = Field(default=Decimal("10"), ge=Decimal("0"),
                              le=Decimal("100"), allow_inf_nan=False)
    target_margin_percent: Decimal = Field(default=Decimal("25"), ge=Decimal("0"),
                                            le=Decimal("100"), allow_inf_nan=False)


class PricingLineResponse(BaseModel):
    description: str
    sku: str
    quantity: Decimal
    unit_type: str
    notes: str
    buy_price_ex_gst: Decimal
    additional_cost_ex_gst: Decimal
    sell_price_ex_gst: Decimal
    landed_cost_per_unit: Decimal
    net_sell_price_per_unit: Decimal
    revenue_ex_gst: Decimal
    revenue_inc_gst: Decimal
    total_cost: Decimal
    gross_profit: Decimal
    margin_percent: Decimal
    markup_percent: Decimal
    discount_value_ex_gst: Decimal
    discount_value_inc_gst: Decimal
    margin_status: Literal["negative", "below_target", "acceptable"]


class PricingTotalsResponse(BaseModel):
    product_count: int
    quantities_by_unit: dict[str, Decimal]
    total_revenue_ex_gst: Decimal
    total_revenue_inc_gst: Decimal
    total_cost: Decimal
    total_gross_profit: Decimal
    weighted_margin_percent: Decimal
    total_discount_ex_gst: Decimal
    total_discount_inc_gst: Decimal


class PricingResponse(BaseModel):
    prices_include_gst: bool
    gst_rate: Decimal
    target_margin_percent: Decimal
    lines: list[PricingLineResponse]
    totals: PricingTotalsResponse
    validation_messages: list[str]


class MelbournePriceLookupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    sku: str = Field(min_length=1, max_length=120)
    prices_include_gst: bool = False
    gst_rate: Decimal = Field(default=Decimal("10"), ge=Decimal("0"),
                              le=Decimal("100"), allow_inf_nan=False)


class MelbournePriceLookupResponse(BaseModel):
    sku: str
    description: str
    unit_type: str
    buy_price: Decimal
    sell_price: Decimal
    buy_price_ex_gst: Decimal
    sell_price_ex_gst: Decimal
    prices_include_gst: bool
    gst_rate: Decimal
    effective_date: str | None
    source_file: str
    buy_source_sheet: str
    sell_source_sheet: str
    availability_status: str


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


@router.post("/api/pricing/calculate", response_model=PricingResponse)
def calculate_pricing_endpoint(body: PricingRequest, request: Request):
    session(request, write=True)
    calculation = calculate_pricing(
        [
            PricingCalculationItem(
                description=item.description,
                sku=item.sku,
                quantity=item.quantity,
                unit_type=item.unit_type,
                buy_price=item.buy_price,
                additional_cost=item.additional_cost,
                sell_price=item.sell_price,
                discount_percent=item.discount_percent,
                notes=item.notes,
            )
            for item in body.items
        ],
        prices_include_gst=body.prices_include_gst,
        gst_rate=body.gst_rate,
        target_margin_percent=body.target_margin_percent,
    )
    result = PricingResponse(
        prices_include_gst=calculation.prices_include_gst,
        gst_rate=calculation.gst_rate,
        target_margin_percent=calculation.target_margin_percent,
        lines=[PricingLineResponse(**line.__dict__) for line in calculation.lines],
        totals=PricingTotalsResponse(**calculation.totals.__dict__),
        validation_messages=list(calculation.validation_messages),
    )
    return response(result.model_dump(mode="json"))


@router.post("/api/pricing/melbourne-lookup", response_model=MelbournePriceLookupResponse)
def lookup_melbourne_price_endpoint(body: MelbournePriceLookupRequest, request: Request):
    session(request, write=True)
    try:
        price = lookup_melbourne_price(body.sku)
    except PriceSourceUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    except AmbiguousPrice as exc:
        raise HTTPException(409, str(exc)) from exc
    except PriceNotFound as exc:
        raise HTTPException(404, str(exc)) from exc

    multiplier = Decimal("1") + body.gst_rate / Decimal("100")
    return response(MelbournePriceLookupResponse(
        sku=price.sku,
        description=price.description,
        unit_type=price.unit_type,
        buy_price=price.buy_price_ex_gst * multiplier if body.prices_include_gst
        else price.buy_price_ex_gst,
        sell_price=price.sell_price_ex_gst * multiplier if body.prices_include_gst
        else price.sell_price_ex_gst,
        buy_price_ex_gst=price.buy_price_ex_gst,
        sell_price_ex_gst=price.sell_price_ex_gst,
        prices_include_gst=body.prices_include_gst,
        gst_rate=body.gst_rate,
        effective_date=price.effective_date,
        source_file=price.source_file,
        buy_source_sheet=price.buy_source_sheet,
        sell_source_sheet=price.sell_source_sheet,
        availability_status=price.availability_status,
    ).model_dump(mode="json"))


@router.get("/api/neo/session")
def neo_session(request: Request):
    local_request(request)
    current = store().session(token_hash(request.cookies.get(COOKIE, "")))
    if current:
        result = response({"active": True, "persona_id": PERSONA_ID, "csrf": current["csrf"]})
        return result
    token, csrf = secrets.token_urlsafe(40), secrets.token_urlsafe(32)
    store().create_session(token_hash(token), csrf, time.time() + SESSION_SECONDS)
    result = response({"active": True, "persona_id": PERSONA_ID, "csrf": csrf})
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
    except RuntimeError as exc:
        return response({"available": False, "models": [], "provider": "local_ollama",
                         "error": str(exc)})
    try:
        resident = resident_models()
    except RuntimeError:
        resident = []
    resident_names = [row["name"] for row in resident]
    default_model = next((name for name in resident_names if name in models), "")
    return response({
        "available": True,
        "models": models,
        "resident": resident,
        "default_model": default_model,
        "provider": "local_ollama",
    })


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
            raise HTTPException(422, "Selected model is not installed locally or does not support chat")
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
            raise HTTPException(422, "Selected model is not installed locally or does not support chat")
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
    try:
        answer = assistant().answer(body.message, conversation["model"], history)
    except (OSError, ValueError, RuntimeError) as exc:
        answer = {
            "answer": "I couldn't complete the local product search. No external service was contacted. "
                      f"Local error: {type(exc).__name__}.",
            "citations": [], "model_status": "local_search_error",
        }
    _, saved = store().add_exchange(
        conversation_id, body.message, answer["answer"], answer["citations"],
    )
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


@router.get("/api/neo/aurora-handoffs")
def list_aurora_handoffs(request: Request):
    session(request)
    return response({"handoffs": matrix_handoff_store.store().approved_for_neo()})


@router.post("/api/neo/aurora-handoffs/{handoff_id}/brief")
def prepare_aurora_handoff_brief(handoff_id: str, body: HandoffBriefRequest,
                                 request: Request):
    session(request, write=True)
    handoff = matrix_handoff_store.store().approved_handoff(handoff_id)
    if not handoff:
        raise HTTPException(404, "Aurora sales-review handoff not found")
    try:
        models = installed_models()
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    if body.model not in models:
        raise HTTPException(422, "Select an installed chat-capable local Ollama model")

    query = (
        "Prepare a concise internal sales brief from this explicitly imported structured Aurora sales-review "
        "handoff. Treat every project detail as customer-reported, not independently verified. State unknown "
        "details and escalation flags, use only applicable verified local product evidence, and do not select "
        "or recommend a product or SKU. Do not ask for or infer customer contact details.\n"
        "Structured handoff JSON:\n"
        + json.dumps(handoff["payload"], ensure_ascii=False, sort_keys=True)
    )
    answer = assistant().answer(query, body.model, [])
    conversation = store().create_conversation(body.model)
    conversation_id = conversation["conversation_id"]
    store().add_message(conversation_id, "user", query)
    message = store().add_message(
        conversation_id, "assistant", answer["answer"], answer["citations"],
    )
    record = store().save_record(
        "sales_brief",
        "Neo sales brief: Aurora handoff " + handoff_id[:12],
        "Internal draft; review before use.\n\n" + answer["answer"],
        answer["citations"],
    )
    return response({
        "conversation": conversation,
        "message": message,
        "messages": store().messages(conversation_id),
        "record": record,
        "model_status": answer["model_status"],
    }, 201)


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
