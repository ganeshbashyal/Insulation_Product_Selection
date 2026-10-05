"""Protected family-first research APIs; no downloader or arbitrary runner."""
from __future__ import annotations

import hmac
import hashlib
import json
import threading
from urllib.parse import urlparse
from typing import Literal

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse
from pydantic import BaseModel, Field

from local_source_review import checked_pages
from product_research import ROOT
from research_store import Conflict, canonical, stamp
from research_workflow import active_effective, effective_evidence, latest_reviews, publication_preview, validate_review
from knowledge_service import service, knowledge_validation

router = APIRouter()
_job_lock = threading.Lock()
COOKIE = "aurora_research_session"


def store():
    return service().store()


def index(refresh=False):
    return service().index(refresh)


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


@router.get("/admin/products")
def page():
    return HTMLResponse((ROOT / "templates" / "product_research.html").read_text(encoding="utf-8"),
                        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})


@router.get("/admin/knowledge")
def knowledge_page():
    return HTMLResponse((ROOT / "templates" / "knowledge_validation.html").read_text(encoding="utf-8"),
                        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"})


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
