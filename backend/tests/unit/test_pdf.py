import sys
from types import SimpleNamespace

from app.services import pdf


def test_render_pdf_passes_template_base_url(monkeypatch):
    captured = {}

    class FakeHTML:
        def __init__(self, string, base_url=None):
            captured["string"] = string
            captured["base_url"] = base_url

        def write_pdf(self):
            return b"%PDF-test"

    monkeypatch.setitem(sys.modules, "weasyprint", SimpleNamespace(HTML=FakeHTML))

    result = pdf.render_pdf(
        "loan_agreement.html",
        {
            "loan": {
                "id": "12345678-1234-5678-1234-567812345678",
                "loan_number": None,
                "loan_type_display": "Shareholder Loan",
                "direction_display": "Borrowed (Company is Borrower)",
                "direction": "inbound",
                "counterparty": "Shareholder",
                "currency": "SGD",
                "principal": "1000.00",
                "interest_rate": "0",
                "interest_type": "simple",
                "start_date": "2026-03-01",
                "maturity_date": None,
                "description": None,
            },
            "company": {
                "legal_name": "Test Co Pte Ltd",
                "uen": "202300001A",
                "address": "1 Test Street",
                "billing_email": "billing@test.com",
            },
            "repayments": None,
            "total_repaid": "0.00",
            "outstanding": "1000.00",
        },
    )

    assert result == b"%PDF-test"
    assert captured["base_url"] == str(pdf.TEMPLATE_DIR)
    assert "base.css" in captured["string"]


def _render_invoice_html(monkeypatch, status, payments):
    captured = {}

    class FakeHTML:
        def __init__(self, string, base_url=None):
            captured["string"] = string

        def write_pdf(self):
            return b"%PDF-test"

    monkeypatch.setitem(sys.modules, "weasyprint", SimpleNamespace(HTML=FakeHTML))
    pdf.render_invoice_pdf({
        "invoice": {
            "invoice_number": "BL-2026-001", "issue_date": "2026-11-24", "due_date": "2026-11-24",
            "currency": "USD", "subtotal_amount": "3060", "tax_rate": "0", "tax_amount": "0",
            "total_amount": "3060", "tax_inclusive": False, "description": "Monthly retainer",
            "payment_method": "crypto", "wallet_address": "0xabc", "status": status,
        },
        "company": {"legal_name": "Test Co Pte Ltd", "uen": "202300001A"},
        "client": {"legal_name": "Client Inc."},
        "line_items": [{"description": "Retainer", "quantity": "1", "unit_price": "3060", "amount": "3060",
                        "tax_code": "OS", "tax_rate": "0", "tax_amount": "0"}],
        "payment_details": None,
        "payment_methods": [{"type": "crypto", "nickname": None, "chain_id": "base", "account_name": "Test Co",
                             "wallet_address": "0xabc"}],
        "payments": payments,
        "has_mixed_tax_codes": False,
    })
    return captured["string"]


def test_paid_invoice_pdf_shows_payments_instead_of_instructions(monkeypatch):
    html = _render_invoice_html(monkeypatch, "paid", [{
        "payment_date": "2026-11-24", "amount": "3060", "currency": "USD",
        "method": "Applied from customer advance", "tx_hash": "0xdeadbeef", "chain_id": None,
        "notes": "Received 3 Apr 2026 in USDT on the Company's behalf",
    }])
    assert "PAID" in html and "Payments Received" in html and "Paid in full." in html
    assert "Applied from customer advance" in html and "Received 3 Apr 2026" in html and "0xdeadbeef" in html
    assert "Payment Details" not in html and "Wallet Address" not in html


def test_issued_invoice_pdf_keeps_payment_instructions(monkeypatch):
    html = _render_invoice_html(monkeypatch, "issued", [])
    assert "Payment Details" in html and "Wallet Address" in html
    assert "Payments Received" not in html and "paid-badge\">PAID" not in html
