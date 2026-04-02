"""Unit tests for FX conversion: schema validation, FX rate computation, journal balancing."""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas.fx_conversion import FxConversionCreate
from app.schemas.journal import JournalEntryCreate, JournalLineCreate


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

    def test_zero_amount_raises(self):
        with pytest.raises(ValidationError, match="greater than zero"):
            FxConversionCreate(**self._valid_payload(buy_amount=Decimal("0")))

    def test_negative_amount_raises(self):
        with pytest.raises(ValidationError, match="greater than zero"):
            FxConversionCreate(**self._valid_payload(sell_amount=Decimal("-100")))


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


class TestMultiCurrencyJournalBalance:
    """Test that multi-currency journal entries balance in SGD equivalent."""

    def test_fx_journal_entry_balances_in_sgd(self):
        """SGD 100,000 → USD 70,000: debit USD 70k * 1.4286 ≈ credit SGD 100k * 1.0."""
        sgd_account = "00000000-0000-0000-0000-000000000001"
        usd_account = "00000000-0000-0000-0000-000000000002"
        fx_rate = Decimal("100000") / Decimal("70000")  # ~1.428571

        entry = JournalEntryCreate(
            entry_date="2026-04-01",
            description="FX conversion test",
            source_type="fx_conversion",
            is_confirmed=True,
            lines=[
                JournalLineCreate(
                    account_id=usd_account,
                    debit=Decimal("70000"),
                    credit=Decimal("0"),
                    currency="USD",
                    fx_rate_to_sgd=fx_rate,
                ),
                JournalLineCreate(
                    account_id=sgd_account,
                    debit=Decimal("0"),
                    credit=Decimal("100000"),
                    currency="SGD",
                    fx_rate_to_sgd=Decimal("1"),
                ),
            ],
        )
        assert len(entry.lines) == 2

    def test_single_currency_still_checks_nominal(self):
        """Single-currency entries must still balance nominally."""
        account_a = "00000000-0000-0000-0000-000000000001"
        account_b = "00000000-0000-0000-0000-000000000002"

        with pytest.raises(ValidationError, match="must balance"):
            JournalEntryCreate(
                entry_date="2026-04-01",
                lines=[
                    JournalLineCreate(
                        account_id=account_a, debit=Decimal("1000"), credit=Decimal("0"), currency="SGD",
                    ),
                    JournalLineCreate(
                        account_id=account_b, debit=Decimal("0"), credit=Decimal("500"), currency="SGD",
                    ),
                ],
            )

    def test_multi_currency_without_fx_rate_raises(self):
        """Multi-currency entries without fx_rate_to_sgd should be rejected."""
        account_a = "00000000-0000-0000-0000-000000000001"
        account_b = "00000000-0000-0000-0000-000000000002"

        with pytest.raises(ValidationError, match="fx_rate_to_sgd"):
            JournalEntryCreate(
                entry_date="2026-04-01",
                lines=[
                    JournalLineCreate(
                        account_id=account_a, debit=Decimal("70000"), credit=Decimal("0"), currency="USD",
                    ),
                    JournalLineCreate(
                        account_id=account_b, debit=Decimal("0"), credit=Decimal("100000"), currency="SGD",
                    ),
                ],
            )

    def test_multi_currency_unbalanced_in_sgd_raises(self):
        """Multi-currency entries that don't balance in SGD should be rejected."""
        account_a = "00000000-0000-0000-0000-000000000001"
        account_b = "00000000-0000-0000-0000-000000000002"

        with pytest.raises(ValidationError, match="must balance in SGD"):
            JournalEntryCreate(
                entry_date="2026-04-01",
                lines=[
                    JournalLineCreate(
                        account_id=account_a, debit=Decimal("70000"), credit=Decimal("0"),
                        currency="USD", fx_rate_to_sgd=Decimal("1.5"),  # 105,000 SGD
                    ),
                    JournalLineCreate(
                        account_id=account_b, debit=Decimal("0"), credit=Decimal("100000"),
                        currency="SGD", fx_rate_to_sgd=Decimal("1"),  # 100,000 SGD
                    ),
                ],
            )
