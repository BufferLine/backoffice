"""Integration sync orchestration service."""
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations import get_provider
from app.integrations.base import BalanceSyncProvider, TransactionSyncProvider
from app.integrations.capabilities import Capability
from app.models.account import Account
from app.models.bank_transaction import BankTransaction
from app.models.integration import IntegrationEvent, IntegrationSyncState

logger = logging.getLogger(__name__)

_MAX_CONSECUTIVE_FAILURES = 5


async def _get_or_create_sync_state(
    db: AsyncSession,
    provider: str,
    capability: str,
    account_id: uuid.UUID | None = None,
) -> IntegrationSyncState:
    result = await db.execute(
        select(IntegrationSyncState).where(
            IntegrationSyncState.provider == provider,
            IntegrationSyncState.capability == capability,
            IntegrationSyncState.account_id == account_id,
        )
    )
    state = result.scalar_one_or_none()
    if state is None:
        state = IntegrationSyncState(
            provider=provider,
            capability=capability,
            account_id=account_id,
        )
        db.add(state)
        await db.flush()
    return state


async def _log_event(
    db: AsyncSession,
    provider: str,
    direction: str,
    event_type: str,
    status: str,
    result_json: dict | None = None,
    error_message: str | None = None,
) -> IntegrationEvent:
    event = IntegrationEvent(
        provider=provider,
        direction=direction,
        event_type=event_type,
        status=status,
        result_json=result_json,
        error_message=error_message,
    )
    db.add(event)
    await db.flush()
    return event


async def run_sync(
    db: AsyncSession,
    provider_name: str,
    capability: str,
) -> dict:
    """
    Orchestrate a full sync run for the given provider and capability.

    Returns a summary dict: {inserted, skipped, errors}.
    """
    provider = get_provider(provider_name)

    if capability == Capability.SYNC_TRANSACTIONS:
        if not isinstance(provider, TransactionSyncProvider):
            raise ValueError(f"Provider {provider_name!r} does not support sync_transactions")
        return await _sync_transactions(db, provider_name, provider)

    if capability == Capability.SYNC_BALANCE:
        if not isinstance(provider, BalanceSyncProvider):
            raise ValueError(f"Provider {provider_name!r} does not support sync_balance")
        return await _sync_balances(db, provider_name, provider)

    raise ValueError(f"Unsupported capability: {capability!r}")


async def _sync_transactions(
    db: AsyncSession,
    provider_name: str,
    provider: TransactionSyncProvider,
) -> dict:
    """Sync transactions for a provider. Maps accounts via Account.statement_source."""

    # Find accounts linked to this provider
    result = await db.execute(
        select(Account).where(Account.statement_source == provider_name, Account.is_active == True)  # noqa: E712
    )
    accounts = result.scalars().all()
    account_id: uuid.UUID | None = accounts[0].id if accounts else None

    state = await _get_or_create_sync_state(db, provider_name, Capability.SYNC_TRANSACTIONS, account_id)

    if state.consecutive_failures >= _MAX_CONSECUTIVE_FAILURES:
        logger.warning(
            "Skipping %s sync_transactions: %d consecutive failures",
            provider_name,
            state.consecutive_failures,
        )
        return {"inserted": 0, "skipped": 0, "errors": state.consecutive_failures}

    inserted = 0
    skipped = 0
    errors = 0
    cursor = state.last_cursor
    since = state.last_synced_at.isoformat() if state.last_synced_at else None

    try:
        while True:
            transactions, next_cursor = await provider.sync_transactions(since=since, cursor=cursor)

            for tx in transactions:
                stmt = (
                    pg_insert(BankTransaction)
                    .values(
                        id=uuid.uuid4(),
                        source=provider_name,
                        source_tx_id=tx.source_tx_id,
                        tx_date=tx.tx_date,
                        amount=tx.amount,
                        currency=tx.currency,
                        counterparty=tx.counterparty,
                        reference=tx.reference,
                        description=tx.description,
                        match_status="unmatched",
                        raw_data_json=tx.raw_data,
                        account_id=account_id,
                    )
                    .on_conflict_do_nothing(
                        constraint="uq_bank_transactions_source_tx"
                    )
                )
                result = await db.execute(stmt)
                if result.rowcount and result.rowcount > 0:
                    inserted += 1
                else:
                    skipped += 1

            state.last_cursor = next_cursor
            await db.flush()

            if next_cursor is None:
                break
            cursor = next_cursor

        state.last_synced_at = datetime.now(timezone.utc)
        state.consecutive_failures = 0
        state.last_error = None
        await db.flush()

        await _log_event(
            db,
            provider_name,
            "outbound",
            "sync_transactions",
            "processed",
            result_json={"inserted": inserted, "skipped": skipped},
        )

    except Exception as exc:
        errors += 1
        state.consecutive_failures += 1
        state.last_error = str(exc)
        await db.flush()

        await _log_event(
            db,
            provider_name,
            "outbound",
            "sync_transactions",
            "failed",
            error_message=str(exc),
        )
        logger.exception("Error syncing transactions for %s", provider_name)

    return {"inserted": inserted, "skipped": skipped, "errors": errors}


async def _sync_balances(
    db: AsyncSession,
    provider_name: str,
    provider: BalanceSyncProvider,
) -> dict:
    """Sync balances and update Account.metadata_json via jsonb_set."""
    state = await _get_or_create_sync_state(db, provider_name, Capability.SYNC_BALANCE)

    if state.consecutive_failures >= _MAX_CONSECUTIVE_FAILURES:
        logger.warning(
            "Skipping %s sync_balance: %d consecutive failures",
            provider_name,
            state.consecutive_failures,
        )
        return {"inserted": 0, "skipped": 0, "errors": state.consecutive_failures}

    updated = 0
    errors = 0

    try:
        balances = await provider.sync_balances()

        for balance_info in balances:
            # Find matching account by statement_source and currency
            result = await db.execute(
                select(Account).where(
                    Account.statement_source == provider_name,
                    Account.currency == balance_info.currency,
                    Account.is_active == True,  # noqa: E712
                )
            )
            account = result.scalar_one_or_none()
            if account is None:
                continue

            # Use jsonb_set pattern to update only the live_balance key
            # without replacing the entire metadata_json object
            await db.execute(
                text(
                    "UPDATE accounts SET metadata_json = "
                    "jsonb_set(COALESCE(metadata_json, '{}'), '{live_balance}', :val::jsonb) "
                    "WHERE id = :account_id"
                ),
                {
                    "val": f'{{"available": "{balance_info.available_balance}", "pending": "{balance_info.pending_balance}", "as_of": "{balance_info.as_of.isoformat() if balance_info.as_of else None}", "currency": "{balance_info.currency}"}}',
                    "account_id": str(account.id),
                },
            )
            updated += 1

        state.last_synced_at = datetime.now(timezone.utc)
        state.consecutive_failures = 0
        state.last_error = None
        await db.flush()

        await _log_event(
            db,
            provider_name,
            "outbound",
            "sync_balance",
            "processed",
            result_json={"updated_accounts": updated},
        )

    except Exception as exc:
        errors += 1
        state.consecutive_failures += 1
        state.last_error = str(exc)
        await db.flush()

        await _log_event(
            db,
            provider_name,
            "outbound",
            "sync_balance",
            "failed",
            error_message=str(exc),
        )
        logger.exception("Error syncing balances for %s", provider_name)

    return {"inserted": updated, "skipped": 0, "errors": errors}
