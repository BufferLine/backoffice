#!/usr/bin/env python3
"""Generate sample PDFs for all document types.

Usage:
    python scripts/generate-samples.py          # generate to samples/
    python scripts/generate-samples.py --open   # generate and open in default viewer
    python scripts/generate-samples.py --ci     # CI mode: generate + verify non-zero size

No database or running server required — uses embedded sample data.
"""

import argparse
import subprocess
import sys
from datetime import date
from decimal import Decimal
from io import BytesIO
from pathlib import Path

# Ensure backend is importable
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.services.pdf import (
    render_invoice_pdf,
    render_loan_agreement_pdf,
    render_loan_discharge_pdf,
    render_loan_statement_pdf,
    render_payslip_pdf,
)

OUTPUT_DIR = Path(__file__).parent.parent / "samples"


def _make_sample_stamp() -> bytes:
    """Generate a simple company stamp PNG for samples."""
    try:
        from PIL import Image, ImageDraw, ImageFont
        img = Image.new("RGB", (200, 200), (255, 255, 255))
        draw = ImageDraw.Draw(img)
        blue = (26, 86, 219)
        light_blue = (100, 140, 230)
        draw.ellipse([10, 10, 190, 190], outline=blue, width=3)
        draw.ellipse([25, 25, 175, 175], outline=light_blue, width=1)
        try:
            font = ImageFont.truetype("Helvetica", 14)
            font_sm = ImageFont.truetype("Helvetica", 10)
        except OSError:
            font = ImageFont.load_default()
            font_sm = font
        draw.text((50, 60), "SAMPLE", fill=blue, font=font)
        draw.text((42, 80), "COMPANY", fill=blue, font=font)
        draw.text((48, 105), "PTE. LTD.", fill=light_blue, font=font_sm)
        draw.text((55, 125), "SINGAPORE", fill=light_blue, font=font_sm)
        buf = BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except ImportError:
        return b""  # Pillow not available — skip stamp

# ── Sample Data ──────────────────────────────────────────────────────────

COMPANY = {
    "legal_name": "SAMPLE COMPANY PTE. LTD.",
    "uen": "202600000X",
    "address": "1 Sample Street, Singapore 000001",
    "billing_email": "admin@example.com",
    "gst_registration_number": None,
    "website": "https://example.com",
}

THEME = {
    "primary_color": "#1a56db",
    "accent_color": "#374151",
    "font_family": "Helvetica, Arial, sans-serif",
}


def _generate_invoice() -> tuple[str, bytes]:
    stamp_bytes = _make_sample_stamp()
    data = {
        "invoice": {
            "invoice_number": "INV-2026-0001",
            "issue_date": date(2026, 3, 20),
            "due_date": date(2026, 4, 19),
            "currency": "SGD",
            "subtotal_amount": 7500.00,
            "tax_rate": 0.09,
            "tax_amount": 450.00,
            "total_amount": 7950.00,
            "tax_inclusive": False,
            "description": "March 2026 consulting and hosting services",
            "payment_method": None,
            "wallet_address": None,
        },
        "company": {**COMPANY, "gst_registration_number": "M9-0012345-6"},
        "client": {
            "legal_name": "Acme Corp Pte Ltd",
            "billing_email": "ap@acme.com",
            "billing_address": "123 Orchard Road, Singapore 238858",
        },
        "line_items": [
            {
                "description": "Software consulting — 160 hours @ $31.25/hr",
                "quantity": 160,
                "unit_price": 31.25,
                "amount": 5000.00,
                "tax_code": "SR",
                "tax_rate": 0.09,
                "tax_amount": 450.00,
            },
            {
                "description": "Cloud hosting (AWS Singapore) — exported service",
                "quantity": 1,
                "unit_price": 2500.00,
                "amount": 2500.00,
                "tax_code": "ZR",
                "tax_rate": 0,
                "tax_amount": 0,
            },
        ],
        "payment_details": {
            "type": "bank_transfer",
            "bank_name": "DBS Bank",
            "account_name": "SAMPLE COMPANY PTE. LTD.",
            "account_number": "072-901234-5",
            "swift": "DBSSSGSG",
            "reference": "INV-2026-0001",
        },
        "payment_methods": None,
        "has_mixed_tax_codes": True,
        "paynow_qr_uri": None,
    }
    return "invoice-sample.pdf", render_invoice_pdf(data, stamp_bytes=stamp_bytes, theme=THEME)


def _generate_payslip() -> tuple[str, bytes]:
    # Citizen employee — full month, CPF + SDL
    stamp_bytes = _make_sample_stamp()
    gross = 5800.00
    cpf_employee = 1160.00   # 20% — deducted from employee
    cpf_employer = 986.00    # 17% — company pays on top
    sdl = 14.50              # 0.25% — company pays on top
    net = gross - cpf_employee  # 4640.00

    data = {
        "employee": {
            "name": "Jane Lim",
            "employee_id": "EMP-002",
            "email": "jane@example.com",
            "designation": "Software Engineer",
            "department": "Engineering",
            "start_date": date(2026, 1, 6),
            "work_pass_type": "Citizen",
            "bank_name": "OCBC Bank",
            "bank_account": "****8901",
        },
        "payroll": {
            "payslip_number": "PS-2026-03-002",
            "period": "March 2026",
            "month": "2026-03",
            "start_date": date(2026, 3, 1),
            "end_date": date(2026, 3, 31),
            "payment_date": date(2026, 3, 31),
            "days_in_month": 31,
            "days_worked": 31,
            "base_salary": gross,
            "monthly_base_salary": gross,
            "prorated_gross_salary": gross,
            "total_deductions": cpf_employee,
            "net_salary": net,
            "currency": "SGD",
        },
        "earnings": [
            {"description": "Basic Salary", "amount": gross},
        ],
        "deductions": [
            {"description": "CPF Employee Contribution", "amount": cpf_employee, "rate": 0.20},
        ],
        "payment_details": {
            "bank_name": "OCBC Bank",
            "account_name": "Jane Lim",
            "account_number": "****8901",
            "reference": "PS-2026-03-002",
        },
        "employer_costs": [
            {"description": "CPF Employer Contribution", "amount": cpf_employer},
            {"description": "Skills Development Levy (SDL)", "amount": sdl},
        ],
        "total_earnings": gross,
        "total_deductions": cpf_employee,
        "total_employer_costs": cpf_employer + sdl,
        "company": COMPANY,
    }
    return "payslip-sample.pdf", render_payslip_pdf(data, stamp_bytes=stamp_bytes, theme=THEME)


