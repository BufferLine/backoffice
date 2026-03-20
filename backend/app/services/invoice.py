import io
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.jurisdiction import get_jurisdiction
from app.models.company import CompanySettings
from app.models.file import File
from app.models.invoice import Invoice, InvoiceLineItem, invoice_payment_methods
from app.models.payment import Payment
from app.models.payment_method import PaymentMethod
from app.services.audit import AuditService
from app.services.changelog import track_status_change
from app.services.file_storage import FileStorageService
from app.services.pdf import render_invoice_pdf
from app.state_machines import InvalidTransitionError
from app.state_machines.invoice import invoice_machine


async def _next_invoice_number(db: AsyncSession) -> str:
    """Derive the next invoice number by finding the current MAX for this year."""
    year = datetime.now(timezone.utc).year
    prefix = f"INV-{year}-"

    result = await db.execute(
        select(func.max(Invoice.invoice_number)).where(
            Invoice.invoice_number.like(f"{prefix}%")
        )
    )
    max_number = result.scalar_one_or_none()
    if max_number is None:
        next_num = 1
    else:
        try:
            next_num = int(max_number.split("-")[-1]) + 1
        except (ValueError, IndexError):
            next_num = 1
    return f"{prefix}{next_num:04d}"


async def _get_company_settings(db: AsyncSession) -> Optional[CompanySettings]:
    result = await db.execute(select(CompanySettings).limit(1))
    return result.scalar_one_or_none()


