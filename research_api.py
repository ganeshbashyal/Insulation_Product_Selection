"""Protected family-first research APIs; no downloader or arbitrary runner."""
from __future__ import annotations

import hmac
import hashlib
import json
import threading
import uuid
from urllib.parse import urlparse
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse
from pydantic import BaseModel, ConfigDict, Field

from local_source_review import checked_pages
from family_assistant import FamilyAssistantError, apply_changes, answer as family_assistant_answer, build_family_context
from family_assistant_store import FamilyAssistantStore
from product_research import ROOT
from research_store import Conflict, canonical, stamp
from research_workflow import active_effective, effective_evidence, latest_reviews, publication_preview, validate_review
from knowledge_service import service, knowledge_validation
from family_review import (ReviewInventoryError, build_review_inventory, family_review_detail,
                           mapped_group_review_detail, unmapped_review_detail, validate_family_review)

router = APIRouter()
_job_lock = threading.Lock()
COOKIE = "aurora_research_session"
_family_assistant_store: FamilyAssistantStore | None = None


def store():
    return service().store()


def index(refresh=False):
    return service().index(refresh)


def family_assistant_store() -> FamilyAssistantStore:
    global _family_assistant_store
    if _family_assistant_store is None:
        _family_assistant_store = FamilyAssistantStore()
    return _family_assistant_store


def same_origin(request):
    origin = request.headers.get("Origin")
    if not origin or origin.rstrip("/") != f"{request.url.scheme}://{request.url.netloc}":
        raise HTTPException(403, "Same-origin requests are required for research changes")


def user(request: Request, role="reader", write=False):
    account = store().session(request.cookies.get(COOKIE, ""))
    if not account:
        raise HTTPException(401, "Sign in with a named local research account")
    if role not in account["roles"]:
        raise HTTPException(403, f"{role} permission required")
    if write:
        same_origin(request)
        if not hmac.compare_digest(request.headers.get("X-Research-CSRF", ""), account["csrf"]):
            raise HTTPException(403, "Invalid research CSRF token")
    return account


def response(data, status=200):
    return JSONResponse(data, status_code=status, headers={"Cache-Control": "no-store"})


class Login(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class Change(BaseModel):
    expected_version: int = Field(default=0, ge=0)
    data: dict


class FamilyManagerConversationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    family_id: str = Field(min_length=1, max_length=100)
    model: str = Field(min_length=1, max_length=120)


class FamilyManagerMessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=4000)


class FamilyManagerApprovalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=0)


@router.get("/admin/products")
def page():
    return HTMLResponse((ROOT / "templates" / "product_research.html").read_text(encoding="utf-8"),
                        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})


@router.get("/admin/knowledge")
def knowledge_page():
    return HTMLResponse((ROOT / "templates" / "knowledge_validation.html").read_text(encoding="utf-8"),
                        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})


@router.get("/admin/family-manager")
def family_manager_page():
    return HTMLResponse(
        (ROOT / "templates" / "family_assistant.html").read_text(encoding="utf-8"),
        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer",
                 "X-Content-Type-Options": "nosniff",
                 "Content-Security-Policy":
                     "default-src 'self'; script-src 'self' 'unsafe-inline'; "
                     "style-src 'self' 'unsafe-inline'; connect-src 'self'; "
                     "img-src 'self' data:; frame-ancestors 'self'"},
    )


@router.get("/admin/competitors")
def competitor_page():
    return HTMLResponse((ROOT / "templates" / "competitor_research.html").read_text(encoding="utf-8"),
                        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})


@router.get("/admin/catalogue")
def catalogue_page():
    return HTMLResponse((ROOT / "templates" / "catalogue_versions.html").read_text(encoding="utf-8"),
                        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})


