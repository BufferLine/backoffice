import csv
import io
from datetime import date, datetime
from decimal import Decimal
from typing import BinaryIO

from app.statement_parsers.base import ParsedTransaction, StatementParser

# Common date formats used in Airwallex exports
_DATE_FORMATS = [
    "%Y-%m-%d",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M:%SZ",
    "%d/%m/%Y",
    "%m/%d/%Y",
]


def _parse_date(value: str) -> date:
    value = value.strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Cannot parse date: {value!r}")


class AirwallexParser(StatementParser):
    """Parser for Airwallex CSV statement exports.

    Expected columns (case-insensitive):
      Transaction ID, Date, Amount, Currency, Counterparty, Reference, Status
    """

    # Map of canonical field name → possible CSV header variants (lowercase)
    _HEADER_MAP: dict[str, list[str]] = {
        "tx_id": ["transaction id", "transaction_id", "id"],
        "date": ["date", "transaction date", "value date"],
        "amount": ["amount", "transaction amount"],
        "currency": ["currency", "transaction currency"],
        "counterparty": ["counterparty", "counter party", "beneficiary", "sender"],
        "reference": ["reference", "payment reference", "ref"],
        "status": ["status", "transaction status"],
        "description": ["description", "remarks", "note"],
    }

    def _resolve_headers(self, headers: list[str]) -> dict[str, int]:
        """Return mapping of canonical name → column index."""
        lowered = [h.strip().lower() for h in headers]
        mapping: dict[str, int] = {}
        for canonical, variants in self._HEADER_MAP.items():
            for variant in variants:
                if variant in lowered:
                    mapping[canonical] = lowered.index(variant)
                    break
        return mapping

    def parse(self, file_data: BinaryIO) -> list[ParsedTransaction]:
        content = file_data.read()
        if isinstance(content, bytes):
            content = content.decode("utf-8-sig")  # handle BOM

        reader = csv.reader(io.StringIO(content))
        headers = next(reader)
        col = self._resolve_headers(headers)

        if "tx_id" not in col or "date" not in col or "amount" not in col or "currency" not in col:
            raise ValueError("Airwallex CSV missing required columns (Transaction ID, Date, Amount, Currency)")

        transactions: list[ParsedTransaction] = []
        for row in reader:
            if not any(cell.strip() for cell in row):
                continue  # skip blank rows

            raw: dict = {headers[i].strip(): row[i].strip() for i in range(min(len(headers), len(row)))}

            tx_id = row[col["tx_id"]].strip()
            tx_date = _parse_date(row[col["date"]])
            amount_str = row[col["amount"]].strip().replace(",", "")
            amount = Decimal(amount_str)
            currency = row[col["currency"]].strip().upper()

            counterparty = row[col["counterparty"]].strip() if "counterparty" in col else None
            reference = row[col["reference"]].strip() if "reference" in col else None
            description = row[col["description"]].strip() if "description" in col else None

            transactions.append(
                ParsedTransaction(
                    source_tx_id=tx_id,
                    tx_date=tx_date,
                    amount=amount,
                    currency=currency,
                    counterparty=counterparty or None,
                    reference=reference or None,
                    description=description or None,
                    raw_data=raw,
                )
            )

        return transactions
