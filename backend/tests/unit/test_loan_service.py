import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.services import loan as loan_svc


class _FakeScalarRows:
    def __init__(self, items):
        self._items = list(items)

    def all(self):
        return list(self._items)

    def __iter__(self):
        return iter(self._items)


class _FakeResult:
    def __init__(self, *, single=None, rows=None, scalar_rows=None):
        self._single = single
        self._rows = list(rows or [])
        self._scalar_rows = list(scalar_rows or [])

    def scalar_one_or_none(self):
        return self._single

    def all(self):
        return list(self._rows)

    def scalars(self):
        return _FakeScalarRows(self._scalar_rows)


class _FakeSession:
    def __init__(self, results):
        self._results = list(results)

    async def execute(self, _query):
        if not self._results:
            raise AssertionError("Unexpected extra execute() call")
        return self._results.pop(0)


@pytest.mark.asyncio
async def test_get_loan_balance_includes_legacy_direct_links():
    loan_id = uuid.uuid4()
    payment_id = uuid.uuid4()
    created_at = datetime(2026, 3, 5, 9, 0, tzinfo=timezone.utc)

    db = _FakeSession(
        [
            _FakeResult(
                single=SimpleNamespace(
                    id=loan_id,
                    principal=Decimal("1000.00"),
                )
            ),
            _FakeResult(rows=[]),
            _FakeResult(
                scalar_rows=[
                    SimpleNamespace(
                        id=payment_id,
                        amount=Decimal("300.00"),
                        notes="Legacy repayment link",
                        created_at=created_at,
                        payment_date=date(2026, 3, 5),
                        bank_reference="LEGACY-LOAN-001",
                    )
                ]
            ),
        ]
    )

    principal, total_allocated, outstanding, allocations = await loan_svc.get_loan_balance(db, loan_id)

    assert principal == Decimal("1000.00")
    assert total_allocated == Decimal("300.00")
    assert outstanding == Decimal("700.00")
    assert len(allocations) == 1
    assert allocations[0].payment_id == payment_id
    assert allocations[0].amount == Decimal("300.00")
    assert allocations[0].notes == "Legacy repayment link"
    assert allocations[0].payment_date == date(2026, 3, 5)
    assert allocations[0].payment_reference == "LEGACY-LOAN-001"


@pytest.mark.asyncio
async def test_get_loan_balance_does_not_double_count_legacy_payment_already_in_allocations():
    loan_id = uuid.uuid4()
    payment_id = uuid.uuid4()
    allocation_id = uuid.uuid4()
    created_at = datetime(2026, 3, 7, 10, 0, tzinfo=timezone.utc)

    db = _FakeSession(
        [
            _FakeResult(
                single=SimpleNamespace(
                    id=loan_id,
                    principal=Decimal("1500.00"),
                )
            ),
            _FakeResult(
                rows=[
                    (
                        SimpleNamespace(
                            id=allocation_id,
                            payment_id=payment_id,
                            amount=Decimal("400.00"),
                            notes="Migrated repayment",
                            created_at=created_at,
                        ),
                        SimpleNamespace(
                            id=payment_id,
                            payment_date=date(2026, 3, 7),
                            bank_reference="ALLOC-001",
                        ),
                    )
                ]
            ),
            _FakeResult(
                scalar_rows=[
                    SimpleNamespace(
                        id=payment_id,
                        amount=Decimal("400.00"),
                        notes="Legacy repayment link",
                        created_at=created_at,
                        payment_date=date(2026, 3, 7),
                        bank_reference="ALLOC-001",
                    )
                ]
            ),
        ]
    )

    principal, total_allocated, outstanding, allocations = await loan_svc.get_loan_balance(db, loan_id)

    assert principal == Decimal("1500.00")
    assert total_allocated == Decimal("400.00")
    assert outstanding == Decimal("1100.00")
    assert len(allocations) == 1
    assert allocations[0].id == allocation_id
    assert allocations[0].payment_id == payment_id
    assert allocations[0].notes == "Migrated repayment"