def competitor_report():
    from competitor_research import comparison
    try:
        idx = index()
        result = comparison(idx.root, idx)
        evidence, publication = effective_evidence(idx, store())
        for row in result["competitors"]:
            row["our_reviewed_claims"] = [claim for claim in evidence.get(row["our_family_id"], [])
                                        if claim["evidence_status"] == "verified"]
            row["publication_state"] = publication["state"]
            pairs = []
            for candidate in row["claims"]:
                for ours in row["our_reviewed_claims"]:
                    if candidate["metric"] != ours["metric_type"]:
                        continue
                    fields = ("unit", "variant", "scope", "test_standard", "test_context")
                    mismatches = [key for key in fields if candidate[key] != ours[key]]
                    pairs.append({"metric": candidate["metric"], "our_evidence_id": ours["evidence_id"],
                                  "competitor_citation": candidate["citation"],
                                  "status": "not_equivalent" if mismatches else "matching_fields_still_requires_human_review",
                                  "mismatched_fields": mismatches, "winner": None})
            row["comparisons"] = pairs
            row["evidence_hash"] = hashlib.sha256(canonical(row).encode()).hexdigest()
            history = [item for item in store().history("competitor:" + row["competitor_id"])
                       if item["kind"] == "competitor_review"]
            row["review_version"] = history[-1]["id"] if history else 0
            row["review_history"] = history
            row["review"] = history[-1]["payload"] if history else None
            row["review_state"] = "pending_human_review"
            if history:
                latest = history[-1]
                with store().connection() as conn:
                    reviewer = conn.execute("SELECT roles,disabled FROM users WHERE username=?",
                                            (latest["actor"],)).fetchone()
                enabled = reviewer and not reviewer["disabled"] and "reviewer" in json.loads(reviewer["roles"])
                row["review_state"] = ("reviewer_disabled" if not enabled else
                                       "stale_evidence" if latest["payload"]["evidence_hash"] != row["evidence_hash"]
                                       else latest["payload"]["decision"])
        return result
    except (OSError, ValueError, KeyError) as exc:
        raise HTTPException(422, "Local competitor data invalid: " + str(exc)) from exc


@router.get("/api/research/competitors")
def competitors(request: Request):
    user(request)
    return response(competitor_report())


@router.post("/api/research/competitors/{competitor_id}/reviews")
def competitor_review(competitor_id: str, body: Change, request: Request):
    account = user(request, "reviewer", write=True)
    row = next((row for row in competitor_report()["competitors"]
                if row["competitor_id"] == competitor_id), None)
    if row is None:
        raise HTTPException(404, "Unknown competitor identity")
    data = body.data
    if set(data) != {"decision", "notes", "evidence_hash"} or not isinstance(data["decision"], str) or data["decision"] not in {
            "comparable", "not_comparable", "needs_information"}:
        raise HTTPException(422, "Explicit comparison decision, notes and current evidence hash required")
    if not isinstance(data["notes"], str) or not 10 <= len(data["notes"].strip()) <= 20000:
        raise HTTPException(422, "Meaningful comparison notes of 10 to 20000 characters required")
    if data["evidence_hash"] != row["evidence_hash"]:
        raise HTTPException(409, "Comparison sources changed; refresh and review again")
    if data["decision"] == "comparable" and (
            not row["claims"] or any(claim["status"] != "cited_text_not_human_approval" or
                                    not any(pair["metric"] == claim["metric"] and
                                            pair["competitor_citation"] == claim["citation"] and
                                            pair["status"] == "matching_fields_still_requires_human_review"
                                            for pair in row["comparisons"])
                                    for claim in row["claims"])):
        raise HTTPException(422, "Comparable requires current citations and matching reviewed metric/variant/test fields")
    try:
        revision = store().save_revision("competitor:" + competitor_id, "competitor_review",
                                         {**data, "reviewed_at": stamp(), "public_use": False,
                                          "automatic_winner": False}, account["username"], body.expected_version)
        return response({"revision": revision, "runtime_changed": False, "public_use": False})
    except Conflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/api/research/competitors/export")
def competitor_export(request: Request, format: Literal["json", "text"] = "json"):
    user(request)
    report = competitor_report()
    if format == "text":
        lines = ["PRIVATE COMPETITOR COMPARISON", "No public approval, automatic winner or SKU eligibility.", ""]
        for row in report["competitors"]:
            lines.extend([f"{row['name']} [{row['competitor_id']}] / our family {row['our_family_id']}",
                          "Review: " + row["review_state"],
                          "Notes: " + (row["review"]["notes"] if row["review"] else "Not reviewed"),
                          "Competitor scoped claims and local citations:"])
            lines.extend(canonical(claim) for claim in row["claims"])
            lines.append("Current reviewed claims for our family:")
            lines.extend(canonical(claim) for claim in row["our_reviewed_claims"])
            lines.append("Field equivalence / remaining gaps:")
            lines.extend(canonical(pair) for pair in row["comparisons"])
            lines.append("")
        lines.extend(report["errors"])
        return PlainTextResponse("\n".join(lines), headers={"Cache-Control": "no-store",
                                 "Content-Disposition": 'attachment; filename="competitor-comparison.txt"'})
    return JSONResponse(report, headers={"Cache-Control": "no-store",
                        "Content-Disposition": 'attachment; filename="competitor-comparison.json"'})


