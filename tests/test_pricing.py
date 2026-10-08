from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

import neo_api
from neo_pricing import PricingItem, calculate_pricing
from neo_store import NeoStore


D = Decimal


def item(**overrides) -> PricingItem:
    values = {
        "description": "Insulation",
        "sku": "INS-01",
        "quantity": D("1"),
        "unit_type": "Each",
        "buy_price": D("50"),
        "additional_cost": D("0"),
        "sell_price": D("80"),
        "discount_percent": D("0"),
        "notes": "",
    }
    values.update(overrides)
    return PricingItem(**values)


def test_standard_line_without_discount():
    result = calculate_pricing([item(quantity=D("10"), additional_cost=D("2"))])
    line = result.lines[0]

    assert line.landed_cost_per_unit == D("52")
    assert line.net_sell_price_per_unit == D("80")
    assert line.revenue_ex_gst == D("800")
    assert line.total_cost == D("520")
    assert line.gross_profit == D("280")
    assert line.margin_percent == D("35")
    assert line.margin_status == "acceptable"


def test_discounted_line_uses_net_sell_and_reports_discount():
    result = calculate_pricing([item(quantity=D("10"), discount_percent=D("10"))])
    line = result.lines[0]

    assert line.net_sell_price_per_unit == D("72")
    assert line.revenue_ex_gst == D("720")
    assert line.discount_value_ex_gst == D("80")
    assert line.discount_value_inc_gst == D("88")


def test_multiple_products_and_quantities_are_grouped_by_unit():
    result = calculate_pricing([
        item(quantity=D("2"), unit_type="Pack", buy_price=D("30"), sell_price=D("50")),
        item(quantity=D("3.5"), unit_type="m²", buy_price=D("10"), sell_price=D("20")),
    ])

    assert result.totals.product_count == 2
    assert result.totals.quantities_by_unit == {"Pack": D("2"), "m²": D("3.5")}
    assert result.totals.total_revenue_ex_gst == D("170")
    assert result.totals.total_cost == D("95")
    assert result.totals.total_gross_profit == D("75")


def test_catalogue_unit_labels_are_preserved_and_summarized_without_mapping():
    result = calculate_pricing([item(quantity=D("2.5"), unit_type="Carton")])

    assert result.lines[0].unit_type == "Carton"
    assert result.totals.quantities_by_unit == {"Carton": D("2.5")}


def test_zero_quantity_returns_zero_amounts_and_safe_percentages():
    result = calculate_pricing([item(quantity=D("0"))])
    line = result.lines[0]

    assert line.revenue_ex_gst == line.total_cost == line.gross_profit == D("0")
    assert line.margin_percent == line.markup_percent == D("0")
    assert result.totals.quantities_by_unit == {}


def test_zero_sell_price_has_zero_revenue_and_safe_margin():
    line = calculate_pricing([item(sell_price=D("0"))]).lines[0]

    assert line.revenue_ex_gst == D("0")
    assert line.margin_percent == D("0")
    assert line.gross_profit == D("-50")
    assert line.margin_status == "negative"


def test_zero_buy_and_additional_cost_has_zero_cost_and_safe_markup():
    line = calculate_pricing([
        item(buy_price=D("0"), additional_cost=D("0"), sell_price=D("80"))
    ]).lines[0]

    assert line.total_cost == D("0")
    assert line.gross_profit == D("80")
    assert line.markup_percent == D("0")


def test_full_discount_with_cost_is_negative_and_discount_is_total_sell_value():
    line = calculate_pricing([item(discount_percent=D("100"))]).lines[0]

    assert line.revenue_ex_gst == D("0")
    assert line.discount_value_ex_gst == D("80")
    assert line.gross_profit == D("-50")
    assert line.margin_status == "negative"
    assert line.margin_percent == D("0")


def test_negative_margin_sale_is_flagged():
    line = calculate_pricing([item(buy_price=D("90"), sell_price=D("80"))]).lines[0]

    assert line.gross_profit == D("-10")
    assert line.margin_percent == D("-12.5")
    assert line.margin_status == "negative"


def test_additional_cost_is_included_in_landed_cost():
    line = calculate_pricing([item(buy_price=D("20"), additional_cost=D("7.25"))]).lines[0]

    assert line.landed_cost_per_unit == D("27.25")
    assert line.total_cost == D("27.25")
    assert line.gross_profit == D("52.75")


