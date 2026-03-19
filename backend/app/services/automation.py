import calendar
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.expense import Expense
from app.models.invoice import Invoice, RecurringInvoiceRule
from app.models.payment import Payment
from app.models.payroll import Employee, PayrollRun
from app.schemas.export import AutomationResult
from app.services import invoice as invoice_service
from app.services import payroll as payroll_service
from app.services.export import validate_month, generate_month_end_pack
from app.services.file_storage import FileStorageService
from app.models.task import TaskInstance
from app.services.task import create_action_todo, generate_instances_for_month, get_overdue


async def run_daily(db: AsyncSession) -> AutomationResult:
    """Run daily checks and return a structured report."""
    today = date.today()
    items: list[dict] = []

    # 1. Overdue invoices (status=issued, due_date < today)
    overdue_result = await db.execute(
        select(Invoice).where(
            Invoice.status == "issued",
            Invoice.due_date < today,
        )
    )
    overdue_invoices = list(overdue_result.scalars().all())
    for inv in overdue_invoices:
        days_overdue = (today - inv.due_date).days if inv.due_date else 0
        items.append({
            "type": "overdue_invoice",
            "entity_type": "invoice",
            "entity_id": str(inv.id),
            "invoice_number": inv.invoice_number,
            "due_date": inv.due_date.isoformat() if inv.due_date else None,
            "currency": inv.currency,
            "total_amount": float(inv.total_amount),
            "description": f"Invoice {inv.invoice_number} is overdue since {inv.due_date}",
        })

        # Create a follow-up todo if one doesn't already exist for this invoice
        todo_title = f"Follow up on {inv.invoice_number} (overdue {days_overdue}d)"
        existing_todo_result = await db.execute(
            select(TaskInstance).where(
                TaskInstance.title.like(f"Follow up on {inv.invoice_number}%"),
                TaskInstance.status.in_(["pending", "in_progress"]),
            )
        )
        if existing_todo_result.scalar_one_or_none() is None:
            await create_action_todo(
                db,
                title=todo_title,
                description=f"Invoice {inv.invoice_number} is overdue by {days_overdue} days (due {inv.due_date})",
                category="operations",
                due_date=today,
                period=today.strftime("%Y-%m"),
                created_by=uuid.UUID("00000000-0000-0000-0000-000000000000"),
            )

    # 2. Unpaid finalized payroll runs
    unpaid_payroll_result = await db.execute(
        select(PayrollRun)
        .where(PayrollRun.status == "finalized")
        .options(selectinload(PayrollRun.employee))
    )
    unpaid_payroll = list(unpaid_payroll_result.scalars().all())
    for run in unpaid_payroll:
        items.append({
            "type": "unpaid_payroll",
            "entity_type": "payroll_run",
            "entity_id": str(run.id),
            "employee_name": run.employee.name if run.employee else "",
            "month": run.month.isoformat(),
            "currency": run.currency,
            "net_salary": float(run.net_salary),
            "description": f"Payroll run for {run.employee.name if run.employee else run.id} ({run.month}) is finalized but unpaid",
        })

    # 3. Expenses in draft status
    draft_expenses_result = await db.execute(
        select(Expense).where(Expense.status == "draft")
    )
    draft_expenses = list(draft_expenses_result.scalars().all())
    for exp in draft_expenses:
        items.append({
            "type": "draft_expense",
            "entity_type": "expense",
            "entity_id": str(exp.id),
            "expense_date": exp.expense_date.isoformat(),
            "vendor": exp.vendor,
            "currency": exp.currency,
            "amount": float(exp.amount),
            "description": f"Expense {exp.id} from {exp.expense_date} is still in draft",
        })

    # 4. Payments without proof file
    payments_no_proof_result = await db.execute(
        select(Payment).where(Payment.proof_file_id.is_(None))
    )
    payments_no_proof = list(payments_no_proof_result.scalars().all())
    for pmt in payments_no_proof:
        items.append({
            "type": "payment_no_proof",
            "entity_type": "payment",
            "entity_id": str(pmt.id),
            "payment_date": pmt.payment_date.isoformat() if pmt.payment_date else None,
            "currency": pmt.currency,
            "amount": float(pmt.amount),
            "description": f"Payment {pmt.id} has no proof file",
        })

    # 5. Overdue task instances
    overdue_tasks = await get_overdue(db)
    for task in overdue_tasks:
        items.append({
            "type": "overdue_task",
            "entity_type": "task_instance",
            "entity_id": str(task.id),
            "title": task.title,
            "due_date": task.due_date.isoformat() if task.due_date else None,
            "description": f"Task '{task.title}' is overdue (due {task.due_date})",
        })

    summary = {
        "overdue_invoices": len(overdue_invoices),
        "unpaid_payroll_runs": len(unpaid_payroll),
        "draft_expenses": len(draft_expenses),
        "payments_without_proof": len(payments_no_proof),
        "overdue_tasks": len(overdue_tasks),
        "total_issues": len(items),
    }

    return AutomationResult(
        report_type="daily",
        generated_at=datetime.now(timezone.utc),
        items=items,
        summary=summary,
    )