@router.get("/api/research/knowledge")
def knowledge_status(request: Request, q: str = Query("", max_length=200),
                     manufacturer: str = "", gap: str = "",
                     offset: int = Query(0, ge=0), limit: int = Query(30, ge=1, le=100)):
    user(request)
    report = knowledge_validation(index(), store())
    rows = report.pop("families")
    rows = [r for r in rows if (not manufacturer or r["manufacturer"] == manufacturer)
            and q.casefold() in canonical([r["family_id"], r["name"], r["manufacturer"]]).casefold()
            and (not gap or any(gap.casefold() in text.casefold() for text in r["gaps"]))]
    return response({**report, "total": len(rows), "offset": offset, "limit": limit,
                     "families": rows[offset:offset + limit]})


@router.get("/api/research/family-review")
def family_review_worklist(request: Request, lane: str = Query("families", pattern="^(families|mapped|unmapped)$"),
                           q: str = Query("", max_length=200), offset: int = Query(0, ge=0),
                           limit: int = Query(30, ge=1, le=100)):
    user(request)
    idx = index()
    try:
        worklist = build_review_inventory(idx.root, idx, store())
    except (OSError, ReviewInventoryError) as exc:
        return response({"state": "unavailable", "error": str(exc),
                         "note": "No review decisions can be saved until the V3 inventory and triage agree."}, 422)
    rows = {
        "families": worklist["families"],
        "mapped": worklist["mapped_exception_groups"],
        "unmapped": worklist["unmapped_groups"],
    }[lane]
    if q:
        needle = q.casefold()
        rows = [row for row in rows if needle in canonical(row).casefold()]
    return response({
        **{key: value for key, value in worklist.items()
           if key not in {"families", "mapped_exception_groups", "unmapped_groups"}},
        "lane": lane, "total": len(rows), "offset": offset, "limit": limit,
        "items": rows[offset:offset + limit],
    })


@router.get("/api/research/family-manager/models")
def family_manager_models(request: Request):
    user(request, "reviewer")
    from local_model import chat_models
    try:
        return response({"available": True, "provider": "local_ollama",
                         "models": chat_models()})
    except RuntimeError as exc:
        return response({"available": False, "provider": "local_ollama",
                         "models": [], "error": str(exc)})


@router.get("/api/research/family-manager/families")
def family_manager_families(request: Request, q: str = Query("", max_length=200)):
    user(request, "reviewer")
    rows = []
    for family in index().families.values():
        item = {key: family.get(key, "") for key in
                ("family_id", "name", "manufacturer", "category")}
        if not q or q.casefold() in canonical(item).casefold():
            rows.append(item)
    rows.sort(key=lambda row: (row["manufacturer"].casefold(), row["name"].casefold(),
                               row["family_id"]))
    return response({"families": rows, "total": len(rows)})


def family_manager_context(family_id: str):
    idx = index(refresh=True)
    if family_id not in idx.families:
        raise HTTPException(404, "Unknown family")
    try:
        detail = service().family(family_id)
    except (OSError, ValueError, KeyError) as exc:
        raise HTTPException(409, "Current local family knowledge could not be read") from exc
    authoring = family_assistant_store().authoring_copy(family_id)
    context = build_family_context(detail, family_id, authoring)
    return context, authoring


def family_manager_public_proposal(proposal: dict, context: dict | None) -> dict:
    return {
        key: proposal[key] for key in (
            "proposal_id", "family_id", "title", "summary", "source_signature",
            "base_revision", "changes", "status", "created_at", "applied_revision",
        ) if key in proposal
    } | {
        "stale": proposal["status"] == "draft" and (
            context is None
            or proposal["source_signature"] != context["source_signature"]
            or proposal["base_revision"] != context["authoring_copy"]["revision"]
        ),
    }


@router.get("/api/research/family-manager/families/{family_id}")
def family_manager_family(family_id: str, request: Request):
    user(request, "reviewer")
    context, authoring = family_manager_context(family_id)
    return response({
        **context,
        "authoring_copy": {
            "revision": authoring["revision"],
            "snapshot": context["authoring_copy"]["snapshot"],
            "saved": context["authoring_copy"]["saved"],
            "source_signature": authoring["source_signature"],
            "source_is_current": (not authoring["source_signature"]
                                  or authoring["source_signature"] == context["source_signature"]),
        },
    })


@router.get("/api/research/family-manager/conversations")
def family_manager_conversations(request: Request, family_id: str | None = None):
    account = user(request, "reviewer")
    if family_id and family_id not in index().families:
        raise HTTPException(404, "Unknown family")
    return response({"conversations": family_assistant_store().conversations(
        account["username"], family_id=family_id,
    )})


