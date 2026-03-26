"""Unit tests for schemas, config validation, and utility functions."""

import uuid
from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.schemas.user import (
    LoginRequest,
    RefreshRequest,
    UserCreate,
    _validate_password,
)
from app.schemas.invoice import (
    ClientCreate,
    InvoiceCreate,
    LineItemCreate,
)
from app.schemas.payment import PaymentCreate, PaymentLinkRequest
from app.schemas.expense import ExpenseCreate
from app.schemas.account import AccountCreate, AccountUpdate
from app.services.file_storage import safe_filename, ALLOWED_MIME_TYPES
from app.services.pdf import _money, _pct
from app.config import _WEAK_JWT_SECRETS


# ---------------------------------------------------------------------------
# _validate_password
# ---------------------------------------------------------------------------

class TestValidatePassword:
    def test_valid_password(self):
        assert _validate_password("securepass") == "securepass"

    def test_exactly_8_chars(self):
        assert _validate_password("abcdefgh") == "abcdefgh"

    def test_too_short_raises(self):
        with pytest.raises(ValueError, match="at least 8 characters"):
            _validate_password("short")

    def test_whitespace_only_raises(self):
        with pytest.raises(ValueError, match="at least 8 characters"):
            _validate_password("        ")

    def test_strips_leading_trailing_whitespace_before_length_check(self):
        # " abc " → stripped to "abc" (3 chars) → too short
        with pytest.raises(ValueError, match="at least 8 characters"):
            _validate_password("  abc  ")

    def test_valid_password_with_surrounding_whitespace_stripped(self):
        # "  password  " → stripped to "password" (8 chars) → valid
        result = _validate_password("  password  ")
        assert result == "password"

    def test_valid_long_password(self):
        pw = "a_very_long_password_1234!"
        assert _validate_password(pw) == pw


# ---------------------------------------------------------------------------
# UserCreate
# ---------------------------------------------------------------------------

class TestUserCreate:
    def test_valid_creation(self):
        user = UserCreate(email="alice@example.com", name="Alice", password="securepass")
        assert user.email == "alice@example.com"
        assert user.name == "Alice"
        assert user.password == "securepass"

    def test_invalid_email_raises(self):
        with pytest.raises(ValidationError):
            UserCreate(email="not-an-email", name="Alice", password="securepass")

    def test_short_password_raises(self):
        with pytest.raises(ValidationError):
            UserCreate(email="alice@example.com", name="Alice", password="short")

    def test_whitespace_only_password_raises(self):
        with pytest.raises(ValidationError):
            UserCreate(email="alice@example.com", name="Alice", password="       ")

    def test_missing_email_raises(self):
        with pytest.raises(ValidationError):
            UserCreate(name="Alice", password="securepass")

    def test_missing_name_raises(self):
        with pytest.raises(ValidationError):
            UserCreate(email="alice@example.com", password="securepass")

    def test_missing_password_raises(self):
        with pytest.raises(ValidationError):
            UserCreate(email="alice@example.com", name="Alice")


# ---------------------------------------------------------------------------
# LoginRequest
# ---------------------------------------------------------------------------

class TestLoginRequest:
    def test_valid(self):
        req = LoginRequest(email="bob@example.com", password="anypassword")
        assert req.email == "bob@example.com"
        assert req.password == "anypassword"

    def test_invalid_email_raises(self):
        with pytest.raises(ValidationError):
            LoginRequest(email="not-valid", password="anypassword")

    def test_missing_password_raises(self):
        with pytest.raises(ValidationError):
            LoginRequest(email="bob@example.com")


# ---------------------------------------------------------------------------
# RefreshRequest
# ---------------------------------------------------------------------------

class TestRefreshRequest:
    def test_valid(self):
        req = RefreshRequest(refresh_token="some.jwt.token")
        assert req.refresh_token == "some.jwt.token"

    def test_missing_refresh_token_raises(self):
        with pytest.raises(ValidationError):
            RefreshRequest()


# ---------------------------------------------------------------------------
# safe_filename
# ---------------------------------------------------------------------------