async def run_weekly(db: AsyncSession) -> AutomationResult:
    """Run weekly checks and return a structured report."""
    today = date.today()
    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    items: list[dict] = []

    # 1. Invoice aging report
    issued_invoices_result = await db.execute(
        select(Invoice).where(Invoice.status == "issued", Invoice.issue_date.isnot(None))
    )
    issued_invoices = list(issued_invoices_result.scalars().all())

    aging_buckets: dict[str, list[dict]] = {
        "0_30": [],
        "31_60": [],
        "61_90": [],
        "91_plus": [],
    }
    for inv in issued_invoices:
        if inv.issue_date is None:
            continue
        age_days = (today - inv.issue_date).days
        entry = {
            "invoice_id": str(inv.id),
            "invoice_number": inv.invoice_number,
            "issue_date": inv.issue_date.isoformat(),
            "due_date": inv.due_date.isoformat() if inv.due_date else None,
            "currency": inv.currency,
            "total_amount": float(inv.total_amount),
            "age_days": age_days,
        }
        if age_days <= 30:
            aging_buckets["0_30"].append(entry)
        elif age_days <= 60:
            aging_buckets["31_60"].append(entry)
        elif age_days <= 90:
            aging_buckets["61_90"].append(entry)
        else:
            aging_buckets["91_plus"].append(entry)

    items.append({
        "type": "invoice_aging",
        "description": "Invoice aging report",
        "buckets": aging_buckets,
        "total_outstanding": len(issued_invoices),
    })

    # 2. This week's expense summary by category
    expenses_result = await db.execute(
        select(Expense).where(
            Expense.expense_date >= week_start,
            Expense.expense_date <= week_end,
        )
    )
    week_expenses = list(expenses_result.scalars().all())
    by_category: dict[str, float] = {}
    for exp in week_expenses:
        cat = exp.category or "uncategorized"
        by_category[cat] = by_category.get(cat, 0.0) + float(exp.amount)

    items.append({
        "type": "weekly_expense_summary",
        "description": f"Expense summary for week {week_start} to {week_end}",
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        "total_expenses": len(week_expenses),
        "by_category": by_category,
    })

    # 3. Outstanding client payments (issued invoices)
    outstanding_result = await db.execute(
        select(Invoice).where(Invoice.status == "issued")
    )
    outstanding_invoices = list(outstanding_result.scalars().all())
    outstanding_total_by_currency: dict[str, float] = {}
    for inv in outstanding_invoices:
        outstanding_total_by_currency[inv.currency] = (
            outstanding_total_by_currency.get(inv.currency, 0.0) + float(inv.total_amount)
        )

    items.append({
        "type": "outstanding_payments",
        "description": "Outstanding client payments",
        "count": len(outstanding_invoices),
        "total_by_currency": outstanding_total_by_currency,
    })

    # 4. Missing evidence reminders (across all time for issued/paid invoices without PDF)
    missing_pdf_result = await db.execute(
        select(Invoice).where(
            Invoice.status.in_(["issued", "paid"]),
            Invoice.issued_pdf_file_id.is_(None),
        )
    )
    missing_pdfs = list(missing_pdf_result.scalars().all())
    for inv in missing_pdfs:
        items.append({
            "type": "missing_invoice_pdf",
            "entity_type": "invoice",
            "entity_id": str(inv.id),
            "invoice_number": inv.invoice_number,
            "description": f"Invoice {inv.invoice_number} is missing a PDF",
        })

    summary = {
        "outstanding_invoices": len(issued_invoices),
        "overdue_invoices": len(aging_buckets["91_plus"]) + len(aging_buckets["61_90"]),
        "week_expenses": len(week_expenses),
        "missing_invoice_pdfs": len(missing_pdfs),
        "total_items": len(items),
    }

    return AutomationResult(
        report_type="weekly",
        generated_at=datetime.now(timezone.utc),
        items=items,
        summary=summary,
    )