@router.post("/api/research/family-manager/conversations", status_code=201)
def family_manager_create_conversation(body: FamilyManagerConversationRequest,
                                       request: Request):
    account = user(request, "reviewer", write=True)
    if body.family_id not in index().families:
        raise HTTPException(404, "Unknown family")
    from local_model import chat_models
    try:
        models = chat_models()
    except RuntimeError as exc:
        raise HTTPException(503, str(exc)) from exc
    if body.model not in models:
        raise HTTPException(422, "Select an installed chat-capable local Ollama model")
    conversation = family_assistant_store().create_conversation(
        str(uuid.uuid4()), account["username"], body.family_id, body.model,
    )
    return response({"conversation": conversation, "messages": []}, 201)


@router.get("/api/research/family-manager/conversations/{conversation_id}/messages")
def family_manager_messages(conversation_id: str, request: Request):
    account = user(request, "reviewer")
    conversation = family_assistant_store().conversation(conversation_id, account["username"])
    if not conversation:
        raise HTTPException(404, "Family conversation not found")
    try:
        messages = family_assistant_store().messages(conversation_id, account["username"])
        proposals = family_assistant_store().proposals(conversation_id, account["username"])
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    try:
        context, _ = family_manager_context(conversation["family_id"])
    except HTTPException as exc:
        if exc.status_code not in {404, 409}:
            raise
        context = None
    return response({"conversation": conversation, "messages": messages,
                     "proposals": [
                         family_manager_public_proposal(proposal, context)
                         for proposal in proposals
                     ]})


@router.post("/api/research/family-manager/conversations/{conversation_id}/messages")
def family_manager_send_message(conversation_id: str, body: FamilyManagerMessageRequest,
                                request: Request):
    account = user(request, "reviewer", write=True)
    manager = family_assistant_store()
    conversation = manager.conversation(conversation_id, account["username"])
    if not conversation:
        raise HTTPException(404, "Family conversation not found")
    context, authoring = family_manager_context(conversation["family_id"])
    history = manager.messages(conversation_id, account["username"])
    manager.add_message(conversation_id, account["username"], "user", body.message)
    try:
        result = family_assistant_answer(
            body.message, context=context,
            baseline=context["authoring_copy"]["snapshot"],
            model=conversation["model"], history=history,
        )
    except RuntimeError as exc:
        raise HTTPException(503, f"Local model unavailable: {exc}") from exc
    except FamilyAssistantError as exc:
        raise HTTPException(502, str(exc)) from exc

    proposal = None
    proposal_id = None
    if result["proposal"]:
        proposed = result["proposal"]
        proposal_id = proposed["proposal_id"]
        try:
            proposal = manager.create_proposal(
                proposal_id=proposal_id, conversation_id=conversation_id,
                actor=account["username"], family_id=conversation["family_id"],
                title=proposed["title"], summary=proposed["summary"],
                source_signature=context["source_signature"],
                base_revision=authoring["revision"],
                baseline=context["authoring_copy"]["snapshot"],
                changes=proposed["changes"],
            )
        except KeyError as exc:
            raise HTTPException(404, "Family conversation not found") from exc
    message = manager.add_message(
        conversation_id, account["username"], "assistant", result["reply"],
        result["citations"], proposal_id,
    )
    return response({"message": message,
                     "proposal": (family_manager_public_proposal(proposal, context)
                                  if proposal else None),
                     "model_status": "local_model"})


@router.delete("/api/research/family-manager/conversations/{conversation_id}")
def family_manager_delete_conversation(conversation_id: str, request: Request):
    account = user(request, "reviewer", write=True)
    if not family_assistant_store().delete_conversation(conversation_id, account["username"]):
        raise HTTPException(404, "Family conversation not found")
    return response({"deleted": True})


@router.delete("/api/research/family-manager/proposals/{proposal_id}")
def family_manager_delete_proposal(proposal_id: str, request: Request):
    account = user(request, "reviewer", write=True)
    if not family_assistant_store().delete_proposal(proposal_id, account["username"]):
        raise HTTPException(404, "Draft proposal not found")
    return response({"deleted": True})


