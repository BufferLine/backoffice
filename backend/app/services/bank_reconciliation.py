import uuid
from datetime import timedelta
from decimal import Decimal
from typing import BinaryIO, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

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


async def auto_match(db: AsyncSession) -> AutoMatchResult:
    """Attempt to match unmatched transactions to payments by amount, currency, and date proximity."""
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
            confidence = 0.5  # Base confidence for amount + currency + date match

            # Boost confidence if reference/counterparty matches
            if tx.reference and payment.bank_reference:
                ref_tx = tx.reference.lower()
                ref_pay = payment.bank_reference.lower()
                if ref_tx in ref_pay or ref_pay in ref_tx:
                    confidence += 0.3

            if tx.counterparty and payment.notes:
                counterparty = tx.counterparty.lower()
                notes = payment.notes.lower()
                if counterparty in notes or notes in counterparty:
                    confidence += 0.2

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
    contra_account_id: uuid.UUID,
    actor_id: uuid.UUID,
    description: Optional[str] = None,
    auto_confirm: bool = True,
) -> BankTransaction:
    """Reconcile a bank transaction by creating a journal entry.

    For deposits (amount > 0): debit bank_account, credit contra_account.
    For withdrawals (amount < 0): debit contra_account, credit bank_account.
    """
    tx = await _get_transaction(db, tx_id)

    if tx.match_status == "reconciled":
        raise ValueError(f"BankTransaction {tx_id} is already reconciled")

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
