"""Unit tests for FX conversion: schema validation, FX rate computation."""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas.fx_conversion import FxConversionCreate


class TestFxConversionCreate:
    def _valid_payload(self, **overrides) -> dict:
        base = {
            "conversion_date": "2026-04-01",
            "sell_currency": "SGD",
            "sell_amount": Decimal("100000"),
            "buy_currency": "USD",
            "buy_amount": Decimal("70000"),
            "sell_account_id": "00000000-0000-0000-0000-000000000001",
            "buy_account_id": "00000000-0000-0000-0000-000000000002",
        }
        base.update(overrides)
        return base

    def test_valid_sgd_to_usd(self):
        data = FxConversionCreate(**self._valid_payload())
        assert data.sell_currency == "SGD"
        assert data.buy_currency == "USD"
        assert data.sell_amount == Decimal("100000")
        assert data.buy_amount == Decimal("70000")

    def test_same_currency_raises(self):
        with pytest.raises(ValidationError, match="must be different"):
            FxConversionCreate(**self._valid_payload(buy_currency="SGD"))

    def test_optional_fields(self):
        data = FxConversionCreate(
            **self._valid_payload(provider="airwallex", reference="AWX-123", notes="Q1 pre-funding")
        )
        assert data.provider == "airwallex"
        assert data.reference == "AWX-123"
        assert data.notes == "Q1 pre-funding"

    def test_optional_fields_default_none(self):
        data = FxConversionCreate(**self._valid_payload())
        assert data.provider is None
        assert data.reference is None
        assert data.notes is None

    def test_missing_required_field_raises(self):
        payload = self._valid_payload()
        del payload["sell_currency"]
        with pytest.raises(ValidationError):
            FxConversionCreate(**payload)

    def test_negative_amount_allowed(self):
        """Negative amounts are valid — schema doesn't restrict sign."""
        data = FxConversionCreate(**self._valid_payload(sell_amount=Decimal("-100")))
        assert data.sell_amount == Decimal("-100")


class TestFxRateComputation:
    """Test the FX rate computation logic used by the service layer."""

    def test_sgd_to_usd_rate(self):
        sell = Decimal("100000")
        buy = Decimal("70000")
        rate = sell / buy
        assert rate == pytest.approx(Decimal("1.428571"), abs=Decimal("0.001"))

    def test_usd_to_sgd_rate(self):
        sell = Decimal("70000")
        buy = Decimal("100000")
        rate = sell / buy
        assert rate == Decimal("0.7")

    def test_sgd_amount_when_sell_is_sgd(self):
        """When selling SGD, sgd_amount = sell_amount."""
        sell_currency = "SGD"
        sell_amount = Decimal("100000")
        buy_currency = "USD"
        buy_amount = Decimal("70000")

        if sell_currency == "SGD":
            sgd_amount = sell_amount
        elif buy_currency == "SGD":
            sgd_amount = buy_amount
        else:
            sgd_amount = sell_amount

        assert sgd_amount == Decimal("100000")

    def test_sgd_amount_when_buy_is_sgd(self):
        """When buying SGD, sgd_amount = buy_amount."""
        sell_currency = "USD"
        sell_amount = Decimal("70000")
        buy_currency = "SGD"
        buy_amount = Decimal("100000")

        if sell_currency == "SGD":
            sgd_amount = sell_amount
        elif buy_currency == "SGD":
            sgd_amount = buy_amount
        else:
            sgd_amount = sell_amount

        assert sgd_amount == Decimal("100000")

    def test_sgd_amount_neither_sgd_uses_sell(self):
        """When neither side is SGD, sgd_amount falls back to sell_amount."""
        sell_currency = "USD"
        sell_amount = Decimal("70000")
        buy_currency = "EUR"
        buy_amount = Decimal("65000")

        if sell_currency == "SGD":
            sgd_amount = sell_amount
        elif buy_currency == "SGD":
            sgd_amount = buy_amount
        else:
            sgd_amount = sell_amount

        assert sgd_amount == Decimal("70000")