@router.post("/api/research/family-manager/proposals/{proposal_id}/approve")
def family_manager_approve_proposal(proposal_id: str,
                                    body: FamilyManagerApprovalRequest,
                                    request: Request):
    account = user(request, "reviewer", write=True)
    manager = family_assistant_store()
    proposal = manager.proposal(proposal_id, account["username"])
    if not proposal:
        raise HTTPException(404, "Family proposal not found")
    context, _ = family_manager_context(proposal["family_id"])
    try:
        snapshot = apply_changes(proposal["baseline"], proposal["changes"],
                                 proposal["family_id"])
        revision = manager.apply_proposal(
            proposal_id, account["username"],
            source_signature=context["source_signature"],
            expected_revision=body.expected_revision,
            snapshot=snapshot,
        )
    except KeyError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    return response({
        "saved": True,
        "family_id": revision["family_id"],
        "revision": revision["revision"],
        "created_at": revision["created_at"],
        "storage": "private local Family Knowledge Manager database",
        "canonical_knowledge_changed": False,
        "deployment_changed": False,
    })


@router.get("/api/research/transcription-audit")
def transcription_audit_worklist(request: Request, q: str = Query("", max_length=200),
                                 offset: int = Query(0, ge=0),
                                 limit: int = Query(30, ge=1, le=100)):
    user(request)
    from scripts.check_family_transcription import read_current_report
    try:
        report = read_current_report(ROOT)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(409, str(exc)) from exc
    rows = report["families"]
    if q:
        needle = q.casefold()
        rows = [row for row in rows if needle in canonical([
            row["family_id"], row["family_name"], row["manufacturer"], row["flags"], row["status"]
        ]).casefold()]
    return response({
        **{key: value for key, value in report.items() if key != "families"},
        "total": len(rows), "offset": offset, "limit": limit,
        "items": [{key: value for key, value in row.items() if key != "facts"}
                  for row in rows[offset:offset + limit]],
    })


@router.get("/api/research/transcription-audit/family/{family_id}")
def transcription_audit_family(family_id: str, request: Request):
    user(request)
    from scripts.check_family_transcription import read_current_report
    try:
        report = read_current_report(ROOT)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(409, str(exc)) from exc
    row = next((item for item in report["families"] if item["family_id"] == family_id), None)
    if row is None:
        raise HTTPException(404, "Unknown family")
    documents = {
        (item.get("path"), item.get("sha256")): item.get("id")
        for item in index().documents.values()
    }
    result = {**row}
    for fact in result["facts"]:
        for match in fact["exact_hash_bound_pdf_matches"]:
            match["document_id"] = documents.get((match["path"], match["sha256"]))
    result["review_boundary"] = (
        "Exact page text matches are provisional internal transcription checks only. "
        "They do not validate source authenticity, currentness, applicability, technical suitability, "
        "compliance, customer claims, or publication."
    )
    return response(result)


