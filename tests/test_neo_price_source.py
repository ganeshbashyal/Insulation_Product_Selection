from __future__ import annotations

from datetime import date
from decimal import Decimal
from hashlib import sha256
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from openpyxl import Workbook

import neo_api
import neo_price_source
from neo_price_source import (
    AmbiguousPrice,
    PriceNotFound,
    PriceSourceUnavailable,
    lookup_melbourne_price,
)
from neo_store import NeoStore


SALES_HEADERS = [
    "Our SKU", "Our Product Name", "Category", "Material Type", "Product Use",
    "R Value / RW / NRC", "Length (mm)", "Width (mm)", "Thickness (mm)",
    "M2 per Unit", "Buy/Sell Unit", "Sell Price (Inc GST)", "Location", "MOQ",
    "Local Pick up?", "Metro Delivery", "Availability Status", "Supplier Name",
    "Notes", "Spec Status", "Spec ID", "Spec Family", "TDS", "SDS",
]
LOCATION_HEADERS = [
    "Our SKU", "Location", "Active?", "Availability Status",
    "Lead Time / Special Order?", "Sell Price (Inc GST)", "Buy Price (Ex GST)",
    "MOQ", "Local Pick up?", "Metro Delivery", "Supplier Name", "Supplier SKU",
    "Last Updated", "Last Price Source", "Last Price Source File/Tab",
    "Location Notes", "Sell Price (Ex GST)", "GP$ (Ex GST)", "GP %",
    "Our Product Name", "Markup %", "Pricing Rule", "Manual Sell Override / POA",
]


def make_workbook(path: Path, *, duplicate: bool = False) -> Path:
    workbook = Workbook()
    sales = workbook.active
    sales.title = "Sales_Melbourne"
    sales.append(["V3 Melbourne staff pricing"])
    sales.append(["Values are source workbook cached values"])
    sales.append(SALES_HEADERS)
    sales.append(["SKU-BOX", "Insulation carton", None, None, None, None, None, None, None,
                  None, "Carton", 110, "Melbourne", None, None, None, "Available"])
    sales.append(["SKU-INACTIVE", "Inactive product", None, None, None, None, None, None,
                  None, None, "Each", 110, "Melbourne", None, None, None, "Not Available"])
    sales.append(["SKU-NOPRICE", "Unpriced product", None, None, None, None, None, None,
                  None, None, "Pack", 110, "Melbourne", None, None, None, "Available"])
    if duplicate:
        sales.append(["sku-box", "Duplicate SKU", None, None, None, None, None, None, None,
                      None, "Carton", 110, "Melbourne", None, None, None, "Available"])

    locations = workbook.create_sheet("SKU_Location")
    locations.append(["V3 location price list"])
    locations.append(LOCATION_HEADERS)
    locations.append([
        "SKU-BOX", "Melbourne", "Yes", "Available", None, 110, 50, None, None, None,
        None, None, date(2025, 3, 4), None, None, None, 100, None, None, None, None,
        None, None,
    ])
    locations.append([
        "SKU-INACTIVE", "Melbourne", "No", "Inactive", None, 110, 50, None, None, None,
        None, None, date(2025, 3, 4), None, None, None, 100, None, None, None, None,
        None, None,
    ])
    locations.append([
        "SKU-NOPRICE", "Melbourne", "Yes", "Available", None, 110, None, None, None, None,
        None, None, date(2025, 3, 4), None, None, None, 100, None, None, None, None,
        None, None,
    ])
    sales.append(["SKU-OOS", "Unavailable product", None, None, None, None, None, None,
                  None, None, "Unit", 110, "Melbourne", None, None, None, "Not Available"])
    locations.append([
        "SKU-OOS", "Melbourne", "Yes", "Not Available", None, 110, 50, None, None, None,
        None, None, date(2025, 3, 4), None, None, None, 100, None, None, None, None,
        None, None,
    ])
    workbook.save(path)
    return path


@pytest.fixture
def price_workbook(tmp_path, monkeypatch):
    path = make_workbook(tmp_path / "local-v3.xlsm")
    monkeypatch.setenv("NEO_PRICING_WORKBOOK", str(path))
    return path


def test_exact_sku_lookup_returns_local_melbourne_prices_and_provenance(price_workbook):
    before = sha256(price_workbook.read_bytes()).hexdigest()

    result = lookup_melbourne_price(" sku-box ")

    assert result.sku == "sku-box"
    assert result.description == "Insulation carton"
    assert result.unit_type == "Carton"
    assert result.buy_price_ex_gst == Decimal("50")
    assert result.sell_price_ex_gst == Decimal("100")
    assert result.effective_date == "2025-03-04"
    assert result.source_file == "local-v3.xlsm"
    assert result.buy_source_sheet == "SKU_Location"
    assert result.sell_source_sheet == "Sales_Melbourne"
    assert result.availability_status == "Available"
    assert sha256(price_workbook.read_bytes()).hexdigest() == before