async def recalculate_totals(db: AsyncSession, invoice: Invoice) -> None:
    """Recalculate subtotal, tax, and total for an invoice from its line items.

    Tax is computed per line item using the item's tax_code and optional tax_rate override:
      SR (Standard Rate): tax = amount × (item.tax_rate or company gst_rate)
      ZR / ES / NT:       tax = 0
    """
    # Reload line items if not loaded
    await db.refresh(invoice, ["line_items"])

    subtotal = Decimal("0")
    for item in invoice.line_items:
        subtotal += Decimal(str(item.amount))

    # Get company settings for tax calculation
    company = await _get_company_settings(db)
    company_gst_rate = Decimal("0")
    gst_registered = False
    if company:
        gst_registered = company.gst_registered
        company_gst_rate = Decimal(str(company.gst_rate)) if company.gst_rate else Decimal("0")

    total_tax = Decimal("0")
    effective_tax_rate: Optional[float] = None

    if gst_registered and company and company.jurisdiction:
        try:
            jurisdiction = get_jurisdiction(company.jurisdiction)
            for item in invoice.line_items:
                tax_code = item.tax_code or "SR"
                if tax_code in ("ZR", "ES", "NT"):
                    item.tax_amount = 0.0
                else:
                    # SR or unknown — treat as standard rate
                    rate = Decimal(str(item.tax_rate)) if item.tax_rate is not None else company_gst_rate
                    item_amount = Decimal(str(item.amount))
                    if invoice.tax_inclusive:
                        item_tax = (item_amount * rate / (1 + rate)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                    else:
                        item_tax = (item_amount * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                    item.tax_amount = float(item_tax)
                    total_tax += item_tax

            effective_tax_rate = float(company_gst_rate) if company_gst_rate else None
        except ValueError:
            effective_tax_rate = None
            total_tax = Decimal("0")
    else:
        for item in invoice.line_items:
            item.tax_amount = 0.0

    invoice.tax_rate = effective_tax_rate
    invoice.tax_amount = float(total_tax)
    invoice.subtotal_amount = float(subtotal)
    if invoice.tax_inclusive:
        # Tax is already embedded in line item prices; total == subtotal
        invoice.total_amount = float(subtotal)
    else:
        invoice.total_amount = float(subtotal + total_tax)
    await db.flush()


async def create_invoice(
    db: AsyncSession,
    client_id: uuid.UUID,
    currency: str,
    created_by: uuid.UUID,
    description: Optional[str] = None,
    payment_method: Optional[str] = None,
    wallet_address: Optional[str] = None,
    tax_inclusive: bool = False,
    payment_method_id: Optional[uuid.UUID] = None,
    payment_method_ids: Optional[list[uuid.UUID]] = None,
) -> Invoice:
    """Create a new draft invoice with auto-generated invoice number.

    Uses a retry loop (up to 3 attempts) to handle concurrent inserts that
    collide on the unique invoice_number constraint.

    payment_method_ids (if provided) populates the join table for multi-method invoices.
    payment_method_id is kept for backward compatibility and is also used as the join
    table entry when payment_method_ids is not provided.
    """
    # Auto-resolve default payment method for currency if neither is provided
    if payment_method_id is None and not payment_method_ids:
        result = await db.execute(
            select(PaymentMethod).where(
                PaymentMethod.currency == currency,
                PaymentMethod.is_default == True,
                PaymentMethod.is_active == True,
            ).limit(1)
        )
        default_method = result.scalar_one_or_none()
        if default_method is not None:
            payment_method_id = default_method.id

    # Determine effective join-table IDs
    effective_pm_ids: list[uuid.UUID] = []
    if payment_method_ids:
        effective_pm_ids = list(payment_method_ids)
        # Also set the legacy field to the first entry for backward compat
        if payment_method_id is None:
            payment_method_id = effective_pm_ids[0]
    elif payment_method_id is not None:
        effective_pm_ids = [payment_method_id]

    last_error: Exception = RuntimeError("Invoice number generation failed")
    for _ in range(3):
        invoice_number = await _next_invoice_number(db)
        invoice = Invoice(
            invoice_number=invoice_number,
            client_id=client_id,
            currency=currency,
            description=description,
            payment_method=payment_method,
            wallet_address=wallet_address,
            created_by=created_by,
            status="draft",
            subtotal_amount=0.0,
            tax_amount=0.0,
            total_amount=0.0,
            tax_inclusive=tax_inclusive,
            payment_method_id=payment_method_id,
        )
        db.add(invoice)
        try:
            await db.flush()
            # Insert join table rows for each payment method
            if effective_pm_ids:
                from sqlalchemy import insert as sa_insert
                await db.execute(
                    sa_insert(invoice_payment_methods),
                    [
                        {"invoice_id": invoice.id, "payment_method_id": pm_id, "sort_order": idx}
                        for idx, pm_id in enumerate(effective_pm_ids)
                    ],
                )
                await db.flush()
            await db.refresh(invoice, ["line_items", "payment_methods"])
            return invoice
        except IntegrityError as e:
            await db.rollback()
            last_error = e
    raise ValueError("Could not generate a unique invoice number after 3 attempts") from last_error


async def get_invoice(db: AsyncSession, invoice_id: uuid.UUID) -> Optional[Invoice]:
    """Fetch invoice with line items and payment methods eager-loaded."""
    result = await db.execute(
        select(Invoice)
        .where(Invoice.id == invoice_id)
        .options(selectinload(Invoice.line_items), selectinload(Invoice.payment_methods))
    )
    return result.scalar_one_or_none()


async def list_invoices(
    db: AsyncSession,
    status: Optional[str] = None,
    client_id: Optional[uuid.UUID] = None,
    page: int = 1,
    per_page: int = 20,
) -> tuple[list[Invoice], int]:
    """Return paginated invoices and total count."""
    query = select(Invoice).options(selectinload(Invoice.line_items), selectinload(Invoice.payment_methods))
    count_query = select(func.count(Invoice.id))

    if status:
        query = query.where(Invoice.status == status)
        count_query = count_query.where(Invoice.status == status)
    if client_id:
        query = query.where(Invoice.client_id == client_id)
        count_query = count_query.where(Invoice.client_id == client_id)

    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    offset = (page - 1) * per_page
    query = query.order_by(Invoice.created_at.desc()).offset(offset).limit(per_page)
    result = await db.execute(query)
    invoices = list(result.scalars().all())

    return invoices, total


async def update_invoice(
    db: AsyncSession,
    invoice: Invoice,
    description: Optional[str] = None,
    currency: Optional[str] = None,
    payment_method: Optional[str] = None,
    wallet_address: Optional[str] = None,
    tax_inclusive: Optional[bool] = None,
    payment_method_id: Optional[uuid.UUID] = None,
) -> Invoice:
    """Update a draft invoice's fields."""
    if invoice.status != "draft":
        raise ValueError("Can only update draft invoices")

    if description is not None:
        invoice.description = description
    if currency is not None:
        invoice.currency = currency
    if payment_method is not None:
        invoice.payment_method = payment_method
    if wallet_address is not None:
        invoice.wallet_address = wallet_address
    if tax_inclusive is not None:
        invoice.tax_inclusive = tax_inclusive
        await recalculate_totals(db, invoice)
    if payment_method_id is not None:
        invoice.payment_method_id = payment_method_id

    await db.flush()
    return invoice


async def add_line_item(
    db: AsyncSession,
    invoice: Invoice,
    description: str,
    quantity: Decimal,
    unit_price: Decimal,
    tax_code: str = "SR",
    tax_rate: Optional[Decimal] = None,
) -> InvoiceLineItem:
    """Add a line item to a draft invoice and recalculate totals."""
    if invoice.status != "draft":
        raise ValueError("Can only add line items to draft invoices")

    amount = (quantity * unit_price).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)

    # Determine sort order
    await db.refresh(invoice, ["line_items"])
    sort_order = len(invoice.line_items)

    item = InvoiceLineItem(
        invoice_id=invoice.id,
        description=description,
        quantity=float(quantity),
        unit_price=float(unit_price),
        amount=float(amount),
        sort_order=sort_order,
        tax_code=tax_code,
        tax_rate=float(tax_rate) if tax_rate is not None else None,
    )
    db.add(item)
    await db.flush()
    await recalculate_totals(db, invoice)
    return item


async def update_line_item(
    db: AsyncSession,
    invoice: Invoice,
    item_id: uuid.UUID,
    description: Optional[str] = None,
    quantity: Optional[Decimal] = None,
    unit_price: Optional[Decimal] = None,
    tax_code: Optional[str] = None,
    tax_rate: Optional[Decimal] = None,
) -> InvoiceLineItem:
    """Update a line item on a draft invoice and recalculate totals."""
    if invoice.status != "draft":
        raise ValueError("Can only update line items on draft invoices")

    result = await db.execute(
        select(InvoiceLineItem).where(
            InvoiceLineItem.id == item_id,
            InvoiceLineItem.invoice_id == invoice.id,
        )
    )
    item = result.scalar_one_or_none()
    if item is None:
        return None

    if description is not None:
        item.description = description
    if quantity is not None:
        item.quantity = float(quantity)
    if unit_price is not None:
        item.unit_price = float(unit_price)
    if tax_code is not None:
        item.tax_code = tax_code
    if tax_rate is not None:
        item.tax_rate = float(tax_rate)

    # Recalculate amount
    new_amount = (
        Decimal(str(item.quantity)) * Decimal(str(item.unit_price))
    ).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
    item.amount = float(new_amount)

    await db.flush()
    await recalculate_totals(db, invoice)
    return item


async def delete_line_item(
    db: AsyncSession,
    invoice: Invoice,
    item_id: uuid.UUID,
) -> bool:
    """Delete a line item from a draft invoice and recalculate totals."""
    if invoice.status != "draft":
        raise ValueError("Can only delete line items from draft invoices")

    result = await db.execute(
        select(InvoiceLineItem).where(
            InvoiceLineItem.id == item_id,
            InvoiceLineItem.invoice_id == invoice.id,
        )
    )
    item = result.scalar_one_or_none()
    if item is None:
        return False

    await db.delete(item)
    await db.flush()
    await recalculate_totals(db, invoice)
    return True


async def issue_invoice(
    db: AsyncSession,
    invoice: Invoice,
    user_id: uuid.UUID,
    file_storage: FileStorageService,
) -> Invoice:
    """Issue a draft invoice: validate, set dates, generate PDF, transition state."""
    # Validate transition (raises InvalidTransitionError if not allowed)
    if not invoice_machine.can_transition(invoice.status, "issue"):
        raise InvalidTransitionError("invoice", invoice.status, "issue")

    # Must have at least one line item
    await db.refresh(invoice, ["line_items"])
    if not invoice.line_items:
        raise ValueError("Cannot issue an invoice with no line items")

    # Set dates
    today = date.today()
    invoice.issue_date = today

    # Calculate due date from client payment terms or company defaults
    payment_terms_days = 30
    company = await _get_company_settings(db)
    if company:
        payment_terms_days = company.default_payment_terms_days

    # Load client to check client-specific terms
    await db.refresh(invoice, ["client"])
    if invoice.client and invoice.client.payment_terms_days is not None:
        payment_terms_days = invoice.client.payment_terms_days

    from datetime import timedelta
    invoice.due_date = today + timedelta(days=payment_terms_days)

    # Generate PDF — failure blocks issuance so the caller is informed
    pdf_data = await _generate_invoice_pdf(db, invoice, company, file_storage)
    invoice.issued_pdf_file_id = pdf_data

    # Transition state
    old_status = invoice.status
    invoice.status = invoice_machine.transition(invoice.status, "issue")

    await db.flush()

    # Change log
    await track_status_change(db, "invoice", invoice.id, old_status, invoice.status, changed_by=user_id)

    # Audit log
    audit = AuditService(db)
    await audit.log(
        action="issue",
        entity_type="invoice",
        entity_id=invoice.id,
        actor_id=user_id,
        output_data={"invoice_number": invoice.invoice_number, "status": invoice.status},
    )

    from app.services.task import create_action_todo
    await db.refresh(invoice, ["client"])
    client_name = invoice.client.legal_name if invoice.client else str(invoice.client_id)
    await create_action_todo(
        db,
        title=f"Send invoice {invoice.invoice_number} to {client_name}",
        description=f"Invoice issued for {invoice.currency} {invoice.total_amount}",
        category="operations",
        due_date=today,
        period=invoice.issue_date.strftime("%Y-%m") if invoice.issue_date else today.strftime("%Y-%m"),
        created_by=user_id,
    )

    return invoice


async def _generate_invoice_pdf(
    db: AsyncSession,
    invoice: Invoice,
    company: Optional[CompanySettings],
    file_storage: FileStorageService,
) -> Optional[uuid.UUID]:
    """Generate invoice PDF, upload to storage, create File record. Returns file ID."""
    # Build template data
    await db.refresh(invoice, ["line_items", "client", "payment_methods"])

    line_items_data = [
        {
            "description": item.description,
            "quantity": item.quantity,
            "unit_price": item.unit_price,
            "amount": item.amount,
            "tax_code": item.tax_code,
            "tax_rate": item.tax_rate,
            "tax_amount": item.tax_amount,
        }
        for item in sorted(invoice.line_items, key=lambda x: x.sort_order)
    ]

    company_data = {}
    if company:
        company_data = {
            "legal_name": company.legal_name,
            "uen": company.uen,
            "address": company.address,
            "billing_email": company.billing_email,
            "bank_name": company.bank_name,
            "bank_account_number": company.bank_account_number,
            "bank_swift_code": company.bank_swift_code,
            "gst_registration_number": company.gst_registration_number,
            "website": company.website,
        }

    client = invoice.client
    client_data = {}
    if client:
        client_data = {
            "legal_name": client.legal_name,
            "billing_email": client.billing_email,
            "billing_address": client.billing_address,
        }

    def _pm_to_dict(pm: PaymentMethod) -> dict:
        if pm.type == "crypto":
            return {
                "type": "crypto",
                "nickname": pm.nickname,
                "wallet_address": pm.wallet_address,
                "chain_id": pm.chain_id,
                "account_name": company.legal_name if company else None,
                "reference": invoice.invoice_number,
            }
        elif pm.type == "paynow":
            return {
                "type": "paynow",
                "nickname": pm.nickname,
                "uen_number": pm.uen_number,
                "account_name": company.legal_name if company else None,
                "reference": invoice.invoice_number,
            }
        else:
            return {
                "type": pm.type,
                "nickname": pm.nickname,
                "bank_name": pm.bank_name,
                "account_name": company.legal_name if company else None,
                "account_number": pm.bank_account_number,
                "swift": pm.bank_swift_code,
                "reference": invoice.invoice_number,
            }

    # Build payment_methods list from the join table (multi-method support)
    # Falls back to the legacy payment_method_id, then company bank settings.
    payment_methods_data: list[dict] = []
    if invoice.payment_methods:
        payment_methods_data = [_pm_to_dict(pm) for pm in invoice.payment_methods]
    elif invoice.payment_method_id is not None:
        pm_result = await db.execute(
            select(PaymentMethod).where(PaymentMethod.id == invoice.payment_method_id)
        )
        pm = pm_result.scalar_one_or_none()
        if pm is not None:
            payment_methods_data = [_pm_to_dict(pm)]
    if not payment_methods_data and company and company.bank_name:
        payment_methods_data = [{
            "type": "bank_transfer",
            "nickname": None,
            "bank_name": company.bank_name,
            "account_name": company.legal_name,
            "account_number": company.bank_account_number,
            "swift": company.bank_swift_code,
            "reference": invoice.invoice_number,
        }]

    # Backward-compat single payment_details (first entry)
    payment_details = payment_methods_data[0] if payment_methods_data else None

    # Check if any non-SR tax codes are present for the GST breakdown section
    has_mixed_tax_codes = len({item["tax_code"] for item in line_items_data}) > 1

    pdf_data = {
        "invoice": {
            "invoice_number": invoice.invoice_number,
            "issue_date": invoice.issue_date,
            "due_date": invoice.due_date,
            "currency": invoice.currency,
            "subtotal_amount": invoice.subtotal_amount,
            "tax_rate": invoice.tax_rate,
            "tax_amount": invoice.tax_amount,
            "total_amount": invoice.total_amount,
            "tax_inclusive": invoice.tax_inclusive,
            "description": invoice.description,
            "payment_method": invoice.payment_method,
            "wallet_address": invoice.wallet_address,
        },
        "company": company_data,
        "client": client_data,
        "line_items": line_items_data,
        "payment_details": payment_details,
        "payment_methods": payment_methods_data,
        "has_mixed_tax_codes": has_mixed_tax_codes,
    }

    # Load company stamp if available
    stamp_bytes = None
    stamp_mime = "image/png"
    if company and company.stamp_file_id:
        stamp_file_result = await db.execute(
            select(File).where(File.id == company.stamp_file_id)
        )
        stamp_file = stamp_file_result.scalar_one_or_none()
        if stamp_file:
            try:
                stamp_bytes = file_storage.download(stamp_file.storage_key)
                stamp_mime = stamp_file.mime_type or "image/png"
            except Exception:
                pass  # stamp is optional, continue without it

    # Load company logo if available
    logo_bytes = None
    logo_mime = "image/png"
    if company and company.logo_file_id:
        logo_file_result = await db.execute(
            select(File).where(File.id == company.logo_file_id)
        )
        logo_file = logo_file_result.scalar_one_or_none()
        if logo_file:
            try:
                logo_bytes = file_storage.download(logo_file.storage_key)
                logo_mime = logo_file.mime_type or "image/png"
            except Exception:
                pass  # logo is optional, continue without it

    # Build theme from company branding settings
    theme = None
    if company:
        theme = {
            "primary_color": company.primary_color or "#1a56db",
            "accent_color": company.accent_color or "#374151",
            "font_family": company.font_family or "Helvetica, Arial, sans-serif",
        }

    # Generate PayNow QR code if applicable
    from app.services.pdf import _generate_paynow_qr
    if (
        payment_details is not None
        and payment_details.get("type") == "paynow"
        and payment_details.get("uen_number")
    ):
        pdf_data["paynow_qr_uri"] = _generate_paynow_qr(
            uen=payment_details["uen_number"],
            amount=Decimal(str(invoice.total_amount)),
            reference=payment_details.get("reference", ""),
        )
    else:
        pdf_data["paynow_qr_uri"] = None

    pdf_bytes = render_invoice_pdf(
        pdf_data,
        stamp_bytes=stamp_bytes,
        stamp_mime=stamp_mime,
        logo_bytes=logo_bytes,
        logo_mime=logo_mime,
        theme=theme,
    )
    filename = f"invoice-{invoice.invoice_number}.pdf"

    storage_key, sha256, size = file_storage.upload(
        io.BytesIO(pdf_bytes),
        original_filename=filename,
        mime_type="application/pdf",
    )

    file_record = File(
        storage_key=storage_key,
        original_filename=filename,
        mime_type="application/pdf",
        size_bytes=size,
        checksum_sha256=sha256,
        linked_entity_type="invoice",
        linked_entity_id=invoice.id,
    )
    db.add(file_record)
    await db.flush()
    return file_record.id


async def mark_paid(
    db: AsyncSession,
    invoice: Invoice,
    payment_id: uuid.UUID,
    user_id: uuid.UUID,
) -> Invoice:
    """Mark an issued invoice as paid after verifying the payment exists."""
    # Validate transition
    invoice_machine.transition(invoice.status, "mark_paid")

    # Verify payment exists and is linked to this invoice
    result = await db.execute(
        select(Payment).where(
            Payment.id == payment_id,
            Payment.related_entity_type == "invoice",
            Payment.related_entity_id == invoice.id,
        )
    )
    payment = result.scalar_one_or_none()
    if payment is None:
        raise ValueError("Payment not found or not linked to this invoice")

    old_status = invoice.status
    invoice.status = invoice_machine.transition(invoice.status, "mark_paid")
    await db.flush()

    await track_status_change(db, "invoice", invoice.id, old_status, invoice.status, changed_by=user_id)

    audit = AuditService(db)
    await audit.log(
        action="mark_paid",
        entity_type="invoice",
        entity_id=invoice.id,
        actor_id=user_id,
        input_data={"payment_id": str(payment_id)},
        output_data={"status": invoice.status},
    )

    return invoice


async def regenerate_invoice_pdf(
    db: AsyncSession,
    invoice: Invoice,
    user_id: uuid.UUID,
    file_storage: FileStorageService,
) -> Invoice:
    """Regenerate the PDF for an issued invoice with current company branding."""
    if invoice.status != "issued":
        raise ValueError("Can only regenerate PDF for issued invoices")

    company = await _get_company_settings(db)
    new_file_id = await _generate_invoice_pdf(db, invoice, company, file_storage)
    invoice.issued_pdf_file_id = new_file_id
    await db.flush()

    audit = AuditService(db)
    await audit.log(
        action="regenerate_pdf",
        entity_type="invoice",
        entity_id=invoice.id,
        actor_id=user_id,
        output_data={"issued_pdf_file_id": str(new_file_id)},
    )

    return invoice


async def cancel_invoice(
    db: AsyncSession,
    invoice: Invoice,
    user_id: uuid.UUID,
) -> Invoice:
    """Cancel a draft or issued invoice. Issued invoices must have no payments."""
    # Validate transition
    invoice_machine.transition(invoice.status, "cancel")

    # For issued invoices, check no payments linked
    if invoice.status == "issued":
        result = await db.execute(
            select(func.count(Payment.id)).where(
                Payment.related_entity_type == "invoice",
                Payment.related_entity_id == invoice.id,
            )
        )
        payment_count = result.scalar_one()
        if payment_count > 0:
            raise ValueError("Cannot cancel an issued invoice with linked payments")

    old_status = invoice.status
    invoice.status = invoice_machine.transition(invoice.status, "cancel")
    await db.flush()

    await track_status_change(db, "invoice", invoice.id, old_status, invoice.status, changed_by=user_id)

    audit = AuditService(db)
    await audit.log(
        action="cancel",
        entity_type="invoice",
        entity_id=invoice.id,
        actor_id=user_id,
        output_data={"status": invoice.status},
    )

    return invoice
