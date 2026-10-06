"""Local-only Matrix managerial interface."""
from __future__ import annotations

import ipaddress
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse

ROOT = Path(__file__).resolve().parent
router = APIRouter()


@router.get("/matrix", response_class=HTMLResponse)
def matrix_page(request: Request):
    address = request.client.host if request.client else ""
    try:
        local = ipaddress.ip_address(address).is_loopback
    except ValueError:
        local = False
    hostname = request.url.hostname or ""
    try:
        local_host = hostname.casefold() == "localhost" or ipaddress.ip_address(hostname).is_loopback
    except ValueError:
        local_host = False
    if not local or not local_host:
        raise HTTPException(404, "Not found")
    return HTMLResponse((ROOT / "templates" / "matrix.html").read_text(encoding="utf-8"),
                        headers={
                            "Cache-Control": "no-store", "Referrer-Policy": "no-referrer",
                            "X-Content-Type-Options": "nosniff", "X-Frame-Options": "SAMEORIGIN",
                            "Content-Security-Policy":
                                "default-src 'self'; script-src 'self' 'unsafe-inline'; "
                                "style-src 'self' 'unsafe-inline'; connect-src 'self'; "
                                "frame-src 'self'; img-src 'self' data:",
                        })
