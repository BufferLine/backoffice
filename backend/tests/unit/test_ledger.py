"""Unit tests for accrual ledger postings (no database)."""

import uuid
from datetime import date, timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.config import settings
from app.schemas.journal import JournalEntryCreate
from app.services import ledger
from app.services.ledger import (
    LedgerAccounts,
    build_invoice_issue_lines,
    build_receipt_lines,
    fx_difference_line,
    rate_currency,
    resolve_fx_rate_to_sgd,
    settles_in,
)

AR = uuid.uuid4()
REV = uuid.uuid4()
GST = uuid.uuid4()
FX = uuid.uuid4()
WALLET = uuid.uuid4()


def _sgd_totals(lines):
    debit = sum(l.debit * l.fx_rate_to_sgd for l in lines)
    credit = sum(l.credit * l.fx_rate_to_sgd for l in lines)
    return debit, credit


def _validate(lines):
    """Run the real JournalEntryCreate balance validator."""
    return JournalEntryCreate(entry_date=date(2026, 11, 5), is_confirmed=True, lines=lines)


class TestCurrencies:
    def test_stablecoins_value_at_peg(self):
        assert rate_currency("usdc") == "USD"
        assert rate_currency("USDT") == "USD"
        assert rate_currency("EUR") == "EUR"

    def test_settles_in(self):
        assert settles_in("USDC", "USD")
        assert settles_in("USDT", "USDC")
        assert settles_in("SGD", "SGD")
        assert not settles_in("USDC", "SGD")
        assert not settles_in("EUR", "USD")


class TestLedgerAccountsJson:
    def test_round_trip(self):
        m = LedgerAccounts(receivable={"USD": AR}, revenue=REV, gst_output=GST, fx_gain_loss=FX)
        back = LedgerAccounts.from_json(m.to_json())
        assert back == m
        assert back.configured

    def test_empty_is_not_configured(self):
        assert not LedgerAccounts.from_json(None).configured
        assert not LedgerAccounts(revenue=REV).configured

    def test_missing_receivable_currency(self):
        m = LedgerAccounts(receivable={"SGD": AR}, revenue=REV)
        with pytest.raises(ValueError, match="receivable account mapped for USD"):
            m.receivable_for("USD")


class TestInvoiceIssueLines:
    def test_sgd_with_gst(self):
        lines = build_invoice_issue_lines(
            total=Decimal("1090.00"), tax=Decimal("90.00"), currency="SGD", rate=Decimal("1"),
            receivable_id=AR, revenue_id=REV, gst_output_id=GST, label="INV-1",
        )
        assert [(l.account_id, l.debit, l.credit) for l in lines] == [
            (AR, Decimal("1090.00"), 0),
            (REV, 0, Decimal("1000.00")),
            (GST, 0, Decimal("90.00")),
        ]
        _validate(lines)

    def test_usd_invoice_converts_revenue_to_sgd(self):
        lines = build_invoice_issue_lines(
            total=Decimal("3750.00"), tax=Decimal("0"), currency="USD", rate=Decimal("1.2934"),
            receivable_id=AR, revenue_id=REV, gst_output_id=None, label="INV-2",
        )
        ar, rev = lines
        assert (ar.currency, ar.debit, ar.fx_rate_to_sgd) == ("USD", Decimal("3750.00"), Decimal("1.2934"))
        assert (rev.currency, rev.credit) == ("SGD", Decimal("4850.25"))  # 3750 * 1.2934
        _validate(lines)

    def test_rounding_absorbed_by_revenue(self):
        lines = build_invoice_issue_lines(
            total=Decimal("1000.01"), tax=Decimal("82.57"), currency="USD", rate=Decimal("1.333333"),
            receivable_id=AR, revenue_id=REV, gst_output_id=GST, label="INV-3",
        )
        _, rev, gst = lines
        assert rev.credit + gst.credit == Decimal("1333.35")  # round(1000.01 * 1.333333)
        debit, credit = _sgd_totals(lines)
        assert abs(debit - credit) < Decimal("0.01")
        _validate(lines)

    def test_gst_requires_mapping(self):
        with pytest.raises(ValueError, match="GST output account"):
            build_invoice_issue_lines(
                total=Decimal("109"), tax=Decimal("9"), currency="SGD", rate=Decimal("1"),
                receivable_id=AR, revenue_id=REV, gst_output_id=None, label="INV-4",
            )


