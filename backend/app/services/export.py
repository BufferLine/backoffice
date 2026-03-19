import hashlib
import io
import json
import uuid
import zipfile
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.export_formatters import get_formatter
from app.models.company import CompanySettings
from app.models.export import ExportPack
from app.models.expense import Expense
from app.models.file import File
from app.models.invoice import Invoice
from app.models.payment import Payment
from app.models.payroll import PayrollRun
from app.schemas.export import ExportValidationResult
from app.services.audit import AuditService
from app.services.file_storage import FileStorageService


def _parse_month(month_str: str) -> date:
    """Parse YYYY-MM string to the first day of that month as a date."""
    year, month_num = map(int, month_str.split("-"))
    return date(year, month_num, 1)


async def _get_company_settings(db: AsyncSession) -> Optional[CompanySettings]:
    result = await db.execute(select(CompanySettings).limit(1))
    return result.scalar_one_or_none()


async def validate_month(db: AsyncSession, month_str: str) -> ExportValidationResult:
    """Check completeness for a given month."""
    month_date = _parse_month(month_str)

    # --- Invoices ---
    inv_result = await db.execute(
        select(Invoice).where(
            func.to_char(Invoice.issue_date, "YYYY-MM") == month_str
        )
    )
    all_invoices = list(inv_result.scalars().all())
    invoices_total = len(all_invoices)
    invoices_issued_or_paid = sum(1 for i in all_invoices if i.status in ("issued", "paid"))
    invoices_draft = sum(1 for i in all_invoices if i.status == "draft")

    # --- Payroll ---
    pay_result = await db.execute(
        select(PayrollRun).where(PayrollRun.month == month_date)
    )
    all_payroll = list(pay_result.scalars().all())
    payroll_total = len(all_payroll)
    payroll_finalized_or_paid = sum(1 for r in all_payroll if r.status in ("finalized", "paid"))
    payroll_pending = sum(1 for r in all_payroll if r.status not in ("finalized", "paid"))

    # --- Expenses ---
    exp_result = await db.execute(
        select(Expense).where(
            func.to_char(Expense.expense_date, "YYYY-MM") == month_str
        )
    )
    all_expenses = list(exp_result.scalars().all())
    expenses_total = len(all_expenses)
    expenses_confirmed = sum(1 for e in all_expenses if e.status in ("confirmed", "reimbursed"))
    expenses_draft = sum(1 for e in all_expenses if e.status == "draft")

    # --- Missing evidence ---
    missing_evidence: list[dict] = []

    # Invoices without PDF
    for inv in all_invoices:
        if inv.status in ("issued", "paid") and inv.issued_pdf_file_id is None:
            missing_evidence.append({
                "entity_type": "invoice",
                "entity_id": str(inv.id),
                "description": f"Invoice {inv.invoice_number} has no PDF",
            })

    # Payroll runs without payslip
    for run in all_payroll:
        if run.status in ("finalized", "paid") and run.payslip_file_id is None:
            missing_evidence.append({
                "entity_type": "payroll_run",
                "entity_id": str(run.id),
                "description": "Payroll run has no payslip PDF",
            })

    # Payments without proof (for the month)
    pay_month_result = await db.execute(
        select(Payment).where(
            func.to_char(Payment.payment_date, "YYYY-MM") == month_str
        )
    )
    all_payments = list(pay_month_result.scalars().all())
    for pmt in all_payments:
        if pmt.proof_file_id is None:
            missing_evidence.append({
                "entity_type": "payment",
                "entity_id": str(pmt.id),
                "description": "Payment has no proof file",
            })

    is_complete = (
        invoices_draft == 0
        and payroll_pending == 0
        and expenses_draft == 0
        and len(missing_evidence) == 0
    )

    return ExportValidationResult(
        month=month_str,
        is_complete=is_complete,
        invoices_total=invoices_total,
        invoices_issued_or_paid=invoices_issued_or_paid,
        invoices_draft=invoices_draft,
        payroll_total=payroll_total,
        payroll_finalized_or_paid=payroll_finalized_or_paid,
        payroll_pending=payroll_pending,
        expenses_total=expenses_total,
        expenses_confirmed=expenses_confirmed,
        expenses_draft=expenses_draft,
        missing_evidence=missing_evidence,
    )


