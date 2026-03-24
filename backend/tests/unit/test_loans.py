"""Unit tests for Loan and PaymentAllocation schemas and models."""

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas.loan import (
    LoanCreate,
    LoanUpdate,
    LoanResponse,
    LoanBalanceResponse,
)
from app.schemas.payment_allocation import (
    AllocationCreate,
    AllocationResponse,
    AllocatePaymentRequest,
)
from app.models.loan import Loan
from app.models.payment_allocation import PaymentAllocation


# ---------------------------------------------------------------------------
# LoanCreate
# ---------------------------------------------------------------------------

class TestLoanSchemas:
    def test_loan_create_all_fields(self):
        loan = LoanCreate(
            loan_type="bank_loan",
            direction="inbound",
            counterparty="DBS Bank",
            currency="SGD",
            principal=Decimal("100000.00"),
            interest_rate=Decimal("0.05"),
            interest_type="simple",
            start_date=date(2026, 1, 1),
            maturity_date=date(2027, 1, 1),
            description="Working capital loan",
        )
        assert loan.loan_type == "bank_loan"
        assert loan.direction == "inbound"
        assert loan.counterparty == "DBS Bank"
        assert loan.currency == "SGD"
        assert loan.principal == Decimal("100000.00")
        assert loan.interest_rate == Decimal("0.05")
        assert loan.interest_type == "simple"
        assert loan.start_date == date(2026, 1, 1)
        assert loan.maturity_date == date(2027, 1, 1)
        assert loan.description == "Working capital loan"

    def test_loan_create_minimal_fields(self):
        loan = LoanCreate(
            loan_type="shareholder_loan",
            direction="inbound",
            counterparty="Alice Tan",
            currency="SGD",
            principal=Decimal("50000"),
            start_date=date(2026, 3, 1),
        )
        assert loan.loan_type == "shareholder_loan"
        assert loan.interest_rate == Decimal("0")
        assert loan.interest_type == "simple"
        assert loan.maturity_date is None
        assert loan.description is None

    def test_loan_create_missing_loan_type_raises(self):
        with pytest.raises(ValidationError):
            LoanCreate(
                direction="inbound",
                counterparty="Alice",
                currency="SGD",
                principal=Decimal("10000"),
                start_date=date(2026, 1, 1),
            )

    def test_loan_create_missing_direction_raises(self):
        with pytest.raises(ValidationError):
            LoanCreate(
                loan_type="bank_loan",
                counterparty="DBS",
                currency="SGD",
                principal=Decimal("10000"),
                start_date=date(2026, 1, 1),
            )

    def test_loan_create_missing_counterparty_raises(self):
        with pytest.raises(ValidationError):
            LoanCreate(
                loan_type="bank_loan",
                direction="inbound",
                currency="SGD",
                principal=Decimal("10000"),
                start_date=date(2026, 1, 1),
            )

    def test_loan_create_missing_principal_raises(self):
        with pytest.raises(ValidationError):
            LoanCreate(
                loan_type="bank_loan",
                direction="inbound",
                counterparty="DBS",
                currency="SGD",
                start_date=date(2026, 1, 1),
            )

    def test_loan_create_missing_start_date_raises(self):
        with pytest.raises(ValidationError):
            LoanCreate(
                loan_type="bank_loan",
                direction="inbound",
                counterparty="DBS",
                currency="SGD",
                principal=Decimal("10000"),
            )

    def test_loan_update_all_optional(self):
        update = LoanUpdate()
        assert update.loan_type is None
        assert update.direction is None
        assert update.counterparty is None
        assert update.currency is None
        assert update.principal is None
        assert update.interest_rate is None
        assert update.interest_type is None
        assert update.start_date is None
        assert update.maturity_date is None
        assert update.description is None

    def test_loan_update_partial(self):
        update = LoanUpdate(description="Updated description", interest_rate=Decimal("0.03"))
        assert update.description == "Updated description"
        assert update.interest_rate == Decimal("0.03")
        assert update.loan_type is None

    def test_loan_response_from_attributes(self):
        loan_id = uuid.uuid4()
        user_id = uuid.uuid4()
        now = datetime.now(tz=timezone.utc)

        class FakeLoan:
            id = loan_id
            loan_type = "director_loan"
            direction = "outbound"
            counterparty = "Bob Lee"
            currency = "SGD"
            principal = Decimal("20000")
            interest_rate = Decimal("0")
            interest_type = "simple"
            start_date = date(2026, 2, 1)
            maturity_date = None
            status = "active"
            description = None
            created_by = user_id
            created_at = now
            updated_at = now

        resp = LoanResponse.model_validate(FakeLoan())
        assert resp.id == loan_id
        assert resp.loan_type == "director_loan"
        assert resp.direction == "outbound"
        assert resp.status == "active"
        assert resp.created_by == user_id

    def test_loan_type_shareholder_loan(self):
        loan = LoanCreate(
            loan_type="shareholder_loan",
            direction="inbound",
            counterparty="Shareholder A",
            currency="SGD",
            principal=Decimal("5000"),
            start_date=date(2026, 1, 1),
        )
        assert loan.loan_type == "shareholder_loan"

    def test_loan_type_director_loan(self):
        loan = LoanCreate(
            loan_type="director_loan",
            direction="outbound",
            counterparty="Director B",
            currency="SGD",
            principal=Decimal("8000"),
            start_date=date(2026, 1, 1),
        )
        assert loan.loan_type == "director_loan"

    def test_loan_type_bank_loan(self):
        loan = LoanCreate(
            loan_type="bank_loan",
            direction="inbound",
            counterparty="OCBC",
            currency="SGD",
            principal=Decimal("200000"),
            start_date=date(2026, 1, 1),
        )
        assert loan.loan_type == "bank_loan"

    def test_direction_inbound(self):
        loan = LoanCreate(
            loan_type="bank_loan",
            direction="inbound",
            counterparty="DBS",
            currency="SGD",
            principal=Decimal("10000"),
            start_date=date(2026, 1, 1),
        )
        assert loan.direction == "inbound"

    def test_direction_outbound(self):
        loan = LoanCreate(
            loan_type="director_loan",
            direction="outbound",
            counterparty="Director C",
            currency="SGD",
            principal=Decimal("10000"),
            start_date=date(2026, 1, 1),
        )
        assert loan.direction == "outbound"