def test_gst_inclusive_buy_additional_and_sell_prices_normalize_to_ex_gst():
    result = calculate_pricing(
        [item(buy_price=D("55"), additional_cost=D("11"), sell_price=D("88"))],
        prices_include_gst=True,
        gst_rate=D("10"),
    )
    line = result.lines[0]

    assert line.buy_price_ex_gst == D("5E+1")
    assert line.additional_cost_ex_gst == D("1E+1")
    assert line.sell_price_ex_gst == D("8E+1")
    assert line.total_cost == D("60")
    assert line.gross_profit == D("20")
    assert line.revenue_ex_gst == D("80")
    assert line.revenue_inc_gst == D("88.0")


def test_overall_margin_is_weighted_by_total_revenue():
    result = calculate_pricing([
        item(buy_price=D("90"), sell_price=D("100")),
        item(buy_price=D("450"), sell_price=D("900")),
    ])

    assert result.lines[0].margin_percent == D("10")
    assert result.lines[1].margin_percent == D("50")
    assert result.totals.weighted_margin_percent == D("46")
    assert result.totals.weighted_margin_percent != D("30")


@pytest.mark.parametrize("field,value", [
    ("discount_percent", D("-0.01")),
    ("discount_percent", D("100.01")),
    ("quantity", D("-1")),
    ("buy_price", D("-0.01")),
    ("additional_cost", D("-0.01")),
    ("sell_price", D("-0.01")),
])
def test_pricing_request_rejects_out_of_range_item_values(field, value):
    from neo_api import PricingItemRequest

    values = {
        "quantity": D("1"), "unit_type": "Each", "buy_price": D("1"),
        "sell_price": D("2"), "discount_percent": D("0"),
    }
    values[field] = value

    with pytest.raises(ValidationError):
        PricingItemRequest.model_validate(values)


@pytest.mark.parametrize("value", [D("-0.01"), D("100.01"), D("NaN"), D("Infinity")])
@pytest.mark.parametrize("field", ["gst_rate", "target_margin_percent"])
def test_pricing_request_rejects_invalid_gst_or_margin_target(field, value):
    from neo_api import PricingRequest

    with pytest.raises(ValidationError):
        PricingRequest.model_validate({"items": [], field: value})


def test_empty_items_returns_zero_summary():
    totals = calculate_pricing([]).totals

    assert totals.product_count == 0
    assert totals.quantities_by_unit == {}
    assert totals.total_revenue_ex_gst == D("0")
    assert totals.total_revenue_inc_gst == D("0")
    assert totals.total_cost == D("0")
    assert totals.total_gross_profit == D("0")
    assert totals.weighted_margin_percent == D("0")
    assert totals.total_discount_ex_gst == D("0")
    assert totals.total_discount_inc_gst == D("0")


def test_decimal_square_metre_quantity_is_not_rounded():
    line = calculate_pricing([
        item(quantity=D("2.375"), unit_type="m²", buy_price=D("3.20"), sell_price=D("5.50"))
    ]).lines[0]

    assert line.quantity == D("2.375")
    assert line.revenue_ex_gst == D("13.0625")
    assert line.total_cost == D("7.60000")


def test_profit_reconciliation_and_discount_quote_gst_reconciliation():
    result = calculate_pricing([
        item(quantity=D("2"), sell_price=D("100"), discount_percent=D("12.5")),
        item(quantity=D("1.5"), unit_type="Roll", buy_price=D("20"),
             sell_price=D("65"), discount_percent=D("5")),
    ], gst_rate=D("10"))

    assert result.totals.total_gross_profit == (
        result.totals.total_revenue_ex_gst - result.totals.total_cost
    )
    assert result.totals.total_revenue_inc_gst == result.totals.total_revenue_ex_gst * D("1.1")
    assert result.totals.total_discount_inc_gst == result.totals.total_discount_ex_gst * D("1.1")


def test_margin_status_respects_target_and_negative_profit_precedence():
    result = calculate_pricing([
        item(buy_price=D("70"), sell_price=D("100")),
        item(buy_price=D("90"), sell_price=D("100")),
        item(buy_price=D("110"), sell_price=D("100")),
    ], target_margin_percent=D("30"))

    assert [line.margin_status for line in result.lines] == [
        "acceptable", "below_target", "negative",
    ]


