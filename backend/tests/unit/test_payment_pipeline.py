"""Unit tests for payment pipeline automation: reference numbers, match confidence, entity prefixes."""

import uuid
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.services.bank_reconciliation import _compute_match_confidence
from app.services.payment import _ENTITY_PREFIX_MAP


# ---------------------------------------------------------------------------
# Reference number prefix mapping
# ---------------------------------------------------------------------------


class TestEntityPrefixMap:
    def test_payroll_run_prefix(self):
        assert _ENTITY_PREFIX_MAP["payroll_run"] == "PS"

    def test_invoice_prefix(self):
        assert _ENTITY_PREFIX_MAP["invoice"] == "INV"

    def test_loan_prefix(self):
        assert _ENTITY_PREFIX_MAP["loan"] == "LN"

    def test_expense_prefix(self):
        assert _ENTITY_PREFIX_MAP["expense"] == "EXP"

    def test_unknown_entity_not_in_map(self):
        assert "unknown" not in _ENTITY_PREFIX_MAP


# ---------------------------------------------------------------------------
# Match confidence scoring
# ---------------------------------------------------------------------------


def _make_tx(**kwargs):
    """Create a mock BankTransaction."""
    defaults = {
        "id": uuid.uuid4(),
        "tx_date": date(2026, 3, 15),
        "amount": 5000,
        "currency": "SGD",
        "reference": None,
        "counterparty": None,
        "description": None,
        "match_status": "unmatched",
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _make_payment(**kwargs):
    """Create a mock Payment."""
    defaults = {
        "id": uuid.uuid4(),
        "payment_date": date(2026, 3, 15),
        "amount": 5000,
        "currency": "SGD",
        "reference_number": None,
        "bank_reference": None,
        "notes": None,
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


class TestComputeMatchConfidence:
    def test_base_confidence_amount_currency_only(self):
        tx = _make_tx()
        payment = _make_payment()
        confidence = _compute_match_confidence(tx, payment)
        assert confidence == pytest.approx(0.6)  # 0.5 base + 0.1 date proximity

    def test_reference_number_exact_match_boosts_confidence(self):
        tx = _make_tx(reference="BL-PS-2026-0001")
        payment = _make_payment(reference_number="BL-PS-2026-0001")
        confidence = _compute_match_confidence(tx, payment)
        assert confidence >= 0.9

    def test_reference_number_partial_match(self):
        tx = _make_tx(reference="Payment ref BL-PS-2026-0001")
        payment = _make_payment(reference_number="BL-PS-2026-0001")
        confidence = _compute_match_confidence(tx, payment)
        assert confidence >= 0.9

    def test_bank_reference_match_without_reference_number(self):
        tx = _make_tx(reference="TRANSFER-12345")
        payment = _make_payment(bank_reference="TRANSFER-12345")
        confidence = _compute_match_confidence(tx, payment)
        assert confidence >= 0.6

    def test_counterparty_match_adds_confidence(self):
        tx = _make_tx(counterparty="John Doe")
        payment = _make_payment(notes="Payment for John Doe salary")
        confidence = _compute_match_confidence(tx, payment)
        assert confidence >= 0.7

    def test_date_proximity_within_2_days_adds_bonus(self):
        tx = _make_tx(tx_date=date(2026, 3, 16))
        payment = _make_payment(payment_date=date(2026, 3, 15))
        confidence = _compute_match_confidence(tx, payment)
        assert confidence >= 0.6

    def test_date_far_apart_no_bonus(self):
        tx = _make_tx(tx_date=date(2026, 3, 20))
        payment = _make_payment(payment_date=date(2026, 3, 15))
        confidence = _compute_match_confidence(tx, payment)
        assert confidence == pytest.approx(0.5)  # No date bonus

    def test_all_signals_match_gives_high_confidence(self):
        tx = _make_tx(
            reference="BL-PS-2026-0001",
            counterparty="Jane Smith",
            tx_date=date(2026, 3, 15),
        )
        payment = _make_payment(
            reference_number="BL-PS-2026-0001",
            bank_reference="BL-PS-2026-0001",
            notes="Salary for Jane Smith",
            payment_date=date(2026, 3, 15),
        )
        confidence = _compute_match_confidence(tx, payment)
        assert confidence == pytest.approx(1.0)

    def test_confidence_capped_at_1(self):
        tx = _make_tx(
            reference="BL-PS-2026-0001",
            counterparty="Jane",
            tx_date=date(2026, 3, 15),
        )
        payment = _make_payment(
            reference_number="BL-PS-2026-0001",
            bank_reference="OTHER-REF",
            notes="Jane payment",
            payment_date=date(2026, 3, 15),
        )
        confidence = _compute_match_confidence(tx, payment)
        assert confidence <= 1.0

    def test_no_reference_no_counterparty_low_confidence(self):
        tx = _make_tx()
        payment = _make_payment(payment_date=date(2026, 3, 20))  # Far date
        confidence = _compute_match_confidence(tx, payment)
        assert confidence < 0.8  # Should not auto-match

    def test_case_insensitive_reference_match(self):
        tx = _make_tx(reference="bl-ps-2026-0001")
        payment = _make_payment(reference_number="BL-PS-2026-0001")
        confidence = _compute_match_confidence(tx, payment)
        assert confidence >= 0.9

    def test_null_payment_date_no_date_bonus(self):
        tx = _make_tx()
        payment = _make_payment(payment_date=None)
        confidence = _compute_match_confidence(tx, payment)
        assert confidence == pytest.approx(0.5)