async def run_monthly(
    db: AsyncSession,
    month_str: str,
    file_storage: Optional[FileStorageService] = None,
    system_user_id: Optional[uuid.UUID] = None,
) -> AutomationResult:
    """Run monthly automation: recurring invoices, payroll drafts, validation, export."""
    year, month_num = map(int, month_str.split("-"))
    days_in_month = calendar.monthrange(year, month_num)[1]
    month_start = date(year, month_num, 1)
    month_end = date(year, month_num, days_in_month)

    items: list[dict] = []

    # Resolve a system user id for created_by if not provided
    # Use a deterministic nil UUID as the system actor when no user is given
    actor_id = system_user_id or uuid.UUID("00000000-0000-0000-0000-000000000000")

    # 1. Process recurring invoice rules due this month
    rules_result = await db.execute(
        select(RecurringInvoiceRule)
        .where(
            RecurringInvoiceRule.is_active == True,  # noqa: E712
            RecurringInvoiceRule.next_issue_date >= month_start,
            RecurringInvoiceRule.next_issue_date <= month_end,
        )
        .options(selectinload(RecurringInvoiceRule.client))
    )
    rules = list(rules_result.scalars().all())

    for rule in rules:
        try:
            invoice = await invoice_service.create_invoice(
                db=db,
                client_id=rule.client_id,
                currency=rule.currency,
                description=rule.description,
                payment_method=rule.payment_method,
                created_by=actor_id,
            )

            # Add line items from template
            if rule.line_items_json:
                line_items = rule.line_items_json if isinstance(rule.line_items_json, list) else []
                for li in line_items:
                    await invoice_service.add_line_item(
                        db=db,
                        invoice=invoice,
                        description=li.get("description", ""),
                        quantity=Decimal(str(li.get("quantity", 1))),
                        unit_price=Decimal(str(li.get("unit_price", 0))),
                    )

            # Update next_issue_date: advance by one month
            next_month_num = month_num + 1
            next_year = year
            if next_month_num > 12:
                next_month_num = 1
                next_year += 1
            next_days = calendar.monthrange(next_year, next_month_num)[1]
            day = min(rule.day_of_month, next_days)
            rule.next_issue_date = date(next_year, next_month_num, day)
            rule.last_issued_invoice_id = invoice.id
            await db.flush()

            items.append({
                "type": "recurring_invoice_created",
                "rule_id": str(rule.id),
                "invoice_id": str(invoice.id),
                "invoice_number": invoice.invoice_number,
                "client_id": str(rule.client_id),
                "description": f"Created recurring invoice {invoice.invoice_number} from rule {rule.id}",
            })
        except Exception as exc:
            items.append({
                "type": "recurring_invoice_error",
                "rule_id": str(rule.id),
                "error": str(exc),
                "description": f"Failed to create recurring invoice for rule {rule.id}: {exc}",
            })

    # 2. Create payroll run drafts for all active employees
    employees_result = await db.execute(
        select(Employee).where(
            Employee.status == "active",
            Employee.start_date <= month_end,
        )
    )
    active_employees = list(employees_result.scalars().all())

    payroll_created = 0
    payroll_skipped = 0
    for employee in active_employees:
        # Skip if employee ended before month start
        if employee.end_date is not None and employee.end_date < month_start:
            payroll_skipped += 1
            continue

        # Check if payroll run already exists for this employee+month
        existing_result = await db.execute(
            select(PayrollRun).where(
                PayrollRun.employee_id == employee.id,
                PayrollRun.month == month_start,
            )
        )
        existing = existing_result.scalar_one_or_none()
        if existing is not None:
            payroll_skipped += 1
            items.append({
                "type": "payroll_draft_skipped",
                "employee_id": str(employee.id),
                "employee_name": employee.name,
                "description": f"Payroll run for {employee.name} ({month_str}) already exists",
            })
            continue

        try:
            run = await payroll_service.create_payroll_run(
                db=db,
                employee_id=employee.id,
                month_str=month_str,
                start_date=None,
                end_date=None,
                created_by=actor_id,
            )
            payroll_created += 1
            items.append({
                "type": "payroll_draft_created",
                "employee_id": str(employee.id),
                "employee_name": employee.name,
                "payroll_run_id": str(run.id),
                "description": f"Created payroll draft for {employee.name} ({month_str})",
            })
        except Exception as exc:
            items.append({
                "type": "payroll_draft_error",
                "employee_id": str(employee.id),
                "employee_name": employee.name,
                "error": str(exc),
                "description": f"Failed to create payroll draft for {employee.name}: {exc}",
            })

    # 3. Run month validation
    validation = await validate_month(db, month_str)
    items.append({
        "type": "month_validation",
        "month": month_str,
        "is_complete": validation.is_complete,
        "invoices_draft": validation.invoices_draft,
        "payroll_pending": validation.payroll_pending,
        "expenses_draft": validation.expenses_draft,
        "missing_evidence_count": len(validation.missing_evidence),
        "description": f"Month {month_str} validation: {'complete' if validation.is_complete else 'incomplete'}",
    })

    # 4. Generate export pack if validation passes and file_storage provided
    export_result: dict = {"attempted": False}
    if validation.is_complete and file_storage is not None and system_user_id is not None:
        try:
            pack = await generate_month_end_pack(
                db=db,
                month_str=month_str,
                force=False,
                user_id=system_user_id,
                file_storage=file_storage,
            )
            export_result = {
                "attempted": True,
                "success": True,
                "export_pack_id": str(pack.id),
                "version": pack.version,
            }
            items.append({
                "type": "export_pack_generated",
                "export_pack_id": str(pack.id),
                "version": pack.version,
                "description": f"Generated export pack v{pack.version} for {month_str}",
            })
        except Exception as exc:
            export_result = {"attempted": True, "success": False, "error": str(exc)}
            items.append({
                "type": "export_pack_error",
                "error": str(exc),
                "description": f"Failed to generate export pack for {month_str}: {exc}",
            })

    # 5. Generate task instances for the month
    try:
        generated_tasks = await generate_instances_for_month(db, month_str)
        items.append({
            "type": "task_instances_generated",
            "month": month_str,
            "count": len(generated_tasks),
            "description": f"Generated {len(generated_tasks)} task instances for {month_str}",
        })
    except Exception as exc:
        generated_tasks = []
        items.append({
            "type": "task_instances_error",
            "error": str(exc),
            "description": f"Failed to generate task instances for {month_str}: {exc}",
        })

    summary = {
        "recurring_invoices_created": sum(1 for i in items if i["type"] == "recurring_invoice_created"),
        "recurring_invoice_errors": sum(1 for i in items if i["type"] == "recurring_invoice_error"),
        "payroll_drafts_created": payroll_created,
        "payroll_drafts_skipped": payroll_skipped,
        "month_validation_complete": validation.is_complete,
        "export_attempted": export_result.get("attempted", False),
        "export_success": export_result.get("success", False),
        "task_instances_generated": len(generated_tasks),
    }

    return AutomationResult(
        report_type="monthly",
        generated_at=datetime.now(timezone.utc),
        items=items,
        summary=summary,
    )