class TestSafeFilename:
    def test_normal_name(self):
        assert safe_filename("invoice_2026.pdf") == "invoice_2026.pdf"

    def test_name_with_spaces(self):
        result = safe_filename("my file name.pdf")
        assert result == "my file name.pdf"

    def test_name_with_double_quotes_replaced(self):
        result = safe_filename('file"name.pdf')
        assert '"' not in result

    def test_name_with_newline_stripped(self):
        result = safe_filename("file\nname.pdf")
        assert "\n" not in result

    def test_name_with_carriage_return_stripped(self):
        result = safe_filename("file\rname.pdf")
        assert "\r" not in result

    def test_name_with_null_byte_stripped(self):
        result = safe_filename("file\x00name.pdf")
        assert "\x00" not in result

    def test_special_chars_replaced(self):
        result = safe_filename("file<>|:*.pdf")
        assert "<" not in result
        assert ">" not in result
        assert "|" not in result
        assert ":" not in result
        assert "*" not in result

    def test_unicode_name(self):
        # Unicode letters are kept (\w matches unicode by default in Python re)
        result = safe_filename("발행서.pdf")
        assert result  # non-empty
        assert "\n" not in result
        assert "\r" not in result

    def test_empty_name_returns_download(self):
        assert safe_filename("") == "download"

    def test_only_dots_and_spaces_returns_download(self):
        # After stripping leading/trailing spaces and dots the result is empty
        assert safe_filename("  ..  ") == "download"

    def test_path_traversal_chars_replaced(self):
        result = safe_filename("../../etc/passwd")
        assert ".." not in result or "/" not in result


# ---------------------------------------------------------------------------
# ALLOWED_MIME_TYPES
# ---------------------------------------------------------------------------

class TestAllowedMimeTypes:
    def test_pdf_allowed(self):
        assert "application/pdf" in ALLOWED_MIME_TYPES

    def test_png_allowed(self):
        assert "image/png" in ALLOWED_MIME_TYPES

    def test_jpeg_allowed(self):
        assert "image/jpeg" in ALLOWED_MIME_TYPES

    def test_gif_allowed(self):
        assert "image/gif" in ALLOWED_MIME_TYPES

    def test_webp_allowed(self):
        assert "image/webp" in ALLOWED_MIME_TYPES

    def test_svg_allowed(self):
        assert "image/svg+xml" in ALLOWED_MIME_TYPES

    def test_csv_allowed(self):
        assert "text/csv" in ALLOWED_MIME_TYPES

    def test_xlsx_allowed(self):
        assert "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" in ALLOWED_MIME_TYPES

    def test_xls_allowed(self):
        assert "application/vnd.ms-excel" in ALLOWED_MIME_TYPES

    def test_executable_not_allowed(self):
        assert "application/x-executable" not in ALLOWED_MIME_TYPES

    def test_javascript_not_allowed(self):
        assert "application/javascript" not in ALLOWED_MIME_TYPES

    def test_html_not_allowed(self):
        assert "text/html" not in ALLOWED_MIME_TYPES


# ---------------------------------------------------------------------------
# _money filter
# ---------------------------------------------------------------------------

class TestMoneyFilter:
    def test_whole_number(self):
        assert _money(Decimal("100")) == "100.00"

    def test_decimal_value(self):
        assert _money(Decimal("1234.56")) == "1234.56"

    def test_zero(self):
        assert _money(Decimal("0")) == "0.00"

    def test_rounds_to_two_decimal_places(self):
        assert _money(Decimal("9.999")) == "10.00"

    def test_large_amount(self):
        assert _money(Decimal("999999.99")) == "999999.99"

    def test_from_string_input(self):
        assert _money("123.45") == "123.45"

    def test_from_float_input(self):
        assert _money(50.0) == "50.00"

    def test_custom_precision_4(self):
        assert _money(Decimal("1.23456"), precision=4) == "1.2346"

    def test_custom_precision_0(self):
        assert _money(Decimal("99.9"), precision=0) == "100"


# ---------------------------------------------------------------------------
# _pct filter
# ---------------------------------------------------------------------------

class TestPctFilter:
    def test_nine_percent(self):
        assert _pct(Decimal("0.09")) == "9.00"

    def test_zero_percent(self):
        assert _pct(Decimal("0")) == "0.00"

    def test_one_hundred_percent(self):
        assert _pct(Decimal("1")) == "100.00"

    def test_from_string_input(self):
        assert _pct("0.09") == "9.00"

    def test_from_float_input(self):
        assert _pct(0.07) == "7.00"

    def test_fractional_percent(self):
        # 0.175 → 17.50
        assert _pct(Decimal("0.175")) == "17.50"

    def test_small_rate(self):
        # 0.001 → 0.10
        assert _pct(Decimal("0.001")) == "0.10"


# ---------------------------------------------------------------------------
# Invoice schemas
# ---------------------------------------------------------------------------

