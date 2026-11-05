"""Exact decimal amounts for CLI options (money must never pass through float)."""

import re
from decimal import Decimal, InvalidOperation
from typing import Optional

import typer


_THOUSANDS = re.compile(r"^-?\d{1,3}(,\d{3})+(\.\d+)?$")


def decimal_amount(value: Optional[str]) -> Optional[str]:
    """Typer callback: validate a decimal string and return it normalised for JSON.

    Amounts are sent to the API as strings so values like ``1234.567891`` (USDC has
    6 decimals) are not rounded through binary floating point.
    """
    if value is None:
        return None
    value = value.strip()
    if "," in value:
        # Commas are only accepted as thousands separators (1,234.56), never as a decimal mark (1,5).
        if not _THOUSANDS.match(value):
            raise typer.BadParameter(f"{value!r}: use '.' for decimals; ',' only as a thousands separator")
        value = value.replace(",", "")
    try:
        parsed = Decimal(value)
    except InvalidOperation:
        raise typer.BadParameter(f"{value!r} is not a valid decimal amount")
    if not parsed.is_finite():
        raise typer.BadParameter(f"{value!r} is not a valid decimal amount")
    return str(parsed)