async def generate_month_end_pack(
    db: AsyncSession,
    month_str: str,
    force: bool,
    user_id: uuid.UUID,
    file_storage: FileStorageService,
) -> ExportPack:
    """Generate a month-end export pack ZIP and store it."""
    month_date = _parse_month(month_str)

    # 1. Validate first
    validation = await validate_month(db, month_str)
    if not validation.is_complete and not force:
        raise ValueError(
            f"Month {month_str} is not complete. Use force=True to override. "
            f"Issues: {len(validation.missing_evidence)} missing evidence, "
            f"{validation.invoices_draft} draft invoices, "
            f"{validation.payroll_pending} pending payroll runs, "
            f"{validation.expenses_draft} draft expenses."
        )

    # 2. Determine version number
    version_result = await db.execute(
        select(func.max(ExportPack.version)).where(ExportPack.month == month_date)
    )
    max_version = version_result.scalar_one_or_none() or 0
    new_version = max_version + 1

    # 3. Create ExportPack record with status="generating"
    pack = ExportPack(
        month=month_date,
        version=new_version,
        status="generating",
        created_by=user_id,
        validation_summary_json=validation.model_dump(),
    )
    db.add(pack)
    await db.flush()
    await db.refresh(pack)

    try:
        # 4. Gather all data
        company = await _get_company_settings(db)

        # Invoices with line items and client
        inv_result = await db.execute(
            select(Invoice)
            .where(
                Invoice.status.in_(["issued", "paid"]),
                func.to_char(Invoice.issue_date, "YYYY-MM") == month_str,
            )
            .options(selectinload(Invoice.line_items), selectinload(Invoice.client))
        )
        invoices = list(inv_result.scalars().all())

        # Payroll runs with employee
        payroll_result = await db.execute(
            select(PayrollRun)
            .where(
                PayrollRun.month == month_date,
                PayrollRun.status.in_(["finalized", "paid"]),
            )
            .options(selectinload(PayrollRun.employee))
        )
        payroll_runs = list(payroll_result.scalars().all())

        # Expenses confirmed/reimbursed
        exp_result = await db.execute(
            select(Expense).where(
                Expense.status.in_(["confirmed", "reimbursed"]),
                func.to_char(Expense.expense_date, "YYYY-MM") == month_str,
            )
        )
        expenses = list(exp_result.scalars().all())

        # Payments for the month
        pmt_result = await db.execute(
            select(Payment).where(
                func.to_char(Payment.payment_date, "YYYY-MM") == month_str,
            )
        )
        payments = list(pmt_result.scalars().all())

        # 5. Format CSVs
        formatter = get_formatter("generic_csv")

        invoice_rows = [
            {
                "invoice_number": inv.invoice_number,
                "client_name": inv.client.legal_name if inv.client else "",
                "issue_date": inv.issue_date,
                "due_date": inv.due_date,
                "currency": inv.currency,
                "subtotal_amount": inv.subtotal_amount,
                "tax_amount": inv.tax_amount,
                "total_amount": inv.total_amount,
                "status": inv.status,
                "payment_method": inv.payment_method,
            }
            for inv in invoices
        ]
        invoices_csv = formatter.format_invoices(invoice_rows)

        payroll_rows = [
            {
                "employee_name": run.employee.name if run.employee else "",
                "month": run.month,
                "start_date": run.start_date,
                "end_date": run.end_date,
                "days_worked": run.days_worked,
                "days_in_month": run.days_in_month,
                "currency": run.currency,
                "monthly_base_salary": run.monthly_base_salary,
                "prorated_gross_salary": run.prorated_gross_salary,
                "total_deductions": run.total_deductions,
                "net_salary": run.net_salary,
                "status": run.status,
            }
            for run in payroll_runs
        ]
        payroll_csv = formatter.format_payroll(payroll_rows)

        expense_rows = [
            {
                "expense_date": exp.expense_date,
                "vendor": exp.vendor,
                "category": exp.category,
                "currency": exp.currency,
                "amount": exp.amount,
                "payment_method": exp.payment_method,
                "reimbursable": exp.reimbursable,
                "status": exp.status,
                "notes": exp.notes,
            }
            for exp in expenses
        ]
        expenses_csv = formatter.format_expenses(expense_rows)

        payment_rows = [
            {
                "payment_date": pmt.payment_date,
                "payment_type": pmt.payment_type,
                "currency": pmt.currency,
                "amount": pmt.amount,
                "fx_rate_to_sgd": pmt.fx_rate_to_sgd,
                "sgd_value": pmt.sgd_value,
                "related_entity_type": pmt.related_entity_type,
                "related_entity_id": str(pmt.related_entity_id) if pmt.related_entity_id else "",
                "tx_hash": pmt.tx_hash,
                "bank_reference": pmt.bank_reference,
            }
            for pmt in payments
        ]
        payments_csv = formatter.format_payments(payment_rows)

        # 6. Collect associated PDF files from storage
        # Build list of (zip_path, storage_key, file_id) for files to include
        pdf_file_entries: list[tuple[str, str]] = []  # (zip_path, storage_key)

        for inv in invoices:
            if inv.issued_pdf_file_id:
                file_result = await db.execute(
                    select(File).where(File.id == inv.issued_pdf_file_id)
                )
                file_rec = file_result.scalar_one_or_none()
                if file_rec:
                    fname = file_rec.original_filename or f"invoice-{inv.invoice_number}.pdf"
                    pdf_file_entries.append((f"invoices/{fname}", file_rec.storage_key))

        for run in payroll_runs:
            if run.payslip_file_id:
                file_result = await db.execute(
                    select(File).where(File.id == run.payslip_file_id)
                )
                file_rec = file_result.scalar_one_or_none()
                if file_rec:
                    fname = file_rec.original_filename or f"payslip-{run.id}.pdf"
                    pdf_file_entries.append((f"payroll/{fname}", file_rec.storage_key))

        for pmt in payments:
            if pmt.proof_file_id:
                file_result = await db.execute(
                    select(File).where(File.id == pmt.proof_file_id)
                )
                file_rec = file_result.scalar_one_or_none()
                if file_rec:
                    fname = file_rec.original_filename or f"proof-{pmt.id}"
                    pdf_file_entries.append((f"evidence/{fname}", file_rec.storage_key))

        # 7. Build ZIP in memory
        zip_buffer = io.BytesIO()
        file_manifest_entries: list[dict] = []
        generated_at = datetime.now(timezone.utc)

        with zipfile.ZipFile(zip_buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
            # CSVs
            def _add_bytes(path: str, data: bytes) -> dict:
                sha = hashlib.sha256(data).hexdigest()
                zf.writestr(path, data)
                return {"path": path, "size_bytes": len(data), "sha256": sha}

            file_manifest_entries.append(_add_bytes("invoices/summary.csv", invoices_csv))
            file_manifest_entries.append(_add_bytes("payroll/summary.csv", payroll_csv))
            file_manifest_entries.append(_add_bytes("expenses/summary.csv", expenses_csv))
            file_manifest_entries.append(_add_bytes("payments/summary.csv", payments_csv))

            # PDF and evidence files
            for zip_path, storage_key in pdf_file_entries:
                try:
                    file_content = file_storage.download(storage_key)
                    file_manifest_entries.append(_add_bytes(zip_path, file_content))
                except Exception:
                    # Skip files that can't be downloaded
                    pass

            # 8. Build manifest JSON
            company_info: dict = {}
            if company:
                company_info = {
                    "legal_name": company.legal_name,
                    "uen": company.uen,
                    "jurisdiction": company.jurisdiction,
                }

            # Summary counts and amounts by currency
            invoice_amounts: dict[str, float] = {}
            for inv in invoices:
                invoice_amounts[inv.currency] = invoice_amounts.get(inv.currency, 0.0) + float(inv.total_amount)

            payroll_amounts: dict[str, float] = {}
            for run in payroll_runs:
                payroll_amounts[run.currency] = payroll_amounts.get(run.currency, 0.0) + float(run.net_salary)

            expense_amounts: dict[str, float] = {}
            for exp in expenses:
                expense_amounts[exp.currency] = expense_amounts.get(exp.currency, 0.0) + float(exp.amount)

            manifest = {
                "month": month_str,
                "version": new_version,
                "generated_at": generated_at.isoformat(),
                "company": company_info,
                "summary": {
                    "invoices": {
                        "count": len(invoices),
                        "total_by_currency": invoice_amounts,
                    },
                    "payroll": {
                        "count": len(payroll_runs),
                        "net_salary_by_currency": payroll_amounts,
                    },
                    "expenses": {
                        "count": len(expenses),
                        "total_by_currency": expense_amounts,
                    },
                    "payments": {
                        "count": len(payments),
                    },
                },
                "validation_summary": validation.model_dump(),
                "files": file_manifest_entries,
            }

            manifest_bytes = json.dumps(manifest, indent=2, default=str).encode("utf-8")
            file_manifest_entries.append(_add_bytes("manifest.json", manifest_bytes))
            # Re-write manifest with itself included (best-effort; manifest entry won't include itself)
            zf.writestr("manifest.json", manifest_bytes)

        zip_bytes = zip_buffer.getvalue()

        # 9. Upload ZIP via FileStorageService, create File record
        zip_filename = f"export-{month_str}-v{new_version}.zip"
        storage_key, sha256, size = file_storage.upload(
            io.BytesIO(zip_bytes),
            original_filename=zip_filename,
            mime_type="application/zip",
        )

        zip_file_record = File(
            storage_key=storage_key,
            original_filename=zip_filename,
            mime_type="application/zip",
            size_bytes=size,
            checksum_sha256=sha256,
            uploaded_by=user_id,
            linked_entity_type="export_pack",
            linked_entity_id=pack.id,
        )
        db.add(zip_file_record)
        await db.flush()
        await db.refresh(zip_file_record)

        # 10. Update ExportPack
        pack.zip_file_id = zip_file_record.id
        pack.manifest_json = manifest
        pack.status = "complete"
        pack.generated_at = generated_at
        await db.flush()

        # 11. Audit log
        audit = AuditService(db)
        await audit.log(
            action="export.generate",
            entity_type="export_pack",
            entity_id=pack.id,
            actor_id=user_id,
            input_data={"month": month_str, "force": force, "version": new_version},
            output_data={"status": "complete", "zip_file_id": str(zip_file_record.id)},
        )

    except Exception:
        pack.status = "failed"
        await db.flush()
        raise

    return pack


async def list_exports(
    db: AsyncSession,
    page: int = 1,
    per_page: int = 20,
) -> tuple[list[ExportPack], int]:
    count_result = await db.execute(select(func.count(ExportPack.id)))
    total = count_result.scalar_one()

    offset = (page - 1) * per_page
    result = await db.execute(
        select(ExportPack)
        .order_by(ExportPack.month.desc(), ExportPack.version.desc())
        .offset(offset)
        .limit(per_page)
    )
    items = list(result.scalars().all())
    return items, total


async def get_export(db: AsyncSession, export_id: uuid.UUID) -> Optional[ExportPack]:
    result = await db.execute(
        select(ExportPack).where(ExportPack.id == export_id)
    )
    return result.scalar_one_or_none()


async def get_export_download_url(
    db: AsyncSession,
    export_id: uuid.UUID,
    file_storage: FileStorageService,
) -> str:
    pack = await get_export(db, export_id)
    if pack is None:
        raise ValueError(f"ExportPack {export_id} not found")
    if pack.zip_file_id is None:
        raise ValueError("Export pack has no ZIP file")

    file_result = await db.execute(
        select(File).where(File.id == pack.zip_file_id)
    )
    file_rec = file_result.scalar_one_or_none()
    if file_rec is None:
        raise ValueError("ZIP file record not found")

    return file_storage.get_presigned_url(file_rec.storage_key)