class TestInvoiceCreate:
    def test_required_fields(self):
        client_id = uuid.uuid4()
        inv = InvoiceCreate(client_id=client_id, currency="SGD")
        assert inv.client_id == client_id
        assert inv.currency == "SGD"

    def test_optional_fields_default_to_none_or_false(self):
        inv = InvoiceCreate(client_id=uuid.uuid4(), currency="USD")
        assert inv.description is None
        assert inv.payment_method is None
        assert inv.wallet_address is None
        assert inv.tax_inclusive is False
        assert inv.payment_method_id is None
        assert inv.payment_method_ids is None

    def test_with_all_fields(self):
        pm_id = uuid.uuid4()
        pm_ids = [uuid.uuid4(), uuid.uuid4()]
        inv = InvoiceCreate(
            client_id=uuid.uuid4(),
            currency="SGD",
            description="Consulting services",
            payment_method="bank_transfer",
            wallet_address="0xABCDEF",
            tax_inclusive=True,
            payment_method_id=pm_id,
            payment_method_ids=pm_ids,
        )
        assert inv.description == "Consulting services"
        assert inv.tax_inclusive is True
        assert inv.payment_method_id == pm_id
        assert len(inv.payment_method_ids) == 2

    def test_missing_client_id_raises(self):
        with pytest.raises(ValidationError):
            InvoiceCreate(currency="SGD")

    def test_missing_currency_raises(self):
        with pytest.raises(ValidationError):
            InvoiceCreate(client_id=uuid.uuid4())


class TestLineItemCreate:
    def test_valid_line_item(self):
        item = LineItemCreate(
            description="Service fee",
            quantity=Decimal("2"),
            unit_price=Decimal("500.00"),
        )
        assert item.description == "Service fee"
        assert item.tax_code == "SR"
        assert item.tax_rate is None

    def test_default_tax_code_is_sr(self):
        item = LineItemCreate(
            description="Item",
            quantity=Decimal("1"),
            unit_price=Decimal("100"),
        )
        assert item.tax_code == "SR"

    def test_custom_tax_code(self):
        item = LineItemCreate(
            description="Exempt item",
            quantity=Decimal("1"),
            unit_price=Decimal("100"),
            tax_code="ES33",
        )
        assert item.tax_code == "ES33"

    def test_missing_description_raises(self):
        with pytest.raises(ValidationError):
            LineItemCreate(quantity=Decimal("1"), unit_price=Decimal("100"))

    def test_missing_quantity_raises(self):
        with pytest.raises(ValidationError):
            LineItemCreate(description="Item", unit_price=Decimal("100"))

    def test_missing_unit_price_raises(self):
        with pytest.raises(ValidationError):
            LineItemCreate(description="Item", quantity=Decimal("1"))


class TestClientCreate:
    def test_only_required_field(self):
        client = ClientCreate(legal_name="ACME Pte Ltd")
        assert client.legal_name == "ACME Pte Ltd"
        assert client.billing_email is None
        assert client.payment_terms_days is None

    def test_all_fields(self):
        client = ClientCreate(
            legal_name="ACME Pte Ltd",
            billing_email="billing@acme.com",
            billing_address="1 Orchard Rd, Singapore",
            default_currency="SGD",
            payment_terms_days=30,
            preferred_payment_method="bank_transfer",
            wallet_address="0xDEADBEEF",
        )
        assert client.payment_terms_days == 30
        assert client.default_currency == "SGD"

    def test_missing_legal_name_raises(self):
        with pytest.raises(ValidationError):
            ClientCreate()


# ---------------------------------------------------------------------------
# Payment schemas
# ---------------------------------------------------------------------------

class TestPaymentCreate:
    def test_required_fields(self):
        payment = PaymentCreate(payment_type="invoice", currency="SGD", amount=Decimal("100.00"))
        assert payment.payment_type == "invoice"
        assert payment.currency == "SGD"
        assert payment.amount == Decimal("100.00")

    def test_optional_fields_default_to_none(self):
        payment = PaymentCreate(payment_type="expense", currency="USD", amount=Decimal("50"))
        assert payment.related_entity_type is None
        assert payment.related_entity_id is None
        assert payment.payment_date is None
        assert payment.fx_rate_to_sgd is None
        assert payment.tx_hash is None
        assert payment.bank_reference is None
        assert payment.notes is None
        assert payment.idempotency_key is None

    def test_missing_currency_raises(self):
        with pytest.raises(ValidationError):
            PaymentCreate(payment_type="invoice", amount=Decimal("100"))

    def test_missing_amount_raises(self):
        with pytest.raises(ValidationError):
            PaymentCreate(payment_type="invoice", currency="SGD")


