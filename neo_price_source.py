"""Read-only exact-SKU pricing lookup from the local V3 staff workbook."""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from zipfile import BadZipFile

from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException


WORKBOOK_NAME = "Insulation_Easy_Sell_Price_List_V3_Final_Staff_Release.xlsm"
MELBOURNE_SALES_SHEET = "Sales_Melbourne"
SKU_LOCATION_SHEET = "SKU_Location"


class PriceSourceError(ValueError):
    """Base error for an unavailable or unsuitable local source price."""


class PriceSourceUnavailable(PriceSourceError):
    """The configured price workbook or its schema is unavailable."""


class PriceNotFound(PriceSourceError):
    """No exact active Melbourne SKU price is available."""


class AmbiguousPrice(PriceSourceError):
    """The workbook contains multiple rows for an exact Melbourne SKU."""


@dataclass(frozen=True)
class MelbournePrice:
    sku: str
    description: str
    unit_type: str
    buy_price_ex_gst: Decimal
    sell_price_ex_gst: Decimal
    effective_date: str | None
    source_file: str
    sell_source_sheet: str
    buy_source_sheet: str
    availability_status: str


def workbook_path() -> Path:
    """Resolve an explicitly configured local file, or the owner's Downloads default."""
    configured = os.environ.get("NEO_PRICING_WORKBOOK", "").strip()
    if configured:
        return Path(configured).expanduser()
    return Path.home() / "Downloads" / WORKBOOK_NAME


def _headers(sheet, row_number: int) -> dict[str, int]:
    row = next(sheet.iter_rows(min_row=row_number, max_row=row_number, values_only=True), ())
    return {
        str(value).strip().casefold(): index
        for index, value in enumerate(row)
        if value is not None and str(value).strip()
    }


def _required_columns(headers: dict[str, int], names: tuple[str, ...], sheet_name: str) -> dict[str, int]:
    missing = [name for name in names if name.casefold() not in headers]
    if missing:
        raise PriceSourceUnavailable(
            f"Required pricing columns are missing from {sheet_name}: {', '.join(missing)}"
        )
    return {name: headers[name.casefold()] for name in names}


def _price(value, column_name: str) -> Decimal:
    if isinstance(value, bool) or value is None:
        raise PriceNotFound(f"Melbourne {column_name} is missing or not numeric.")
    try:
        result = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        raise PriceNotFound(f"Melbourne {column_name} is missing or not numeric.") from None
    if not result.is_finite() or result < 0:
        raise PriceNotFound(f"Melbourne {column_name} is not a valid non-negative price.")
    return result


def _effective_date(value) -> str | None:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str) and value.strip():
        return value.strip()[:40]
    return None


def lookup_melbourne_price(sku: str) -> MelbournePrice:
    """Read one active SKU from the Melbourne sheets; never writes or caches workbook data."""
    normalized_sku = sku.strip()
    if not normalized_sku:
        raise PriceNotFound("Enter an SKU for an exact Melbourne price lookup.")

    path = workbook_path()
    if not path.is_file():
        raise PriceSourceUnavailable(
            "The local V3 price workbook is unavailable. Check NEO_PRICING_WORKBOOK "
            "or the owner's Downloads folder."
        )

    try:
        workbook = load_workbook(path, read_only=True, data_only=True)
    except (BadZipFile, InvalidFileException, OSError, ValueError, KeyError) as exc:
        raise PriceSourceUnavailable(
            f"The local V3 price workbook could not be opened ({type(exc).__name__})."
        ) from exc

    try:
        if MELBOURNE_SALES_SHEET not in workbook.sheetnames or SKU_LOCATION_SHEET not in workbook.sheetnames:
            raise PriceSourceUnavailable("The V3 workbook is missing its Melbourne pricing sheets.")

        sales = workbook[MELBOURNE_SALES_SHEET]
        sales_columns = _required_columns(_headers(sales, 3), (
            "Our SKU", "Our Product Name", "Buy/Sell Unit", "Availability Status",
        ), MELBOURNE_SALES_SHEET)
        matching_sales = []
        for row in sales.iter_rows(min_row=4, values_only=True):
            value = row[sales_columns["Our SKU"]]
            if value is not None and str(value).strip().casefold() == normalized_sku.casefold():
                matching_sales.append(row)

        if len(matching_sales) > 1:
            raise AmbiguousPrice("The exact SKU appears more than once in the Melbourne sales view.")
        if not matching_sales:
            raise PriceNotFound("No exact SKU match exists in the Melbourne sales view.")

        locations = workbook[SKU_LOCATION_SHEET]
        location_columns = _required_columns(_headers(locations, 2), (
            "Our SKU", "Location", "Active?", "Buy Price (Ex GST)",
            "Sell Price (Ex GST)", "Last Updated", "Availability Status",
        ), SKU_LOCATION_SHEET)
        matching_locations = []
        for row in locations.iter_rows(min_row=3, values_only=True):
            value = row[location_columns["Our SKU"]]
            city = row[location_columns["Location"]]
            if (value is not None
                    and str(value).strip().casefold() == normalized_sku.casefold()
                    and str(city or "").strip().casefold() == "melbourne"):
                matching_locations.append(row)

        if len(matching_locations) > 1:
            raise AmbiguousPrice("The exact SKU has multiple Melbourne location price rows.")
        if not matching_locations:
            raise PriceNotFound("No exact Melbourne buy/sell price row exists for this SKU.")

        sales_row = matching_sales[0]
        location_row = matching_locations[0]
        active = str(location_row[location_columns["Active?"]] or "").strip().casefold()
        if active != "yes":
            raise PriceNotFound("This SKU is not marked active for Melbourne pricing.")
        availability_status = str(
            location_row[location_columns["Availability Status"]] or ""
        ).strip()
        if availability_status.casefold() != "available":
            raise PriceNotFound(
                f"This SKU is not currently available for Melbourne pricing "
                f"({availability_status or 'status not stated'})."
            )
        sales_availability = str(
            sales_row[sales_columns["Availability Status"]] or ""
        ).strip()
        if sales_availability.casefold() != "available":
            raise PriceNotFound(
                f"This SKU is not currently available in the Melbourne sales view "
                f"({sales_availability or 'status not stated'})."
            )

        description = str(sales_row[sales_columns["Our Product Name"]] or "").strip()
        unit_type = str(sales_row[sales_columns["Buy/Sell Unit"]] or "").strip()
        if not unit_type:
            raise PriceNotFound("The Melbourne sales view has no unit type for this SKU.")

        return MelbournePrice(
            sku=normalized_sku,
            description=description,
            unit_type=unit_type,
            buy_price_ex_gst=_price(
                location_row[location_columns["Buy Price (Ex GST)"]], "buy price"
            ),
            sell_price_ex_gst=_price(
                location_row[location_columns["Sell Price (Ex GST)"]], "sell price"
            ),
            effective_date=_effective_date(location_row[location_columns["Last Updated"]]),
            source_file=path.name,
            sell_source_sheet=MELBOURNE_SALES_SHEET,
            buy_source_sheet=SKU_LOCATION_SHEET,
            availability_status=availability_status,
        )
    except (IndexError, KeyError, OSError, ValueError) as exc:
        if isinstance(exc, PriceSourceError):
            raise
        raise PriceSourceUnavailable(
            f"The local V3 workbook could not be read ({type(exc).__name__})."
        ) from exc
    finally:
        workbook.close()
