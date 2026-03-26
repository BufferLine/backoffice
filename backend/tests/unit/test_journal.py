"""Unit tests for journal schemas (validation logic)."""

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest

from app.schemas.journal import JournalEntryCreate, JournalLineCreate


# ---------------------------------------------------------------------------
# JournalLineCreate
# ---------------------------------------------------------------------------


class TestJournalLineCreate:
    def test_valid_debit_line(self):
        line = JournalLineCreate(
            account_id=uuid4(), debit=Decimal("100.00"), credit=Decimal("0"), currency="SGD"
        )
        assert line.debit == Decimal("100.00")
        assert line.credit == Decimal("0")

    def test_valid_credit_line(self):
        line = JournalLineCreate(
            account_id=uuid4(), debit=Decimal("0"), credit=Decimal("50.00"), currency="SGD"
        )
        assert line.debit == Decimal("0")
        assert line.credit == Decimal("50.00")

    def test_both_zero_rejected(self):
        with pytest.raises(ValueError, match="debit > 0 or credit > 0"):
            JournalLineCreate(
                account_id=uuid4(), debit=Decimal("0"), credit=Decimal("0"), currency="SGD"
            )

    def test_both_nonzero_rejected(self):
        with pytest.raises(ValueError, match="debit > 0 or credit > 0"):
            JournalLineCreate(
                account_id=uuid4(), debit=Decimal("10"), credit=Decimal("10"), currency="SGD"
            )

    def test_optional_fields(self):
        line = JournalLineCreate(
            account_id=uuid4(), debit=Decimal("100"), credit=Decimal("0"),
            currency="USD", fx_rate_to_sgd=Decimal("1.35"), description="Test"
        )
        assert line.fx_rate_to_sgd == Decimal("1.35")
        assert line.description == "Test"


# ---------------------------------------------------------------------------
# JournalEntryCreate
# ---------------------------------------------------------------------------


class TestJournalEntryCreate:
    def _make_balanced_entry(self, **overrides):
        acct1, acct2 = uuid4(), uuid4()
        defaults = {
            "entry_date": date(2026, 3, 26),
            "description": "Test entry",
            "lines": [
                JournalLineCreate(
                    account_id=acct1, debit=Decimal("1000"), credit=Decimal("0"), currency="SGD"
                ),
                JournalLineCreate(
                    account_id=acct2, debit=Decimal("0"), credit=Decimal("1000"), currency="SGD"
                ),
            ],
        }
        defaults.update(overrides)
        return JournalEntryCreate(**defaults)

    def test_valid_balanced_entry(self):
        entry = self._make_balanced_entry()
        assert len(entry.lines) == 2
        assert entry.description == "Test entry"

    def test_unbalanced_rejected(self):
        acct1, acct2 = uuid4(), uuid4()
        with pytest.raises(ValueError, match="must balance"):
            JournalEntryCreate(
                entry_date=date(2026, 3, 26),
                lines=[
                    JournalLineCreate(
                        account_id=acct1, debit=Decimal("100"), credit=Decimal("0"), currency="SGD"
                    ),
                    JournalLineCreate(
                        account_id=acct2, debit=Decimal("0"), credit=Decimal("50"), currency="SGD"
                    ),
                ],
            )

    def test_single_line_rejected(self):
        with pytest.raises(ValueError, match="at least 2 lines"):
            JournalEntryCreate(
                entry_date=date(2026, 3, 26),
                lines=[
                    JournalLineCreate(
                        account_id=uuid4(), debit=Decimal("100"), credit=Decimal("0"), currency="SGD"
                    ),
                ],
            )

    def test_empty_lines_rejected(self):
        with pytest.raises(ValueError, match="at least 2 lines"):
            JournalEntryCreate(entry_date=date(2026, 3, 26), lines=[])

    def test_three_line_entry(self):
        a1, a2, a3 = uuid4(), uuid4(), uuid4()
        entry = JournalEntryCreate(
            entry_date=date(2026, 3, 26),
            lines=[
                JournalLineCreate(account_id=a1, debit=Decimal("100"), credit=Decimal("0"), currency="SGD"),
                JournalLineCreate(account_id=a2, debit=Decimal("0"), credit=Decimal("60"), currency="SGD"),
                JournalLineCreate(account_id=a3, debit=Decimal("0"), credit=Decimal("40"), currency="SGD"),
            ],
        )
        assert len(entry.lines) == 3

    def test_source_fields(self):
        source_id = uuid4()
        entry = self._make_balanced_entry(source_type="payment", source_id=source_id)
        assert entry.source_type == "payment"
        assert entry.source_id == source_id

    def test_confirmed_flag(self):
        entry = self._make_balanced_entry(is_confirmed=True)
        assert entry.is_confirmed is True

    def test_default_unconfirmed(self):
        entry = self._make_balanced_entry()
        assert entry.is_confirmed is False

    def test_multi_currency_balanced(self):
        """Multi-currency lines still need debit == credit in total."""
        a1, a2 = uuid4(), uuid4()
        # Same amounts even if different currencies — balance check is numeric
        entry = JournalEntryCreate(
            entry_date=date(2026, 3, 26),
            lines=[
                JournalLineCreate(
                    account_id=a1, debit=Decimal("1000"), credit=Decimal("0"),
                    currency="SGD", fx_rate_to_sgd=Decimal("1"),
                ),
                JournalLineCreate(
                    account_id=a2, debit=Decimal("0"), credit=Decimal("1000"),
                    currency="USD", fx_rate_to_sgd=Decimal("1.35"),
                ),
            ],
        )
        assert len(entry.lines) == 2

    def test_precision_balance(self):
        """Decimal precision matters — 100.001 != 100.000."""
        a1, a2 = uuid4(), uuid4()
        with pytest.raises(ValueError, match="must balance"):
            JournalEntryCreate(
                entry_date=date(2026, 3, 26),
                lines=[
                    JournalLineCreate(
                        account_id=a1, debit=Decimal("100.001"), credit=Decimal("0"), currency="SGD"
                    ),
                    JournalLineCreate(
                        account_id=a2, debit=Decimal("0"), credit=Decimal("100.000"), currency="SGD"
                    ),
                ],
            )