class TestReceiptLines:
    def _lines(self, receipt_rate, issue_rate="1.2934", amount="3750.00"):
        return build_receipt_lines(
            amount=Decimal(amount), currency="USDC", receipt_rate=Decimal(receipt_rate), wallet_id=WALLET,
            receivable_amount=Decimal("3750.00"), receivable_currency="USD",
            receivable_rate=Decimal(issue_rate), receivable_id=AR, fx_gain_loss_id=FX, label="INV-2",
        )

    def test_fx_gain_when_usd_strengthens(self):
        lines = self._lines("1.3000")
        wallet, ar, fx = lines
        assert (wallet.account_id, wallet.currency, wallet.debit) == (WALLET, "USDC", Decimal("3750.00"))
        assert (ar.account_id, ar.currency, ar.credit, ar.fx_rate_to_sgd) == (AR, "USD", Decimal("3750.00"), Decimal("1.2934"))
        # 3750 * (1.3000 - 1.2934) = 24.75
        assert (fx.account_id, fx.credit, fx.debit) == (FX, Decimal("24.75"), 0)
        _validate(lines)

    def test_fx_loss_when_usd_weakens(self):
        lines = self._lines("1.2800")
        fx = lines[-1]
        assert (fx.debit, fx.credit) == (Decimal("50.25"), 0)  # 3750 * 0.0134
        assert fx.description.startswith("FX loss")
        _validate(lines)

    def test_no_fx_line_at_same_rate(self):
        assert len(self._lines("1.2934")) == 2

    def test_fx_difference_requires_mapping(self):
        with pytest.raises(ValueError, match="FX gain/loss account"):
            build_receipt_lines(
                amount=Decimal("100"), currency="USDC", receipt_rate=Decimal("1.30"), wallet_id=WALLET,
                receivable_amount=Decimal("100"), receivable_currency="USD", receivable_rate=Decimal("1.29"),
                receivable_id=AR, fx_gain_loss_id=None, label="INV-9",
            )


class TestFxDifferenceLine:
    def test_sub_cent_difference_is_dropped(self):
        assert fx_difference_line(Decimal("0.004"), FX, "x") is None

    def test_rounds_to_cents(self):
        line = fx_difference_line(Decimal("-12.345"), FX, "x")
        assert line.debit == Decimal("12.35") and line.credit == 0


class TestResolveRate:
    @pytest.mark.asyncio
    async def test_sgd_is_one(self):
        quote = await resolve_fx_rate_to_sgd("SGD", date(2020, 1, 1))
        assert (quote.rate, quote.source) == (Decimal("1"), "functional")

    @pytest.mark.asyncio
    async def test_explicit_rate_is_quantised(self):
        quote = await resolve_fx_rate_to_sgd("USDC", date(2020, 1, 1), Decimal("1.29345678"))
        assert (quote.rate, quote.source) == (Decimal("1.293457"), "manual")

    @pytest.mark.asyncio
    async def test_non_positive_rate_rejected(self):
        with pytest.raises(ValueError, match="positive"):
            await resolve_fx_rate_to_sgd("USD", date(2020, 1, 1), Decimal("0"))

    @pytest.mark.asyncio
    async def test_back_dated_requires_explicit_rate(self):
        past = ledger.today_local() - timedelta(days=3)
        with pytest.raises(ValueError, match="only today's rate"):
            await resolve_fx_rate_to_sgd("USD", past)

    @pytest.mark.asyncio
    async def test_today_without_airwallex_explains(self, monkeypatch):
        monkeypatch.setattr(settings, "AIRWALLEX_CLIENT_ID", None)
        monkeypatch.setattr(settings, "AIRWALLEX_API_KEY", None)
        with pytest.raises(ValueError, match="Airwallex is not configured"):
            await resolve_fx_rate_to_sgd("USDC", ledger.today_local())

    @pytest.mark.asyncio
    async def test_today_fetches_usd_rate_for_stablecoin(self, monkeypatch):
        monkeypatch.setattr(settings, "AIRWALLEX_CLIENT_ID", "id")
        monkeypatch.setattr(settings, "AIRWALLEX_API_KEY", "key")
        provider = SimpleNamespace(
            fetch_fx_rate=AsyncMock(
                return_value=SimpleNamespace(rate="1.2934", raw_data={"currency_pair": "USDSGD"})
            )
        )
        with patch("app.integrations.get_provider", return_value=provider):
            quote = await resolve_fx_rate_to_sgd("USDC", ledger.today_local())
        provider.fetch_fx_rate.assert_awaited_once_with(sell_currency="USD", buy_currency="SGD")
        assert (quote.rate, quote.source) == (Decimal("1.293400"), "airwallex:USD")

    @pytest.mark.asyncio
    async def test_inverted_pair_is_flipped(self, monkeypatch):
        monkeypatch.setattr(settings, "AIRWALLEX_CLIENT_ID", "id")
        monkeypatch.setattr(settings, "AIRWALLEX_API_KEY", "key")
        provider = SimpleNamespace(
            fetch_fx_rate=AsyncMock(return_value=SimpleNamespace(rate="0.8", raw_data={"currency_pair": "SGDUSD"}))
        )
        with patch("app.integrations.get_provider", return_value=provider):
            quote = await resolve_fx_rate_to_sgd("USD", ledger.today_local())
        assert quote.rate == Decimal("1.250000")
