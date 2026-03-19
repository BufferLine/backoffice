import csv
import io
from datetime import date, datetime
from decimal import Decimal
from typing import BinaryIO, Optional

from app.statement_parsers.base import ParsedTransaction, StatementParser

_DATE_FORMATS = [
    "%Y-%m-%d",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%SZ",
    "%d/%m/%Y",
    "%m/%d/%Y",
    "%d-%m-%Y",
    "%Y%m%d",
]


def _parse_date(value: str) -> date:
    value = value.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Cannot parse date: {value!r}")


# Default column index mapping
_DEFAULT_COLUMN_MAPPING: dict[str, int] = {
    "tx_id": 0,
    "date": 1,
    "amount": 2,
    "currency": 3,
    "counterparty": 4,
    "reference": 5,
    "description": 6,
}


class GenericParser(StatementParser):
    """Generic CSV parser with configurable column mapping.

    column_mapping: dict mapping canonical field names to column indices.
    Fields: tx_id, date, amount, currency, counterparty (optional),
            reference (optional), description (optional).
    """

    def __init__(self, column_mapping: Optional[dict[str, int]] = None):
        self._col = column_mapping if column_mapping is not None else _DEFAULT_COLUMN_MAPPING.copy()

    def parse(self, file_data: BinaryIO) -> list[ParsedTransaction]:
        content = file_data.read()
        if isinstance(content, bytes):
            content = content.decode("utf-8-sig")  # handle BOM

        reader = csv.reader(io.StringIO(content))

        # Skip header row if first cell doesn't look like a date or number
        rows = list(reader)
        start = 0
        if rows:
            first_row = rows[0]
            first_cell = first_row[0].strip() if first_row else ""
            # Heuristic: if first cell can't be parsed as a date and doesn't look like an ID
            # treat it as a header and skip
            is_header = False
            try:
                _parse_date(first_cell)
            except ValueError:
                try:
                    Decimal(first_cell.replace(",", ""))
                except Exception:
                    is_header = True

            if is_header:
                start = 1

        col = self._col
        transactions: list[ParsedTransaction] = []

        for row in rows[start:]:
            if not any(cell.strip() for cell in row):
                continue  # skip blank rows

            def _get(field: str) -> Optional[str]:
                idx = col.get(field)
                if idx is None or idx >= len(row):
                    return None
                val = row[idx].strip()
                return val if val else None

            tx_id_val = _get("tx_id")
            date_val = _get("date")
            amount_val = _get("amount")
            currency_val = _get("currency")

            if not tx_id_val or not date_val or not amount_val or not currency_val:
                continue  # skip incomplete rows

            tx_date = _parse_date(date_val)
            amount = Decimal(amount_val.replace(",", ""))
            currency = currency_val.upper()

            raw: dict = {str(i): cell.strip() for i, cell in enumerate(row)}

            transactions.append(
                ParsedTransaction(
                    source_tx_id=tx_id_val,
                    tx_date=tx_date,
                    amount=amount,
                    currency=currency,
                    counterparty=_get("counterparty"),
                    reference=_get("reference"),
                    description=_get("description"),
                    raw_data=raw,
                )
            )

        return transactions