@pytest.mark.parametrize(("sku", "error"), [
    ("SKU-NOT-FOUND", PriceNotFound),
    ("SKU-INACTIVE", PriceNotFound),
    ("SKU-NOPRICE", PriceNotFound),
    ("SKU-OOS", PriceNotFound),
])
def test_lookup_refuses_missing_inactive_or_unpriced_skus(price_workbook, sku, error):
    with pytest.raises(error):
        lookup_melbourne_price(sku)


def test_lookup_refuses_ambiguous_exact_sku(tmp_path, monkeypatch):
    path = make_workbook(tmp_path / "duplicate.xlsm", duplicate=True)
    monkeypatch.setenv("NEO_PRICING_WORKBOOK", str(path))

    with pytest.raises(AmbiguousPrice):
        lookup_melbourne_price("SKU-BOX")


def test_lookup_reports_missing_local_workbook(tmp_path, monkeypatch):
    monkeypatch.setenv("NEO_PRICING_WORKBOOK", str(tmp_path / "absent.xlsm"))

    with pytest.raises(PriceSourceUnavailable, match="unavailable"):
        lookup_melbourne_price("SKU-BOX")


def test_api_lookup_returns_prices_in_selected_gst_basis_and_requires_csrf(
    price_workbook, monkeypatch, tmp_path
):
    monkeypatch.setattr(neo_api, "_store", NeoStore(tmp_path / "neo.sqlite3"))
    app = FastAPI()
    app.include_router(neo_api.router)
    client = TestClient(app, base_url="http://127.0.0.1",
                        client=("127.0.0.1", 5000))
    payload = {"sku": "SKU-BOX", "prices_include_gst": True, "gst_rate": "10"}

    assert client.post("/api/pricing/melbourne-lookup", json=payload).status_code == 401
    csrf = client.get("/api/neo/session").json()["csrf"]
    headers = {"Origin": "http://127.0.0.1", "X-Neo-CSRF": csrf}
    result = client.post("/api/pricing/melbourne-lookup", json=payload, headers=headers)

    assert result.status_code == 200
    assert result.headers["cache-control"] == "no-store"
    body = result.json()
    assert Decimal(body["buy_price"]) == Decimal("55.0")
    assert Decimal(body["sell_price"]) == Decimal("110.0")
    assert Decimal(body["buy_price_ex_gst"]) == Decimal("50")
    assert Decimal(body["sell_price_ex_gst"]) == Decimal("100")
    assert body["prices_include_gst"] is True
    assert body["unit_type"] == "Carton"
    assert body["source_file"] == price_workbook.name


def test_api_lookup_returns_clear_http_statuses_for_unavailable_or_unmatched_sku(
    price_workbook, monkeypatch, tmp_path
):
    monkeypatch.setattr(neo_api, "_store", NeoStore(tmp_path / "neo.sqlite3"))
    app = FastAPI()
    app.include_router(neo_api.router)
    client = TestClient(app, base_url="http://127.0.0.1",
                        client=("127.0.0.1", 5000))
    csrf = client.get("/api/neo/session").json()["csrf"]
    headers = {"Origin": "http://127.0.0.1", "X-Neo-CSRF": csrf}

    missing = client.post("/api/pricing/melbourne-lookup", json={"sku": "NOPE"}, headers=headers)
    assert missing.status_code == 404
    assert "exact SKU" in missing.json()["detail"]

    monkeypatch.setattr(neo_price_source, "workbook_path", lambda: tmp_path / "gone.xlsm")
    unavailable = client.post(
        "/api/pricing/melbourne-lookup", json={"sku": "SKU-BOX"}, headers=headers
    )
    assert unavailable.status_code == 503
    assert "workbook is unavailable" in unavailable.json()["detail"]


def test_api_lookup_reports_ambiguous_exact_sku_as_conflict(tmp_path, monkeypatch):
    path = make_workbook(tmp_path / "ambiguous.xlsm", duplicate=True)
    monkeypatch.setenv("NEO_PRICING_WORKBOOK", str(path))
    monkeypatch.setattr(neo_api, "_store", NeoStore(tmp_path / "neo.sqlite3"))
    app = FastAPI()
    app.include_router(neo_api.router)
    client = TestClient(app, base_url="http://127.0.0.1",
                        client=("127.0.0.1", 5000))
    csrf = client.get("/api/neo/session").json()["csrf"]

    result = client.post("/api/pricing/melbourne-lookup", headers={
        "Origin": "http://127.0.0.1", "X-Neo-CSRF": csrf,
    }, json={"sku": "SKU-BOX"})

    assert result.status_code == 409
    assert "more than once" in result.json()["detail"]