LOAN_BASE = {
    "id": "LOAN-2026-001",
    "loan_type": "shareholder_loan",
    "loan_type_display": "Shareholder Loan",
    "direction": "inbound",
    "direction_display": "Borrowed (Company is Borrower)",
    "counterparty": "John Smith",
    "currency": "SGD",
    "principal": Decimal("60000"),
    "interest_rate": Decimal("0"),
    "interest_type": "simple",
    "start_date": date(2026, 3, 9),
    "maturity_date": date(2027, 3, 9),
    "description": "Shareholder loan for initial company operations and working capital",
}

SAMPLE_REPAYMENTS = [
    {"date": date(2026, 4, 1), "reference": "TRF-REPAY-001", "amount": Decimal("5000"), "notes": "Monthly repayment #1"},
    {"date": date(2026, 5, 1), "reference": "TRF-REPAY-002", "amount": Decimal("5000"), "notes": "Monthly repayment #2"},
    {"date": date(2026, 6, 1), "reference": "TRF-REPAY-003", "amount": Decimal("5000"), "notes": "Monthly repayment #3"},
]


def _generate_loan_agreement() -> tuple[str, bytes]:
    stamp_bytes = _make_sample_stamp()
    data = {
        "loan": LOAN_BASE,
        "company": COMPANY,
        "repayments": None,
        "total_repaid": Decimal("0"),
        "outstanding": Decimal("60000"),
    }
    return "loan-agreement-sample.pdf", render_loan_agreement_pdf(data, stamp_bytes=stamp_bytes, theme=THEME)


def _generate_loan_statement() -> tuple[str, bytes]:
    data = {
        "loan": LOAN_BASE,
        "company": COMPANY,
        "repayments": SAMPLE_REPAYMENTS,
        "total_repaid": Decimal("15000"),
        "outstanding": Decimal("45000"),
        "statement_date": date(2026, 6, 15),
    }
    return "loan-statement-sample.pdf", render_loan_statement_pdf(data, theme=THEME)


def _generate_loan_discharge() -> tuple[str, bytes]:
    stamp_bytes = _make_sample_stamp()
    all_repayments = [
        {"date": date(2026, m, 1), "reference": f"TRF-REPAY-{i:03d}", "amount": Decimal("5000"), "notes": f"Monthly repayment #{i}"}
        for i, m in enumerate(range(4, 13), start=1)
    ] + [
        {"date": date(2027, m, 1), "reference": f"TRF-REPAY-{i:03d}", "amount": Decimal("5000"), "notes": f"Monthly repayment #{i}"}
        for i, m in enumerate(range(1, 4), start=10)
    ]
    data = {
        "loan": {**LOAN_BASE, "status": "repaid"},
        "company": COMPANY,
        "repayments": all_repayments,
        "total_repaid": Decimal("60000"),
        "outstanding": Decimal("0"),
        "discharge_date": date(2027, 3, 9),
    }
    return "loan-discharge-sample.pdf", render_loan_discharge_pdf(data, stamp_bytes=stamp_bytes, theme=THEME)


# ── Main ─────────────────────────────────────────────────────────────────

GENERATORS = [
    ("Invoice", _generate_invoice),
    ("Payslip", _generate_payslip),
    ("Loan Agreement", _generate_loan_agreement),
    ("Loan Statement", _generate_loan_statement),
    ("Loan Discharge", _generate_loan_discharge),
]


def main():
    parser = argparse.ArgumentParser(description="Generate sample PDFs for all document types")
    parser.add_argument("--open", action="store_true", help="Open generated PDFs in default viewer")
    parser.add_argument("--ci", action="store_true", help="CI mode: verify non-zero size, exit 1 on failure")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    passed = 0
    failed = 0

    for doc_type, generator in GENERATORS:
        try:
            filename, pdf_bytes = generator()
            filepath = OUTPUT_DIR / filename
            filepath.write_bytes(pdf_bytes)

            size_kb = len(pdf_bytes) / 1024
            if len(pdf_bytes) == 0:
                print(f"  [FAIL] {doc_type}: empty PDF")
                failed += 1
            else:
                print(f"  [OK]   {doc_type}: {filepath} ({size_kb:.1f} KB)")
                passed += 1

                if args.open:
                    subprocess.run(["open", str(filepath)], check=False)

        except Exception as e:
            print(f"  [FAIL] {doc_type}: {e}")
            failed += 1

    print(f"\n  Results: {passed} ok, {failed} failed → {OUTPUT_DIR}/")

    if args.ci and failed > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
