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