def test_calculator_api_requires_neo_session_same_origin_and_csrf(monkeypatch, tmp_path):
    database = NeoStore(tmp_path / "neo.sqlite3")
    monkeypatch.setattr(neo_api, "_store", database)
    app = FastAPI()
    app.include_router(neo_api.router)
    client = TestClient(app, base_url="http://127.0.0.1",
                        client=("127.0.0.1", 5000))
    payload = {
        "items": [{
            "description": "R2.5 Ceiling Batts", "sku": "INS-R25",
            "quantity": "10", "unit_type": "Pack", "buy_price": "50",
            "additional_cost": "2", "sell_price": "80",
            "discount_percent": "10", "notes": "",
        }],
    }

    assert client.post("/api/pricing/calculate", json=payload).status_code == 401
    client.get("/api/neo/session")
    assert client.post(
        "/api/pricing/calculate", json=payload,
        headers={"Origin": "http://127.0.0.1"},
    ).status_code == 403
    csrf = client.get("/api/neo/session").json()["csrf"]
    headers = {"Origin": "http://127.0.0.1", "X-Neo-CSRF": csrf}
    assert client.post(
        "/api/pricing/calculate", json=payload,
        headers={**headers, "Origin": "http://attacker.invalid"},
    ).status_code == 403
    response = client.post("/api/pricing/calculate", json=payload, headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert D(body["lines"][0]["revenue_ex_gst"]) == D("720")
    assert body["lines"][0]["margin_status"] == "acceptable"
    assert D(body["totals"]["total_gross_profit"]) == D("200")
    assert body["validation_messages"] == []
    assert database.conversations() == []
    assert database.records() == []
    with database.connection() as connection:
        tables = {row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
    assert not any("pricing" in table for table in tables)
    remote = TestClient(app, base_url="http://127.0.0.1",
                        client=("192.0.2.15", 5000))
    assert remote.post("/api/pricing/calculate", json=payload).status_code == 404
    rebinding = TestClient(app, base_url="http://pricing.attacker.invalid",
                           client=("127.0.0.1", 5000))
    assert rebinding.post("/api/pricing/calculate", json=payload).status_code == 404


def test_calculator_api_does_not_call_neo_oracle_pricing_or_model(monkeypatch, tmp_path):
    database = NeoStore(tmp_path / "neo.sqlite3")
    monkeypatch.setattr(neo_api, "_store", database)
    monkeypatch.setattr(neo_api, "assistant", lambda: pytest.fail("AI assistant called"))
    app = FastAPI()
    app.include_router(neo_api.router)
    client = TestClient(app, base_url="http://127.0.0.1",
                        client=("127.0.0.1", 5000))
    csrf = client.get("/api/neo/session").json()["csrf"]

    response = client.post("/api/pricing/calculate", headers={
        "Origin": "http://127.0.0.1", "X-Neo-CSRF": csrf,
    }, json={"items": []})

    assert response.status_code == 200
    assert response.json()["totals"]["product_count"] == 0


def test_calculator_api_validation_and_neo_frontend_contract(monkeypatch, tmp_path):
    monkeypatch.setattr(neo_api, "_store", NeoStore(tmp_path / "validation-neo.sqlite3"))
    app = FastAPI()
    app.include_router(neo_api.router)
    operation = app.openapi()["paths"]["/api/pricing/calculate"]["post"]
    assert operation["requestBody"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/PricingRequest"
    )
    assert operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/PricingResponse"
    )
    client = TestClient(app, base_url="http://127.0.0.1",
                        client=("127.0.0.1", 5000))
    client.get("/api/neo/session")
    csrf = client.get("/api/neo/session").json()["csrf"]
    headers = {"Origin": "http://127.0.0.1", "X-Neo-CSRF": csrf}
    response = client.post("/api/pricing/calculate", headers=headers, json={
        "items": [{
            "quantity": "-1", "unit_type": "Each", "buy_price": "1",
            "sell_price": "2",
        }],
    })

    assert response.status_code == 422
    assert any("quantity" in error["loc"] for error in response.json()["detail"])
    page = (Path(__file__).resolve().parents[1] / "templates" / "neo.html").read_text(encoding="utf-8")
    assert 'id="salesTab"' in page and 'id="pricingTab"' in page
    assert 'id="messageForm"' in page and 'id="conversationList"' in page
    assert '"/api/pricing/calculate"' in page
    assert '"/api/pricing/melbourne-lookup"' in page
    assert "Load Melbourne prices" in page
    assert "Lookup cleared after GST basis/rate changed" in page
    assert 'unit.add(new Option(result.unit_type,result.unit_type))' in page
    assert "localStorage" not in page and "sessionStorage" not in page