@router.get("/api/research/family-review/family/{family_id}")
def family_review_card(family_id: str, request: Request):
    user(request)
    idx = index()
    try:
        return response(family_review_detail(idx.root, idx, store(), family_id))
    except (OSError, ReviewInventoryError) as exc:
        raise HTTPException(422, "V3 review inventory is unavailable: " + str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/api/research/family-review/unmapped/{group_id}")
def unmapped_review_card(group_id: str, request: Request):
    user(request)
    idx = index()
    try:
        return response(unmapped_review_detail(idx.root, idx, store(), group_id))
    except (OSError, ReviewInventoryError) as exc:
        raise HTTPException(422, "V3 review inventory is unavailable: " + str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/api/research/family-review/mapped/{group_id}")
def mapped_review_card(group_id: str, request: Request):
    user(request)
    idx = index()
    try:
        return response(mapped_group_review_detail(idx.root, idx, store(), group_id))
    except (OSError, ReviewInventoryError) as exc:
        raise HTTPException(422, "V3 review inventory is unavailable: " + str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/api/research/family-review/{scope}/{scope_id}")
def save_family_validation(scope: str, scope_id: str, body: Change, request: Request):
    account = user(request, "reviewer", write=True)
    idx = index()
    try:
        result = validate_family_review(idx.root, idx, store(), scope, scope_id,
                                        body.data, account["username"], body.expected_version)
        return response(result)
    except Conflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except ReviewInventoryError as exc:
        raise HTTPException(422, "V3 review inventory is unavailable: " + str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/api/research/login")
def login(body: Login, request: Request):
    same_origin(request)
    try:
        account = store().login(body.username, body.password, request.client.host if request.client else "unknown")
    except ValueError as exc:
        raise HTTPException(429 if "Too many" in str(exc) else 401, str(exc)) from exc
    result = response({key: value for key, value in account.items() if key != "token"})
    result.set_cookie(COOKIE, account["token"], httponly=True, samesite="strict",
                      secure=request.url.scheme == "https", max_age=8 * 3600, path="/")
    return result


@router.get("/api/research/me")
def me(request: Request):
    return response(user(request))


@router.post("/api/research/logout")
def logout(request: Request):
    user(request, write=True)
    store().logout(request.cookies.get(COOKIE, ""))
    result = response({"status": "signed_out"})
    result.delete_cookie(COOKIE, path="/")
    return result


@router.get("/api/research/overview")
def overview(request: Request):
    user(request)
    return response({**index().overview(), "publication": active_effective(index(), store())["state"]})


@router.post("/api/research/refresh")
def refresh(request: Request):
    user(request, write=True)
    return response({**index(refresh=True).overview(), "message": "Existing files refreshed; no script started or file changed"})


@router.get("/api/research/families")
def browse(request: Request, q: str = Query("", max_length=200), manufacturer: str = "",
           category: str = "", status: str = "", offset: int = Query(0, ge=0),
           limit: int = Query(30, ge=1, le=100)):
    user(request)
    idx = index()
    rows = idx.browse(q, manufacturer, category, "", 0, len(idx.families))["families"]
    reviews = list(latest_reviews(store()).values())
    published = active_effective(idx, store())
    result = []
    for row in rows:
        key = row["family_id"]
        states = list(row["states"])
        decisions = [r["payload"] for r in reviews if r["payload"]["family_id"] == key]
        states.append("reviewed_draft" if any(r["decision"] == "approved" for r in decisions) else "pending_human_review")
        if any(r["family_id"] == key for r in published["claims"]):
            states.append("published")
        if any(r["family_id"] == key and r["eligible"] for r in published["eligibility"].values()):
            states.append("eligible")
        if not status or status in states:
            result.append({**row, "states": states})
    return response({"total": len(result), "offset": offset, "limit": limit, "families": result[offset:offset + limit]})


def family_detail(key):
    return service().family(key)


@router.post("/api/research/source-preview")
def source_preview(body: Change, request: Request):
    user(request, "reviewer", write=True)
    value = body.data.get("manifest")
    if not isinstance(value, str):
        raise HTTPException(400, "Explicit local manifest path required")
    try:
        return response(service().source_preview(service().root / value))
    except (OSError, ValueError, KeyError) as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/api/research/source-stage")
def source_stage(body: Change, request: Request):
    user(request, "reviewer", write=True)
    value, confirmation = body.data.get("manifest"), body.data.get("confirmation")
    if not isinstance(value, str) or not isinstance(confirmation, str):
        raise HTTPException(400, "Local manifest and exact preview confirmation required")
    try:
        return response(service().source_stage(service().root / value, confirmation))
    except (OSError, ValueError, KeyError) as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/api/research/catalogue")
def catalogue_overview(request: Request):
    user(request)
    try:
        return response(service().catalogue_overview())
    except (OSError, ValueError, KeyError) as exc:
        raise HTTPException(422, "Local catalogue data invalid: " + str(exc)) from exc


@router.post("/api/research/catalogue/preview")
def catalogue_preview(body: Change, request: Request):
    user(request, "reviewer", write=True)
    source, mapping, sheet = body.data.get("source"), body.data.get("mapping"), body.data.get("sheet")
    if not isinstance(source, str) or not isinstance(mapping, dict):
        raise HTTPException(400, "Local source path and explicit column mapping required")
    if sheet is not None and not isinstance(sheet, str):
        raise HTTPException(400, "Worksheet name must be a string when provided")
    try:
        return response(service().catalogue_preview(service().root / source, mapping, sheet))
    except (OSError, ValueError, KeyError) as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/api/research/catalogue/stage")
def catalogue_stage(body: Change, request: Request):
    user(request, "reviewer", write=True)
    data = body.data.get("preview")
    if not isinstance(data, dict) or "version_id" not in data or "payload" not in data:
        raise HTTPException(400, "Unmodified preview result required to stage a catalogue version")
    try:
        return response(service().catalogue_stage(data))
    except (OSError, ValueError, KeyError) as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/api/research/catalogue/activate")
def catalogue_activate(body: Change, request: Request):
    user(request, "publisher", write=True)
    version_id, confirm = body.data.get("version_id"), body.data.get("confirm")
    if "expected_active_id" not in body.data:
        raise HTTPException(400, "Expected active version must be provided; refresh the catalogue first")
    expected = body.data.get("expected_active_id")
    if not isinstance(version_id, str) or not isinstance(confirm, str):
        raise HTTPException(400, "Exact catalogue version ID and typed confirmation required")
    if expected is not None and not isinstance(expected, str):
        raise HTTPException(400, "Expected active version must be a string or null")
    try:
        return response(service().catalogue_activate(version_id, confirm, expected))
    except Conflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except (OSError, ValueError, KeyError) as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/api/research/families/{family_id}/retained-review")
def retained_review(family_id: str, body: Change, request: Request):
    account = user(request, "reviewer", write=True)
    try:
        return response(service().review_retained(family_id, body.data, account["username"], body.expected_version))
    except Conflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except (ValueError, KeyError) as exc:
        raise HTTPException(400, str(exc)) from exc

@router.get("/api/research/families/{family_id}")
def detail(family_id: str, request: Request):
    user(request)
    try:
        return response(family_detail(family_id))
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/api/research/families/{family_id}/source-review")
def source_identity_review(family_id: str, body: Change, request: Request):
    account = user(request, "reviewer", write=True)
    try:
        return response(service().review_source_identity(
            family_id, body.data, account["username"], body.expected_version))
    except Conflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except (ValueError, KeyError) as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/api/research/families/{family_id}/draft-pack")
def draft_pack(family_id: str, request: Request):
    user(request)
    try:
        return response(service().draft_family(family_id))
    except (ValueError, OSError) as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/api/research/compare")
def compare(request: Request, ids: str = Query(max_length=1000)):
    user(request)
    keys = list(dict.fromkeys(ids.split(",")))
    if not 2 <= len(keys) <= 4:
        raise HTTPException(400, "Choose 2-4 distinct families")
    try:
        return response({"families": [family_detail(key) for key in keys], "note": "Source-scoped comparison, not a suitability recommendation"})
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.get("/api/research/documents")
def documents(request: Request):
    user(request)
    return response({"documents": list(index().documents.values()), "note": "Library documents may be unlinked; choosing one does not prove family applicability"})


@router.get("/api/research/documents/{identifier}/file")
def document_file(identifier: str, request: Request):
    user(request)
    try:
        path, doc = index().document(identifier)
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    return FileResponse(path, media_type="application/pdf", filename=path.name, content_disposition_type="inline",
                        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff",
                                 "Content-Security-Policy": "sandbox", "Referrer-Policy": "no-referrer"})


@router.get("/api/research/documents/{identifier}/pages")
def pages(identifier: str, request: Request, page: int = Query(1, ge=1)):
    user(request)
    try:
        path, doc = index().document(identifier)
        extraction = checked_pages(path, doc["sha256"])
        if extraction["status"] == "read_error":
            return response({**doc, **extraction}, 422)
        if page > len(extraction["pages"]):
            raise HTTPException(404, "Page not found")
        return response({**doc, "page_count": extraction["page_count"], "status": extraction["status"],
                         "page": extraction["pages"][page - 1], "review_status": "pending_human_review"})
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc


@router.post("/api/research/families/{family_id}/notes")
def notes(family_id: str, body: Change, request: Request):
    account = user(request, "reviewer", write=True)
    if family_id not in index().families:
        raise HTTPException(404, "Unknown family")
    text = body.data.get("text", "")
    if not isinstance(text, str) or not 1 <= len(text.strip()) <= 10000:
        raise HTTPException(400, "Notes must contain 1-10000 characters")
    try:
        revision = store().save_revision("family:" + family_id, "note", {"text": text, "family_id": family_id},
                                         account["username"], body.expected_version)
        return response({"revision": revision})
    except Conflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/api/research/families/{family_id}/reviews")
def review(family_id: str, body: Change, request: Request):
    account = user(request, "reviewer", write=True)
    if len(canonical(body.data)) > 100000:
        raise HTTPException(400, "Review payload is too large")
    try:
        return response(service().review_claim_or_sku(family_id, body.data, account["username"], body.expected_version))
    except Conflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/api/research/publication/preview")
def preview(request: Request, scoped: bool = Query(False)):
    account = user(request, "publisher", write=True)
    try:
        return response(service().publication_preview(account["username"], scoped=scoped))
    except Conflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.post("/api/research/publication/{proposal_id}/publish")
def publish(proposal_id: int, request: Request):
    account = user(request, "publisher", write=True)
    # Rebuild source baselines immediately before transactional activation.
    try:
        return response(service().publish(proposal_id, account["username"]))
    except Conflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc


@router.get("/api/research/audit")
def audit(request: Request, limit: int = Query(100, ge=1, le=500)):
    user(request, "publisher")
    with store().connection() as conn:
        records = conn.execute("SELECT id,occurred,actor,kind,target,payload FROM events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return response([{**dict(row), "payload": json.loads(row["payload"])} for row in records])


@router.post("/api/research/families/{family_id}/local-audit")
def local_audit(family_id: str, request: Request):
    account = user(request, "reviewer", write=True)
    idx = index()
    record = idx.sources.research.get(family_id)
    if not record or not record.get("_path"):
        raise HTTPException(400, "No existing research record to audit")
    # Validate paths before reusing the existing local-only audit helper.
    idx.sources.documents(family_id)
    import llm_client
    host = urlparse(llm_client.OLLAMA_HOST)
    if host.scheme != "http" or host.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise HTTPException(400, "Audit requires an installed loopback Ollama model")
    if not _job_lock.acquire(blocking=False):
        raise HTTPException(409, "A selected-family local audit is already running")
    ready = False
    try:
        source_baseline = idx.baseline()
        with store().connection() as conn:
            cursor = conn.execute("INSERT INTO jobs(actor,family_id,kind,state,occurred,payload) VALUES(?,?,?,?,?,?)",
                                  (account["username"], family_id, "existing_local_audit", "running", stamp(), "{}"))
            job_id = cursor.lastrowid
        ready = True
    finally:
        if not ready:
            _job_lock.release()
    def run():
        job_store = store()
        try:
            from scripts import validate_research_accuracy as existing
            # No model pull. Explicitly check the selected installed model.
            import urllib.request
            with urllib.request.urlopen(llm_client.OLLAMA_HOST + "/api/tags", timeout=10) as result:
                installed = {r["name"] for r in json.load(result)["models"]}
            model = "llama3.2:latest"
            if model not in installed:
                raise ValueError("Required small local model is not installed; no download attempted")
            result = existing.validate_family(idx.root / record["_path"], model, 90)
            result["limits"] = "Existing model audit uses bounded source text (12 pages/12000 characters); this is not human verification. See all-page source view."
            result["baseline"] = source_baseline
            result["comparison"] = {"existing_report": idx.accuracy.get(family_id), "proposed_audit": dict(result)}
            with job_store.connection() as conn:
                state = "failed" if result["status"] in {"validator_call_failed", "validator_reply_unparseable"} else "staged"
                conn.execute("UPDATE jobs SET state=?,payload=? WHERE id=? AND state='running'", (state, canonical(result), job_id))
                job_store.event(conn, account["username"], "local_audit_staged", family_id, {"job_id": job_id})
        except Exception as exc:
            # Job boundary reports failures, never a success-shaped fallback.
            with job_store.connection() as conn:
                conn.execute("UPDATE jobs SET state='failed',payload=? WHERE id=? AND state='running'",
                             (canonical({"error": str(exc), "error_type": type(exc).__name__}), job_id))
        finally:
            _job_lock.release()
    threading.Thread(target=run, daemon=True).start()
    return response({"job_id": job_id, "state": "running", "note": "Result staged separately; no existing research/report overwritten"})


@router.get("/api/research/jobs")
def jobs(request: Request):
    user(request)
    with store().connection() as conn:
        rows = conn.execute("SELECT * FROM jobs ORDER BY id DESC LIMIT 50").fetchall()
    return response([{**dict(row), "payload": json.loads(row["payload"])} for row in rows])


@router.post("/api/research/jobs/{job_id}/cancel")
def cancel(job_id: int, request: Request):
    account = user(request, "reviewer", write=True)
    with store().connection() as conn:
        if conn.execute("UPDATE jobs SET state='cancelled' WHERE id=? AND state IN ('running','staged')", (job_id,)).rowcount != 1:
            raise HTTPException(409, "Job is not cancellable")
        store().event(conn, account["username"], "local_audit_cancelled", str(job_id), {})
    return response({"state": "cancelled", "note": "In-flight model request may finish; its result will be discarded"})


@router.post("/api/research/jobs/{job_id}/accept")
def accept_job(job_id: int, body: Change, request: Request):
    account = user(request, "reviewer", write=True)
    with store().connection() as conn:
        job = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not job or job["state"] != "staged":
        raise HTTPException(409, "Job is not staged")
    payload = json.loads(job["payload"])
    if payload["baseline"] != index(refresh=True).baseline():
        raise HTTPException(409, "Sources changed; discard or run a new local audit")
    try:
        revision = store().save_revision("family:" + job["family_id"], "model_audit",
                                         {**payload, "family_id": job["family_id"], "job_id": job_id,
                                          "human_approval": False}, account["username"], body.expected_version)
    except Conflict as exc:
        raise HTTPException(409, str(exc)) from exc
    with store().connection() as conn:
        conn.execute("UPDATE jobs SET state='accepted_annotation' WHERE id=?", (job_id,))
    return response({"revision": revision, "note": "Accepted as model-audit annotation only; original files and runtime unchanged"})
