"""Pure, deterministic Decimal calculations for Neo's transient pricing tool."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal, Sequence


UnitType = str
MarginStatus = Literal["negative", "below_target", "acceptable"]
UNIT_TYPES: tuple[UnitType, ...] = ("Each", "Pack", "Roll", "Bag", "m²")
HUNDRED = Decimal("100")
ONE = Decimal("1")
ZERO = Decimal("0")


@dataclass(frozen=True)
class PricingItem:
    description: str = ""
    sku: str = ""
    quantity: Decimal = ONE
    unit_type: UnitType = "Each"
    buy_price: Decimal = ZERO
    additional_cost: Decimal = ZERO
    sell_price: Decimal = ZERO
    discount_percent: Decimal = ZERO
    notes: str = ""


@dataclass(frozen=True)
class PricingLine:
    description: str
    sku: str
    quantity: Decimal
    unit_type: UnitType
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
    margin_status: MarginStatus


@dataclass(frozen=True)
class PricingTotals:
    product_count: int
    quantities_by_unit: dict[str, Decimal]
    total_revenue_ex_gst: Decimal
    total_revenue_inc_gst: Decimal
    total_cost: Decimal
    total_gross_profit: Decimal
    weighted_margin_percent: Decimal
    total_discount_ex_gst: Decimal
    total_discount_inc_gst: Decimal


@dataclass(frozen=True)
class PricingCalculation:
    prices_include_gst: bool
    gst_rate: Decimal
    target_margin_percent: Decimal
    lines: tuple[PricingLine, ...]
    totals: PricingTotals
    validation_messages: tuple[str, ...] = ()


def _require_decimal(value: Decimal, name: str, *, minimum: Decimal = ZERO,
                     maximum: Decimal | None = None) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError(f"{name} must be a finite decimal value")
    if value < minimum or (maximum is not None and value > maximum):
        bound = f"between {minimum} and {maximum}" if maximum is not None else f"at least {minimum}"
        raise ValueError(f"{name} must be {bound}")
    return value


def _percentage(numerator: Decimal, denominator: Decimal) -> Decimal:
    return numerator * HUNDRED / denominator if denominator else ZERO


def calculate_pricing(
    items: Sequence[PricingItem],
    *,
    prices_include_gst: bool = False,
    gst_rate: Decimal = Decimal("10"),
    target_margin_percent: Decimal = Decimal("25"),
) -> PricingCalculation:
    """Calculate a quote entirely in Decimal; no inputs or results are stored."""
    if not isinstance(prices_include_gst, bool):
        raise ValueError("prices_include_gst must be a boolean")
    gst_rate = _require_decimal(gst_rate, "GST rate", maximum=HUNDRED)
    target_margin_percent = _require_decimal(
        target_margin_percent, "target margin", maximum=HUNDRED
    )
    gst_multiplier = ONE + gst_rate / HUNDRED

    lines: list[PricingLine] = []
    quantities = {unit: ZERO for unit in UNIT_TYPES}
    total_revenue_ex_gst = ZERO
    total_revenue_inc_gst = ZERO
    total_cost = ZERO
    total_gross_profit = ZERO
    total_discount_ex_gst = ZERO
    total_discount_inc_gst = ZERO

    for index, item in enumerate(items, start=1):
        if (not isinstance(item.unit_type, str)
                or not item.unit_type.strip()
                or len(item.unit_type) > 40
                or item.unit_type != item.unit_type.strip()):
            raise ValueError(f"Item {index} has an invalid unit type")
        quantity = _require_decimal(item.quantity, f"item {index} quantity")
        buy_entered = _require_decimal(item.buy_price, f"item {index} buy price")
        additional_entered = _require_decimal(
            item.additional_cost, f"item {index} additional cost"
        )
        sell_entered = _require_decimal(item.sell_price, f"item {index} sell price")
        discount_percent = _require_decimal(
            item.discount_percent, f"item {index} discount", maximum=HUNDRED
        )

        divisor = gst_multiplier if prices_include_gst else ONE
        buy_ex_gst = buy_entered / divisor
        additional_ex_gst = additional_entered / divisor
        sell_ex_gst = sell_entered / divisor
        landed_cost = buy_ex_gst + additional_ex_gst
        net_sell = sell_ex_gst * (ONE - discount_percent / HUNDRED)
        revenue_ex_gst = quantity * net_sell
        revenue_inc_gst = revenue_ex_gst * gst_multiplier
        line_cost = quantity * landed_cost
        gross_profit = revenue_ex_gst - line_cost
        margin_percent = _percentage(gross_profit, revenue_ex_gst)
        markup_percent = _percentage(gross_profit, line_cost)
        discount_ex_gst = quantity * (sell_ex_gst - net_sell)
        discount_inc_gst = discount_ex_gst * gst_multiplier
        margin_status: MarginStatus = (
            "negative" if gross_profit < ZERO
            else "below_target" if margin_percent < target_margin_percent
            else "acceptable"
        )

        lines.append(PricingLine(
            description=item.description,
            sku=item.sku,
            quantity=quantity,
            unit_type=item.unit_type,
            notes=item.notes,
            buy_price_ex_gst=buy_ex_gst,
            additional_cost_ex_gst=additional_ex_gst,
            sell_price_ex_gst=sell_ex_gst,
            landed_cost_per_unit=landed_cost,
            net_sell_price_per_unit=net_sell,
            revenue_ex_gst=revenue_ex_gst,
            revenue_inc_gst=revenue_inc_gst,
            total_cost=line_cost,
            gross_profit=gross_profit,
            margin_percent=margin_percent,
            markup_percent=markup_percent,
            discount_value_ex_gst=discount_ex_gst,
            discount_value_inc_gst=discount_inc_gst,
            margin_status=margin_status,
        ))
        quantities.setdefault(item.unit_type, ZERO)
        quantities[item.unit_type] += quantity
        total_revenue_ex_gst += revenue_ex_gst
        total_revenue_inc_gst += revenue_inc_gst
        total_cost += line_cost
        total_gross_profit += gross_profit
        total_discount_ex_gst += discount_ex_gst
        total_discount_inc_gst += discount_inc_gst

    totals = PricingTotals(
        product_count=len(lines),
        quantities_by_unit={unit: quantity for unit, quantity in quantities.items() if quantity},
        total_revenue_ex_gst=total_revenue_ex_gst,
        total_revenue_inc_gst=total_revenue_inc_gst,
        total_cost=total_cost,
        total_gross_profit=total_gross_profit,
        weighted_margin_percent=_percentage(total_gross_profit, total_revenue_ex_gst),
        total_discount_ex_gst=total_discount_ex_gst,
        total_discount_inc_gst=total_discount_inc_gst,
    )
    return PricingCalculation(
        prices_include_gst=prices_include_gst,
        gst_rate=gst_rate,
        target_margin_percent=target_margin_percent,
        lines=tuple(lines),
        totals=totals,
    )