# ---------------------------------------------------------------------------
# AllocationCreate / AllocatePaymentRequest / AllocationResponse
# ---------------------------------------------------------------------------

class TestAllocationSchemas:
    def test_allocation_create_valid(self):
        entity_id = uuid.uuid4()
        alloc = AllocationCreate(
            entity_type="invoice",
            entity_id=entity_id,
            amount=Decimal("500.00"),
        )
        assert alloc.entity_type == "invoice"
        assert alloc.entity_id == entity_id
        assert alloc.amount == Decimal("500.00")
        assert alloc.notes is None

    def test_allocation_create_with_notes(self):
        alloc = AllocationCreate(
            entity_type="loan",
            entity_id=uuid.uuid4(),
            amount=Decimal("1000"),
            notes="Partial repayment",
        )
        assert alloc.notes == "Partial repayment"

    def test_allocation_create_missing_entity_type_raises(self):
        with pytest.raises(ValidationError):
            AllocationCreate(entity_id=uuid.uuid4(), amount=Decimal("100"))

    def test_allocation_create_missing_entity_id_raises(self):
        with pytest.raises(ValidationError):
            AllocationCreate(entity_type="invoice", amount=Decimal("100"))

    def test_allocation_create_missing_amount_raises(self):
        with pytest.raises(ValidationError):
            AllocationCreate(entity_type="invoice", entity_id=uuid.uuid4())

    def test_allocate_payment_request_list(self):
        req = AllocatePaymentRequest(
            allocations=[
                AllocationCreate(entity_type="invoice", entity_id=uuid.uuid4(), amount=Decimal("300")),
                AllocationCreate(entity_type="expense", entity_id=uuid.uuid4(), amount=Decimal("200")),
            ]
        )
        assert len(req.allocations) == 2
        assert req.allocations[0].entity_type == "invoice"
        assert req.allocations[1].entity_type == "expense"

    def test_allocate_payment_request_empty_list(self):
        req = AllocatePaymentRequest(allocations=[])
        assert req.allocations == []

    def test_allocation_response_from_attributes(self):
        _alloc_id = uuid.uuid4()
        _payment_id = uuid.uuid4()
        _entity_id = uuid.uuid4()
        _now = datetime.now(tz=timezone.utc)

        class FakeAllocation:
            id = _alloc_id
            payment_id = _payment_id
            entity_type = "loan"
            entity_id = _entity_id
            amount = Decimal("1500.00")
            notes = "Q1 repayment"
            created_at = _now

        resp = AllocationResponse.model_validate(FakeAllocation())
        assert resp.id == _alloc_id
        assert resp.payment_id == _payment_id
        assert resp.entity_type == "loan"
        assert resp.entity_id == _entity_id
        assert resp.amount == Decimal("1500.00")
        assert resp.notes == "Q1 repayment"

    def test_allocation_response_entity_types(self):
        """entity_type accepts the four valid string values."""
        now = datetime.now(tz=timezone.utc)
        for etype in ("invoice", "expense", "loan", "payroll"):
            class FakeAlloc:
                id = uuid.uuid4()
                payment_id = uuid.uuid4()
                entity_type = etype
                entity_id = uuid.uuid4()
                amount = Decimal("100")
                notes = None
                created_at = now

            resp = AllocationResponse.model_validate(FakeAlloc())
            assert resp.entity_type == etype


