import uuid
from datetime import timedelta
from decimal import Decimal
from typing import BinaryIO, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.bank_transaction import BankTransaction
from app.models.file import File
from app.models.payment import Payment
from app.schemas.bank import AutoMatchResult, AutoMatchResultItem
from app.schemas.journal import JournalEntryCreate, JournalLineCreate
from app.services.audit import AuditService
from app.services.journal import create_journal_entry
from app.statement_parsers import get_parser


async def import_statement(
    db: AsyncSession,
    file_data: BinaryIO,
    source: str,
    filename: str,
    user_id: uuid.UUID,
    mime_type: str = "text/csv",
) -> dict:
    """Parse CSV and create BankTransaction records. Returns import summary."""
    parser = get_parser(source)
    transactions = parser.parse(file_data)

    # Store original file record
    file_record = File(
        storage_key=f"bank_statements/{uuid.uuid4()}/{filename}",
        original_filename=filename,
        mime_type=mime_type,
        linked_entity_type="bank_statement",
        uploaded_by=user_id,
    )
    db.add(file_record)
    await db.flush()

    imported_count = 0
    skipped_duplicates = 0

    for tx in transactions:
        # Check uniqueness by source + source_tx_id
        result = await db.execute(
            select(BankTransaction).where(
                BankTransaction.source == source,
                BankTransaction.source_tx_id == tx.source_tx_id,
            )
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            skipped_duplicates += 1
            continue

        bank_tx = BankTransaction(
            source=source,
            source_tx_id=tx.source_tx_id,
            tx_date=tx.tx_date,
            amount=tx.amount,
            currency=tx.currency,
            counterparty=tx.counterparty,
            reference=tx.reference,
            description=tx.description,
            match_status="unmatched",
            raw_data_json=tx.raw_data,
            statement_file_id=file_record.id,
            imported_by=user_id,
        )
        db.add(bank_tx)
        imported_count += 1

    await db.flush()

    await AuditService(db).log(
        action="bank_statement.import",
        entity_type="file",
        entity_id=file_record.id,
        actor_id=user_id,
        input_data={"source": source, "filename": filename},
        output_data={"imported_count": imported_count, "skipped_duplicates": skipped_duplicates},
    )

    return {"imported_count": imported_count, "skipped_duplicates": skipped_duplicates}


def _compute_match_confidence(
    tx: BankTransaction,
    payment: Payment,
) -> float:
    """Compute match confidence using composite conditions.

    Matching criteria:
    - Amount + currency match (required, base 0.5)
    - Reference number match (strong signal, +0.3)
    - Bank reference / counterparty match (+0.1 each)
    - Date proximity within +-2 business days (+0.1)
    """
    confidence = 0.5  # Base for amount + currency match (already filtered)

    # Reference number match (system-generated, highly reliable)
    ref_number_matched = False
    if payment.reference_number and tx.reference:
        ref_tx = tx.reference.lower().strip()
        ref_pay = payment.reference_number.lower().strip()
        # Exact match or tx.reference contains the full reference number as a
        # discrete token (bank statements often prepend/append text around it)
        if ref_tx == ref_pay or ref_pay in ref_tx:
            confidence += 0.3
            ref_number_matched = True

    # Bank reference match
    if tx.reference and payment.bank_reference and not ref_number_matched:
        bank_ref_tx = tx.reference.lower()
        bank_ref_pay = payment.bank_reference.lower()
        if bank_ref_tx in bank_ref_pay or bank_ref_pay in bank_ref_tx:
            confidence += 0.1

    # Counterparty match
    if tx.counterparty and payment.notes:
        counterparty = tx.counterparty.lower()
        notes = payment.notes.lower()
        if counterparty in notes or notes in counterparty:
            confidence += 0.1

    # Date proximity bonus (within +-2 business days)
    if payment.payment_date and tx.tx_date:
        day_diff = abs((tx.tx_date - payment.payment_date).days)
        if day_diff <= 2:
            confidence += 0.1

    return min(confidence, 1.0)


async def auto_match(db: AsyncSession) -> AutoMatchResult:
    """Attempt to match unmatched transactions to payments by composite criteria.

    Matching requires: amount + currency exact match.
    Then scores on: reference_number, bank_reference, counterparty, date proximity.
    Only matches with confidence >= 0.8 are accepted.
    """
    result = await db.execute(
        select(BankTransaction).where(BankTransaction.match_status == "unmatched")
    )
    unmatched_txs = list(result.scalars().all())

    matched_count = 0
    unmatched_count = 0
    results: list[AutoMatchResultItem] = []
    matched_payment_ids: set[uuid.UUID] = set()

    for tx in unmatched_txs:
        date_from = tx.tx_date - timedelta(days=3)
        date_to = tx.tx_date + timedelta(days=3)

        payment_result = await db.execute(
            select(Payment).where(
                Payment.currency == tx.currency,
                Payment.amount == tx.amount,
                Payment.payment_date >= date_from,
                Payment.payment_date <= date_to,
            )
        )
        candidates = list(payment_result.scalars().all())

        best_payment = None
        best_confidence = 0.0

        for payment in candidates:
            if payment.id in matched_payment_ids:
                continue

            confidence = _compute_match_confidence(tx, payment)

            if confidence > best_confidence:
                best_confidence = confidence
                best_payment = payment

        if best_payment is not None and best_confidence >= 0.8:
            tx.matched_payment_id = best_payment.id
            tx.match_status = "auto_matched"
            tx.match_confidence = round(best_confidence, 2)
            matched_payment_ids.add(best_payment.id)
            matched_count += 1
            results.append(
                AutoMatchResultItem(
                    tx_id=tx.id,
                    payment_id=best_payment.id,
                    confidence=best_confidence,
                )
            )
        else:
            unmatched_count += 1

    await db.flush()

    return AutoMatchResult(
        matched_count=matched_count,
        unmatched_count=unmatched_count,
        results=results,
    )


async def try_auto_match_payment(
    db: AsyncSession,
    payment: Payment,
) -> Optional[BankTransaction]:
    """Try to match a specific payment against unmatched bank transactions.

    Called automatically after payment creation to attempt immediate matching.
    Uses composite criteria: amount + currency + reference + date.
    """
    if not payment.payment_date:
        return None

    date_from = payment.payment_date - timedelta(days=3)
    date_to = payment.payment_date + timedelta(days=3)

    result = await db.execute(
        select(BankTransaction).where(
            BankTransaction.match_status == "unmatched",
            BankTransaction.currency == payment.currency,
            BankTransaction.amount == payment.amount,
            BankTransaction.tx_date >= date_from,
            BankTransaction.tx_date <= date_to,
        )
    )
    candidates = list(result.scalars().all())

    best_tx = None
    best_confidence = 0.0

    for tx in candidates:
        confidence = _compute_match_confidence(tx, payment)
        if confidence > best_confidence:
            best_confidence = confidence
            best_tx = tx

    if best_tx is not None and best_confidence >= 0.8:
        best_tx.matched_payment_id = payment.id
        best_tx.match_status = "auto_matched"
        best_tx.match_confidence = round(best_confidence, 2)
        await db.flush()
        return best_tx

    return None


async def manual_match(
    db: AsyncSession,
    tx_id: uuid.UUID,
    payment_id: uuid.UUID,
    actor_id: uuid.UUID,
) -> BankTransaction:
    tx = await _get_transaction(db, tx_id)
    result = await db.execute(select(Payment).where(Payment.id == payment_id))
    payment = result.scalar_one_or_none()
    if payment is None:
        raise ValueError(f"Payment {payment_id} not found")

    tx.matched_payment_id = payment_id
    tx.match_status = "manual_matched"
    tx.match_confidence = None
    await db.flush()

    await AuditService(db).log(
        action="bank_transaction.manual_match",
        entity_type="bank_transaction",
        entity_id=tx.id,
        actor_id=actor_id,
        input_data={"payment_id": str(payment_id)},
    )
    return tx


async def ignore_transaction(
    db: AsyncSession,
    tx_id: uuid.UUID,
    actor_id: uuid.UUID,
) -> BankTransaction:
    tx = await _get_transaction(db, tx_id)
    tx.match_status = "ignored"
    await db.flush()

    await AuditService(db).log(
        action="bank_transaction.ignore",
        entity_type="bank_transaction",
        entity_id=tx.id,
        actor_id=actor_id,
    )
    return tx


async def list_transactions(
    db: AsyncSession,
    status: Optional[str] = None,
    source: Optional[str] = None,
    page: int = 1,
    per_page: int = 20,
) -> tuple[list[BankTransaction], int]:
    query = select(BankTransaction)

    if status:
        query = query.where(BankTransaction.match_status == status)

    if source:
        query = query.where(BankTransaction.source == source)

    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar_one()

    query = query.order_by(BankTransaction.tx_date.desc()).offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(query)
    items = list(result.scalars().all())

    return items, total


async def get_transaction(db: AsyncSession, tx_id: uuid.UUID) -> BankTransaction:
    return await _get_transaction(db, tx_id)


async def reconcile_transaction(
    db: AsyncSession,
    tx_id: uuid.UUID,
    bank_account_id: uuid.UUID,
    contra_account_id: Optional[uuid.UUID],
    actor_id: uuid.UUID,
    description: Optional[str] = None,
    auto_confirm: bool = True,
    fx_rate_to_sgd: Optional[Decimal] = None,
) -> BankTransaction:
    """Reconcile a bank transaction by creating a journal entry.

    For deposits (amount > 0): debit bank_account, credit contra_account.
    For withdrawals (amount < 0): debit contra_account, credit bank_account.

    A deposit matched to a payment for an invoice whose receivable was posted at
    issue settles that receivable instead (contra defaults to the receivable account;
    revenue must not be booked twice). Foreign-currency settlements are rated and
    book the FX difference against the issue-date rate.
    """
    tx = await _get_transaction(db, tx_id)

    if tx.match_status == "reconciled":
        raise ValueError(f"BankTransaction {tx_id} is already reconciled")

    settled = await _invoice_settled_by(db, tx)
    if settled is not None:
        payment, invoice = settled
        return await _reconcile_invoice_settlement(
            db, tx, payment, invoice, bank_account_id, contra_account_id,
            actor_id, description, auto_confirm, fx_rate_to_sgd,
        )

    if contra_account_id is None:
        raise ValueError("contra_account_id is required unless the transaction settles a posted invoice")

    amount = abs(Decimal(str(tx.amount)))
    is_deposit = Decimal(str(tx.amount)) > 0
    entry_desc = description or tx.description or f"Bank transaction {tx.source_tx_id}"

    if is_deposit:
        debit_account = bank_account_id
        credit_account = contra_account_id
    else:
        debit_account = contra_account_id
        credit_account = bank_account_id

    journal_data = JournalEntryCreate(
        entry_date=tx.tx_date,
        description=entry_desc,
        source_type="bank_import",
        source_id=tx.id,
        is_confirmed=auto_confirm,
        lines=[
            JournalLineCreate(
                account_id=debit_account,
                debit=amount,
                credit=Decimal("0"),
                currency=tx.currency,
            ),
            JournalLineCreate(
                account_id=credit_account,
                debit=Decimal("0"),
                credit=amount,
                currency=tx.currency,
            ),
        ],
    )

    entry = await create_journal_entry(db, journal_data, created_by=actor_id)

    tx.match_status = "reconciled"
    tx.account_id = bank_account_id
    await db.flush()

    await AuditService(db).log(
        action="bank_transaction.reconcile",
        entity_type="bank_transaction",
        entity_id=tx.id,
        actor_id=actor_id,
        input_data={
            "journal_entry_id": str(entry.id),
            "bank_account_id": str(bank_account_id),
            "contra_account_id": str(contra_account_id),
        },
    )
    return tx


async def _get_transaction(db: AsyncSession, tx_id: uuid.UUID) -> BankTransaction:
    result = await db.execute(select(BankTransaction).where(BankTransaction.id == tx_id))
    tx = result.scalar_one_or_none()
    if tx is None:
        raise ValueError(f"BankTransaction {tx_id} not found")
    return tx


async def _invoice_settled_by(db: AsyncSession, tx: BankTransaction):
    """(payment, invoice) when a deposit is matched to a payment for an invoice with a posted receivable."""
    from app.models.invoice import Invoice

    if tx.matched_payment_id is None or Decimal(str(tx.amount)) <= 0:
        return None
    payment = (await db.execute(select(Payment).where(Payment.id == tx.matched_payment_id))).scalar_one_or_none()
    if payment is None or payment.related_entity_type != "invoice" or payment.related_entity_id is None:
        return None
    invoice = (
        await db.execute(select(Invoice).where(Invoice.id == payment.related_entity_id))
    ).scalar_one_or_none()
    if invoice is None or invoice.journal_entry_id is None:
        return None
    return payment, invoice


async def _reconcile_invoice_settlement(
    db: AsyncSession,
    tx: BankTransaction,
    payment: Payment,
    invoice,
    bank_account_id: uuid.UUID,
    contra_account_id: Optional[uuid.UUID],
    actor_id: uuid.UUID,
    description: Optional[str],
    auto_confirm: bool,
    fx_rate_to_sgd: Optional[Decimal],
) -> BankTransaction:
    from app.services import ledger

    await ledger.lock_invoice(db, invoice.id)
    if invoice.status not in ("issued", "paid"):
        raise ValueError(
            f"Invoice {invoice.invoice_number} is {invoice.status}; its receivable was reversed. "
            "Reconcile this deposit with an explicit contra account (e.g. a customer credit/refund liability)"
        )
    if payment.journal_entry_id is not None or await ledger.receivable_settled(db, invoice.id):
        raise ValueError(
            f"Invoice {invoice.invoice_number} receivable is already settled (payment journal exists); "
            "this deposit would book it twice. Mark it with `acct bank tx-ignore` or reconcile with an explicit contra"
        )

    ar_line = await ledger.receivable_line(db, invoice)
    receivable_id = ar_line.account_id
    if contra_account_id is not None and contra_account_id != receivable_id:
        raise ValueError(
            f"Invoice {invoice.invoice_number} revenue was already booked at issue; "
            "reconcile against its receivable account (omit contra_account_id)"
        )
    if not ledger.settles_in(tx.currency, invoice.currency):
        raise ValueError(
            f"A {tx.currency} deposit cannot settle {invoice.currency} invoice {invoice.invoice_number}; "
            "record the settlement manually"
        )

    bank_account = (await db.execute(select(Account).where(Account.id == bank_account_id))).scalar_one_or_none()
    if bank_account is None:
        raise ValueError(f"Bank account {bank_account_id} not found")
    if bank_account.currency != tx.currency:
        raise ValueError(f"Bank account currency {bank_account.currency} does not match deposit currency {tx.currency}")

    mapping = await ledger.get_ledger_accounts(db)
    amount = Decimal(str(tx.amount))
    if amount != Decimal(str(ar_line.debit)):
        raise ValueError(
            f"Deposit {tx.currency} {amount} differs from invoice {invoice.invoice_number} receivable "
            f"{ar_line.currency} {ar_line.debit} (e.g. bank fees); record the settlement manually"
        )

    quote = await ledger.resolve_fx_rate_to_sgd(tx.currency, tx.tx_date, fx_rate_to_sgd)
    label = invoice.invoice_number or str(invoice.id)
    lines = ledger.build_receipt_lines(
        amount=amount,
        currency=tx.currency,
        receipt_rate=quote.rate,
        wallet_id=bank_account_id,
        receivable_amount=Decimal(str(ar_line.debit)),
        receivable_currency=ar_line.currency,
        receivable_rate=Decimal(str(ar_line.fx_rate_to_sgd)),
        receivable_id=receivable_id,
        fx_gain_loss_id=mapping.fx_gain_loss,
        label=label,
    )
    entry = await create_journal_entry(
        db,
        JournalEntryCreate(
            entry_date=tx.tx_date,
            description=description or f"Invoice {label} settled by bank deposit {tx.source_tx_id}",
            source_type="bank_import",
            source_id=tx.id,
            is_confirmed=auto_confirm,
            lines=lines,
        ),
        created_by=actor_id,
    )
    payment.journal_entry_id = entry.id
    tx.match_status = "reconciled"
    tx.account_id = bank_account_id
    await db.flush()

    await AuditService(db).log(
        action="bank_transaction.reconcile",
        entity_type="bank_transaction",
        entity_id=tx.id,
        actor_id=actor_id,
        input_data={
            "journal_entry_id": str(entry.id),
            "bank_account_id": str(bank_account_id),
            "contra_account_id": str(receivable_id),
            "invoice_id": str(invoice.id),
            "fx_rate_to_sgd": str(quote.rate),
            "fx_rate_source": quote.source,
        },
    )
    return tx