class TestPaymentLinkRequest:
    def test_valid(self):
        entity_id = uuid.uuid4()
        req = PaymentLinkRequest(related_entity_type="invoice", related_entity_id=entity_id)
        assert req.related_entity_type == "invoice"
        assert req.related_entity_id == entity_id

    def test_missing_entity_type_raises(self):
        with pytest.raises(ValidationError):
            PaymentLinkRequest(related_entity_id=uuid.uuid4())

    def test_missing_entity_id_raises(self):
        with pytest.raises(ValidationError):
            PaymentLinkRequest(related_entity_type="invoice")


# ---------------------------------------------------------------------------
# Expense schemas
# ---------------------------------------------------------------------------

class TestExpenseCreate:
    def test_required_fields(self):
        from datetime import date
        exp = ExpenseCreate(expense_date=date(2026, 1, 15), currency="SGD", amount=Decimal("45.00"))
        assert exp.currency == "SGD"
        assert exp.amount == Decimal("45.00")
        assert exp.reimbursable is False

    def test_optional_fields_default(self):
        from datetime import date
        exp = ExpenseCreate(expense_date=date(2026, 1, 15), currency="SGD", amount=Decimal("10"))
        assert exp.vendor is None
        assert exp.category is None
        assert exp.payment_method is None
        assert exp.notes is None
        assert exp.reimbursable is False

    def test_all_fields(self):
        from datetime import date
        exp = ExpenseCreate(
            expense_date=date(2026, 3, 1),
            vendor="Grab",
            category="transport",
            currency="SGD",
            amount=Decimal("12.50"),
            payment_method="corporate_card",
            reimbursable=True,
            notes="Client meeting",
        )
        assert exp.vendor == "Grab"
        assert exp.reimbursable is True

    def test_missing_expense_date_raises(self):
        with pytest.raises(ValidationError):
            ExpenseCreate(currency="SGD", amount=Decimal("10"))

    def test_missing_currency_raises(self):
        from datetime import date
        with pytest.raises(ValidationError):
            ExpenseCreate(expense_date=date(2026, 1, 1), amount=Decimal("10"))

    def test_missing_amount_raises(self):
        from datetime import date
        with pytest.raises(ValidationError):
            ExpenseCreate(expense_date=date(2026, 1, 1), currency="SGD")


# ---------------------------------------------------------------------------
# Config: _WEAK_JWT_SECRETS
# ---------------------------------------------------------------------------

class TestWeakJwtSecrets:
    def test_change_me_in_production_is_weak(self):
        assert "change-me-in-production" in _WEAK_JWT_SECRETS

    def test_dev_jwt_secret_is_weak(self):
        assert "dev_jwt_secret_change_in_production_32chars" in _WEAK_JWT_SECRETS

    def test_is_frozenset(self):
        assert isinstance(_WEAK_JWT_SECRETS, frozenset)

    def test_strong_secret_not_in_weak_set(self):
        assert "a_very_secure_random_jwt_secret_abc123" not in _WEAK_JWT_SECRETS


# ---------------------------------------------------------------------------
# AccountCreate / AccountUpdate — account_class validation
# ---------------------------------------------------------------------------

class TestAccountClassValidation:
    """Ensure account_class only accepts valid accounting classes."""

    _BASE = {
        "name": "Test Account",
        "account_type": "virtual",
        "currency": "SGD",
        "opening_balance_date": "2026-01-01",
    }

    @pytest.mark.parametrize("cls", ["asset", "liability", "equity", "revenue", "expense"])
    def test_valid_account_class_accepted(self, cls: str):
        acct = AccountCreate(**{**self._BASE, "account_class": cls})
        assert acct.account_class == cls

    def test_none_account_class_accepted(self):
        acct = AccountCreate(**self._BASE)
        assert acct.account_class is None

    def test_invalid_account_class_rejected(self):
        with pytest.raises(ValidationError):
            AccountCreate(**{**self._BASE, "account_class": "invalid"})

    def test_update_valid_account_class(self):
        update = AccountUpdate(account_class="liability")
        assert update.account_class == "liability"

    def test_update_invalid_account_class_rejected(self):
        with pytest.raises(ValidationError):
            AccountUpdate(account_class="bad_value")