# ---------------------------------------------------------------------------
# Loan model
# ---------------------------------------------------------------------------

class TestLoanModel:
    def test_loan_model_has_expected_fields(self):
        expected = {
            "id", "loan_type", "direction", "counterparty", "currency",
            "principal", "interest_rate", "interest_type", "start_date",
            "maturity_date", "status", "description", "document_file_id",
            "metadata_json", "created_by", "created_at", "updated_at",
        }
        mapper_cols = {c.key for c in Loan.__mapper__.columns}
        assert expected <= mapper_cols

    def test_loan_status_default(self):
        col = Loan.__mapper__.columns["status"]
        assert col.default.arg == "active"

    def test_loan_interest_rate_default(self):
        col = Loan.__mapper__.columns["interest_rate"]
        assert col.default.arg == 0

    def test_loan_interest_type_default(self):
        col = Loan.__mapper__.columns["interest_type"]
        assert col.default.arg == "simple"

    def test_loan_tablename(self):
        assert Loan.__tablename__ == "loans"

    def test_loan_loan_type_nullable_false(self):
        assert Loan.__mapper__.columns["loan_type"].nullable is False

    def test_loan_direction_nullable_false(self):
        assert Loan.__mapper__.columns["direction"].nullable is False

    def test_loan_maturity_date_nullable(self):
        assert Loan.__mapper__.columns["maturity_date"].nullable is True

    def test_loan_description_nullable(self):
        assert Loan.__mapper__.columns["description"].nullable is True


# ---------------------------------------------------------------------------
# PaymentAllocation model
# ---------------------------------------------------------------------------

class TestPaymentAllocationModel:
    def test_payment_allocation_has_expected_fields(self):
        expected = {
            "id", "payment_id", "entity_type", "entity_id",
            "amount", "notes", "created_by", "created_at",
        }
        mapper_cols = {c.key for c in PaymentAllocation.__mapper__.columns}
        assert expected <= mapper_cols

    def test_payment_allocation_tablename(self):
        assert PaymentAllocation.__tablename__ == "payment_allocations"

    def test_entity_type_is_string_column(self):
        col = PaymentAllocation.__mapper__.columns["entity_type"]
        from sqlalchemy import String
        assert isinstance(col.type, String)

    def test_entity_type_nullable_false(self):
        assert PaymentAllocation.__mapper__.columns["entity_type"].nullable is False

    def test_entity_id_nullable_false(self):
        assert PaymentAllocation.__mapper__.columns["entity_id"].nullable is False

    def test_amount_nullable_false(self):
        assert PaymentAllocation.__mapper__.columns["amount"].nullable is False

    def test_notes_nullable(self):
        assert PaymentAllocation.__mapper__.columns["notes"].nullable is True

    def test_payment_id_nullable_false(self):
        assert PaymentAllocation.__mapper__.columns["payment_id"].nullable is False
