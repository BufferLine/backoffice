"""Accrual ledger postings for invoices, crypto receipts, and FX carrying cost.

The functional currency is SGD. Every journal line carries ``fx_rate_to_sgd`` so
foreign-currency (and stablecoin) balances keep both their native quantity and
their SGD carrying value:

- Invoice issue:   Dr Receivable (invoice ccy, issue-date rate) / Cr Revenue (SGD) / Cr GST output (SGD)
- Crypto receipt:  Dr Wallet (coin qty, receipt-date rate) / Cr Receivable (issue-date carrying value)
                   ± FX gain/loss (SGD) for the rate difference
- FX conversion:   see ``app.services.fx_conversion`` — the sold currency leaves at its
                   carrying rate (``carrying_rate_to_sgd``) and the difference is FX gain/loss.

Ledger accounts are configured once in ``CompanySettings.metadata_json["ledger_accounts"]``.
Posting is opt-in: without a configured mapping, invoices issue exactly as before.
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.account import Account
from app.models.company import CompanySettings
from app.models.invoice import Invoice
from app.models.journal import JournalEntry, JournalLine
from app.models.payment import Payment
from app.schemas.journal import JournalEntryCreate, JournalLineCreate
from app.schemas.payment import PaymentCreate
from app.services.audit import AuditService
from app.services.journal import create_journal_entry

logger = logging.getLogger(__name__)

FUNCTIONAL_CURRENCY = "SGD"
_LOCAL_TZ = ZoneInfo("Asia/Singapore")

# Stablecoins are valued at the fiat they track. A USD invoice can be settled in USDC/USDT.
STABLECOIN_PEGS: dict[str, str] = {"USDC": "USD", "USDT": "USD"}

_RATE_Q = Decimal("0.000001")  # journal_lines.fx_rate_to_sgd is NUMERIC(19, 6)
_SGD_Q = Decimal("0.01")

_METADATA_KEY = "ledger_accounts"


def q_rate(value: Decimal) -> Decimal:
    return Decimal(value).quantize(_RATE_Q, rounding=ROUND_HALF_UP)


def q_sgd(value: Decimal) -> Decimal:
    return Decimal(value).quantize(_SGD_Q, rounding=ROUND_HALF_UP)


def rate_currency(currency: str) -> str:
    """The fiat currency used to value ``currency`` (stablecoins map to their peg)."""
    code = currency.upper()
    return STABLECOIN_PEGS.get(code, code)


def settles_in(payment_currency: str, invoice_currency: str) -> bool:
    """Whether a payment in ``payment_currency`` can settle an invoice in ``invoice_currency``."""
    return rate_currency(payment_currency) == rate_currency(invoice_currency)


def today_local() -> date:
    return datetime.now(_LOCAL_TZ).date()


# --- Account mapping -------------------------------------------------------


@dataclass
class LedgerAccounts:
    receivable: dict[str, uuid.UUID] = field(default_factory=dict)
    revenue: Optional[uuid.UUID] = None
    gst_output: Optional[uuid.UUID] = None
    fx_gain_loss: Optional[uuid.UUID] = None

    @property
    def configured(self) -> bool:
        return self.revenue is not None and bool(self.receivable)

    def receivable_for(self, currency: str) -> uuid.UUID:
        account_id = self.receivable.get(currency.upper())
        if account_id is None:
            raise ValueError(
                f"No receivable account mapped for {currency}. "
                f"Set one with `acct ledger set --receivable {currency.upper()}=<account-id>`."
            )
        return account_id

    def require_fx_gain_loss(self) -> uuid.UUID:
        if self.fx_gain_loss is None:
            raise ValueError("No FX gain/loss account mapped. Set one with `acct ledger set --fx-gain-loss <account-id>`.")
        return self.fx_gain_loss

    def to_json(self) -> dict:
        return {
            "receivable": {k: str(v) for k, v in sorted(self.receivable.items())},
            "revenue": str(self.revenue) if self.revenue else None,
            "gst_output": str(self.gst_output) if self.gst_output else None,
            "fx_gain_loss": str(self.fx_gain_loss) if self.fx_gain_loss else None,
        }

    @classmethod
    def from_json(cls, data: dict | None) -> "LedgerAccounts":
        data = data or {}

        def _uuid(v):
            return uuid.UUID(str(v)) if v else None

        return cls(
            receivable={k.upper(): uuid.UUID(str(v)) for k, v in (data.get("receivable") or {}).items() if v},
            revenue=_uuid(data.get("revenue")),
            gst_output=_uuid(data.get("gst_output")),
            fx_gain_loss=_uuid(data.get("fx_gain_loss")),
        )


async def _company(db: AsyncSession) -> Optional[CompanySettings]:
    return (await db.execute(select(CompanySettings).limit(1))).scalar_one_or_none()


async def get_ledger_accounts(db: AsyncSession) -> LedgerAccounts:
    company = await _company(db)
    if company is None:
        return LedgerAccounts()
    return LedgerAccounts.from_json((company.metadata_json or {}).get(_METADATA_KEY))


async def _require_account(
    db: AsyncSession,
    account_id: uuid.UUID,
    role: str,
    currency: Optional[str] = None,
    classes: Optional[set[str]] = None,
) -> Account:
    account = (await db.execute(select(Account).where(Account.id == account_id))).scalar_one_or_none()
    if account is None:
        raise ValueError(f"{role} account {account_id} not found")
    if not account.is_active:
        raise ValueError(f"{role} account {account.name} is inactive")
    if currency and account.currency != currency:
        raise ValueError(f"{role} account {account.name} must be in {currency}, not {account.currency}")
    if classes and account.account_class not in classes:
        raise ValueError(
            f"{role} account {account.name} must have account_class in {sorted(classes)}, "
            f"not {account.account_class!r}"
        )
    return account


async def set_ledger_accounts(
    db: AsyncSession,
    actor_id: uuid.UUID,
    receivable: Optional[dict[str, uuid.UUID]] = None,
    revenue: Optional[uuid.UUID] = None,
    gst_output: Optional[uuid.UUID] = None,
    fx_gain_loss: Optional[uuid.UUID] = None,
) -> LedgerAccounts:
    """Merge the given mappings into the stored ledger account mapping (validated)."""
    company = await _company(db)
    if company is None:
        raise ValueError("Company settings not initialised; run `acct init` first")

    current = LedgerAccounts.from_json((company.metadata_json or {}).get(_METADATA_KEY))

    for ccy, account_id in (receivable or {}).items():
        ccy = ccy.upper()
        await _require_account(db, account_id, f"Receivable ({ccy})", currency=ccy, classes={"asset"})
        current.receivable[ccy] = account_id
    if revenue:
        await _require_account(db, revenue, "Revenue", currency=FUNCTIONAL_CURRENCY, classes={"revenue"})
        current.revenue = revenue
    if gst_output:
        await _require_account(db, gst_output, "GST output", currency=FUNCTIONAL_CURRENCY, classes={"liability"})
        current.gst_output = gst_output
    if fx_gain_loss:
        await _require_account(
            db, fx_gain_loss, "FX gain/loss", currency=FUNCTIONAL_CURRENCY, classes={"revenue", "expense"}
        )
        current.fx_gain_loss = fx_gain_loss

    # Reassign so SQLAlchemy detects the JSONB change.
    metadata = dict(company.metadata_json or {})
    metadata[_METADATA_KEY] = current.to_json()
    company.metadata_json = metadata
    await db.flush()

    await AuditService(db).log(
        action="ledger.set_accounts",
        entity_type="company_settings",
        entity_id=company.id,
        actor_id=actor_id,
        output_data=current.to_json(),
    )
    return current


# --- FX rates --------------------------------------------------------------


@dataclass
class RateQuote:
    rate: Decimal  # SGD per 1 unit of the currency
    source: str


async def _fetch_live_rate(base_currency: str) -> Decimal:
    if not (settings.AIRWALLEX_CLIENT_ID and settings.AIRWALLEX_API_KEY):
        raise ValueError(
            f"No {base_currency}/SGD rate given and Airwallex is not configured to fetch one; pass fx_rate_to_sgd"
        )
    import app.integrations.providers  # noqa: F401 — register providers
    from app.integrations import get_provider

    try:
        provider = get_provider("airwallex")
        quote = await provider.fetch_fx_rate(sell_currency=base_currency, buy_currency=FUNCTIONAL_CURRENCY)
        rate = Decimal(str(quote.rate))
    except Exception as exc:  # network/provider errors → actionable message, not a 500
        raise ValueError(
            f"Could not fetch today's {base_currency}/SGD rate from Airwallex ({exc}); pass fx_rate_to_sgd"
        ) from exc
    if rate <= 0:
        raise ValueError(f"Airwallex returned a non-positive {base_currency}/SGD rate; pass fx_rate_to_sgd")
    pair = str((quote.raw_data or {}).get("currency_pair") or "").upper()
    if pair == f"{FUNCTIONAL_CURRENCY}{base_currency}":
        rate = Decimal("1") / rate  # quoted as foreign per SGD
    return rate


async def resolve_fx_rate_to_sgd(
    currency: str,
    on_date: date,
    explicit_rate: Optional[Decimal] = None,
) -> RateQuote:
    """SGD per 1 unit of ``currency`` on ``on_date``.

    Order: SGD (and SGD-pegged) → 1; an explicit rate; today's live Airwallex rate.
    Historical rates are not fetched — a back-dated posting needs an explicit rate.
    """
    base = rate_currency(currency)
    if base == FUNCTIONAL_CURRENCY:
        return RateQuote(Decimal("1"), "functional")
    if explicit_rate is not None:
        if explicit_rate <= 0:
            raise ValueError("fx_rate_to_sgd must be positive")
        return RateQuote(q_rate(explicit_rate), "manual")
    if on_date != today_local():
        raise ValueError(
            f"fx_rate_to_sgd is required for {currency} on {on_date.isoformat()}: "
            "only today's rate can be fetched automatically"
        )
    rate = await _fetch_live_rate(base)
    source = "airwallex" if base == currency.upper() else f"airwallex:{base}"
    return RateQuote(q_rate(rate), source)


# --- Generic helpers -------------------------------------------------------


async def carrying_rate_to_sgd(db: AsyncSession, account_id: uuid.UUID, as_of: date) -> Optional[Decimal]:
    """Weighted-average SGD carrying rate of an account as of ``as_of``.

    Uses confirmed, rated journal lines dated on or before ``as_of``.
    Returns None when the account has no positive rated balance.
    """
    native = func.coalesce(func.sum(JournalLine.debit - JournalLine.credit), 0)
    sgd = func.coalesce(func.sum((JournalLine.debit - JournalLine.credit) * JournalLine.fx_rate_to_sgd), 0)
    row = (
        await db.execute(
            select(native, sgd)
            .join(JournalEntry, JournalLine.journal_entry_id == JournalEntry.id)
            .where(
                JournalLine.account_id == account_id,
                JournalLine.fx_rate_to_sgd.is_not(None),
                JournalEntry.is_confirmed.is_(True),
                JournalEntry.entry_date <= as_of,
            )
        )
    ).one()
    native_balance, sgd_balance = Decimal(str(row[0])), Decimal(str(row[1]))
    if native_balance <= 0:
        return None
    return q_rate(sgd_balance / native_balance)


def fx_difference_line(diff_sgd: Decimal, fx_account_id: uuid.UUID, description: str) -> Optional[JournalLineCreate]:
    """A balancing SGD line: a positive difference is a gain (credit), negative a loss (debit)."""
    diff = q_sgd(diff_sgd)
    if diff == 0:
        return None
    return JournalLineCreate(
        account_id=fx_account_id,
        debit=-diff if diff < 0 else Decimal("0"),
        credit=diff if diff > 0 else Decimal("0"),
        currency=FUNCTIONAL_CURRENCY,
        fx_rate_to_sgd=Decimal("1"),
        description=f"{'FX gain' if diff > 0 else 'FX loss'}: {description}",
    )


async def reverse_journal_entry(
    db: AsyncSession,
    entry_id: uuid.UUID,
    entry_date: date,
    description: str,
    source_type: str,
    source_id: Optional[uuid.UUID],
    actor_id: uuid.UUID,
) -> JournalEntry:
    original = (await db.execute(select(JournalEntry).where(JournalEntry.id == entry_id))).scalar_one()
    lines = [
        JournalLineCreate(
            account_id=line.account_id,
            debit=Decimal(str(line.credit)),
            credit=Decimal(str(line.debit)),
            currency=line.currency,
            fx_rate_to_sgd=Decimal(str(line.fx_rate_to_sgd)) if line.fx_rate_to_sgd is not None else None,
            description=f"Reversal: {line.description or ''}".strip(),
        )
        for line in original.lines
    ]
    return await create_journal_entry(
        db,
        JournalEntryCreate(
            entry_date=entry_date,
            description=description,
            source_type=source_type,
            source_id=source_id,
            is_confirmed=True,
            lines=lines,
        ),
        created_by=actor_id,
    )


# --- Invoice issue (accounts receivable) ------------------------------------


async def lock_invoice(db: AsyncSession, invoice_id: uuid.UUID) -> Invoice:
    """Re-read an invoice with a row lock so concurrent posts/receipts serialise.

    Pending changes are flushed first so ``populate_existing`` cannot discard them.
    """
    await db.flush()
    invoice = (
        await db.execute(
            select(Invoice).where(Invoice.id == invoice_id).with_for_update().execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if invoice is None:
        raise ValueError(f"Invoice {invoice_id} not found")
    return invoice


async def receivable_settled(db: AsyncSession, invoice_id: uuid.UUID) -> bool:
    """Whether a settlement journal (crypto receipt or bank reconcile) exists for the invoice."""
    count = (
        await db.execute(
            select(func.count(Payment.id)).where(
                Payment.related_entity_type == "invoice",
                Payment.related_entity_id == invoice_id,
                Payment.journal_entry_id.is_not(None),
            )
        )
    ).scalar_one()
    return count > 0


def build_invoice_issue_lines(
    total: Decimal,
    tax: Decimal,
    currency: str,
    rate: Decimal,
    receivable_id: uuid.UUID,
    revenue_id: uuid.UUID,
    gst_output_id: Optional[uuid.UUID],
    label: str,
) -> list[JournalLineCreate]:
    """Dr receivable (native) / Cr revenue (SGD) / Cr GST output (SGD).

    SGD amounts are rounded to cents; revenue absorbs the rounding so the SGD side
    totals exactly ``round(total * rate)``.
    """
    if tax > 0 and gst_output_id is None:
        raise ValueError("Invoice has GST but no GST output account is mapped (`acct ledger set --gst-output`)")
    is_sgd = currency == FUNCTIONAL_CURRENCY
    total_sgd = total if is_sgd else q_sgd(total * rate)
    gst_sgd = tax if is_sgd else q_sgd(tax * rate)
    revenue_sgd = total_sgd - gst_sgd

    lines = [
        JournalLineCreate(
            account_id=receivable_id,
            debit=total,
            currency=currency,
            fx_rate_to_sgd=Decimal("1") if is_sgd else rate,
            description=f"Receivable {label}",
        )
    ]
    if revenue_sgd > 0:
        lines.append(
            JournalLineCreate(
                account_id=revenue_id,
                credit=revenue_sgd,
                currency=FUNCTIONAL_CURRENCY,
                fx_rate_to_sgd=Decimal("1"),
                description=f"Revenue {label}",
            )
        )
    if gst_sgd > 0:
        lines.append(
            JournalLineCreate(
                account_id=gst_output_id,
                credit=gst_sgd,
                currency=FUNCTIONAL_CURRENCY,
                fx_rate_to_sgd=Decimal("1"),
                description=f"GST output {label}",
            )
        )
    return lines


async def post_invoice_issue(
    db: AsyncSession,
    invoice: Invoice,
    actor_id: uuid.UUID,
    fx_rate_to_sgd: Optional[Decimal] = None,
    entry_date: Optional[date] = None,
) -> Optional[JournalEntry]:
    """Post the accounts-receivable entry for an invoice.

    Returns None (and posts nothing) when no ledger mapping is configured or the total is zero.
    """
    await lock_invoice(db, invoice.id)  # refreshes ``invoice`` in place (same identity)
    if invoice.journal_entry_id is not None:
        raise ValueError(f"Invoice {invoice.invoice_number} already has a journal entry")
    mapping = await get_ledger_accounts(db)
    if not mapping.configured:
        return None

    total = Decimal(str(invoice.total_amount))
    tax = Decimal(str(invoice.tax_amount or 0))
    if total <= 0:
        return None

    posting_date = entry_date or invoice.issue_date or today_local()
    quote = await resolve_fx_rate_to_sgd(invoice.currency, posting_date, fx_rate_to_sgd)
    label = invoice.invoice_number or str(invoice.id)
    lines = build_invoice_issue_lines(
        total=total,
        tax=tax,
        currency=invoice.currency,
        rate=quote.rate,
        receivable_id=mapping.receivable_for(invoice.currency),
        revenue_id=mapping.revenue,
        gst_output_id=mapping.gst_output,
        label=label,
    )
    entry = await create_journal_entry(
        db,
        JournalEntryCreate(
            entry_date=posting_date,
            description=f"Invoice {label} issued ({invoice.currency} {total:,.2f} @ {quote.rate} SGD, {quote.source})",
            source_type="invoice",
            source_id=invoice.id,
            is_confirmed=True,
            lines=lines,
        ),
        created_by=actor_id,
    )
    invoice.journal_entry_id = entry.id
    await db.flush()
    return entry


async def receivable_line(db: AsyncSession, invoice: Invoice) -> JournalLine:
    """The receivable debit line of an invoice's issue entry (independent of the current mapping)."""
    if invoice.journal_entry_id is None:
        raise ValueError(
            f"Invoice {invoice.invoice_number} has no receivable journal entry; "
            f"post it first with `acct invoice post-journal {invoice.id}`"
        )
    line = (
        await db.execute(
            select(JournalLine).where(
                JournalLine.journal_entry_id == invoice.journal_entry_id,
                JournalLine.currency == invoice.currency,
                JournalLine.debit > 0,
            )
        )
    ).scalars().first()
    if line is None or line.fx_rate_to_sgd is None:
        raise ValueError(f"Invoice {invoice.invoice_number} journal entry has no rated receivable line")
    return line


# --- Crypto receipt --------------------------------------------------------


def build_receipt_lines(
    amount: Decimal,
    currency: str,
    receipt_rate: Decimal,
    wallet_id: uuid.UUID,
    receivable_amount: Decimal,
    receivable_currency: str,
    receivable_rate: Decimal,
    receivable_id: uuid.UUID,
    fx_gain_loss_id: Optional[uuid.UUID],
    label: str,
) -> list[JournalLineCreate]:
    """Dr wallet (receipt rate) / Cr receivable (issue rate) ± FX gain/loss."""
    lines = [
        JournalLineCreate(
            account_id=wallet_id,
            debit=amount,
            currency=currency,
            fx_rate_to_sgd=receipt_rate,
            description=f"Received {currency} {amount} for {label}",
        ),
        JournalLineCreate(
            account_id=receivable_id,
            credit=receivable_amount,
            currency=receivable_currency,
            fx_rate_to_sgd=receivable_rate,
            description=f"Settle receivable {label}",
        ),
    ]
    diff = amount * receipt_rate - receivable_amount * receivable_rate
    if q_sgd(diff) != 0:
        if fx_gain_loss_id is None:
            raise ValueError("No FX gain/loss account mapped. Set one with `acct ledger set --fx-gain-loss <account-id>`.")
        fx_line = fx_difference_line(diff, fx_gain_loss_id, label)
        if fx_line is not None:
            lines.append(fx_line)
    return lines


async def receive_crypto_payment(
    db: AsyncSession,
    invoice_id: uuid.UUID,
    wallet_account_id: uuid.UUID,
    amount: Decimal,
    currency: str,
    actor_id: uuid.UUID,
    tx_hash: Optional[str] = None,
    chain_id: Optional[str] = None,
    payment_date: Optional[date] = None,
    fx_rate_to_sgd: Optional[Decimal] = None,
    notes: Optional[str] = None,
    skip_verification: bool = False,
    skip_reason: Optional[str] = None,
) -> Payment:
    """Record a stablecoin/crypto receipt for an issued invoice in one step.

    Verifies the transfer on-chain (canonical token contract, recipient = the wallet
    account's address, exact amount, confirmations), then records the payment, posts the
    receipt journal entry, and marks the invoice paid. Verification can only be skipped
    explicitly with a reason, which is stored on the payment and in the audit log.
    """
    from app.services import invoice as invoice_service
    from app.services import onchain
    from app.services import payment as payment_service

    currency = currency.upper()
    if skip_verification:
        reason = (skip_reason or "").strip()
        if len(reason) < 15:
            raise ValueError("skip_reason must explain why on-chain verification is skipped (at least 15 characters)")
        tx_hash = onchain.canonical_tx_hash(tx_hash) if tx_hash else None
        chain_id = chain_id.strip().lower() if chain_id else None
    else:
        chain_id = onchain.normalize_chain(chain_id)
        tx_hash = onchain.normalize_tx_hash(tx_hash)

    invoice = await invoice_service.get_invoice(db, invoice_id)
    if invoice is None:
        raise ValueError(f"Invoice {invoice_id} not found")

    async def precheck() -> None:
        """Checks repeated after taking the row lock (state may change during the RPC call)."""
        if invoice.status != "issued":
            raise ValueError(f"Invoice must be 'issued' to receive payment, current: {invoice.status}")
        if not settles_in(currency, invoice.currency):
            raise ValueError(f"A {currency} payment cannot settle a {invoice.currency} invoice")
        total = Decimal(str(invoice.total_amount))
        if amount != total:
            raise ValueError(
                f"Received amount {currency} {amount} does not equal invoice total {invoice.currency} {total}; "
                "partial and over-payments are not supported"
            )
        if tx_hash:
            duplicate = (
                await db.execute(select(Payment.id).where(func.lower(Payment.tx_hash) == tx_hash.lower()))
            ).first()
            if duplicate is not None:
                raise ValueError(f"Duplicate tx_hash: {tx_hash} is already recorded")
        if await receivable_settled(db, invoice.id):
            raise ValueError(f"Invoice {invoice.invoice_number} receivable is already settled")

    await precheck()
    wallet = await _require_account(db, wallet_account_id, "Wallet", currency=currency)

    if skip_verification:
        verification = {"skipped": True, "reason": reason, "chain": chain_id}
    else:
        if not wallet.wallet_address:
            raise ValueError(
                f"Wallet account {wallet.name} has no wallet_address to verify against; "
                f"an admin can set it with `acct account update {wallet.id} --wallet-address 0x...`"
            )
        if wallet.chain_id:
            try:
                wallet_chain = onchain.normalize_chain(wallet.chain_id)
            except onchain.OnchainVerificationError:
                wallet_chain = wallet.chain_id
            if wallet_chain != chain_id:
                raise onchain.OnchainVerificationError(
                    f"Wallet account {wallet.name} is on {wallet.chain_id}, but the transfer is on {chain_id}"
                )
        # Query the chain before taking the invoice row lock (RPC can take seconds).
        result = await onchain.verify_stablecoin_transfer(
            chain=chain_id, tx_hash=tx_hash, currency=currency, to_address=wallet.wallet_address,
            expected_amount=amount,
        )
        if result.verified and result.block_timestamp is not None and invoice.issue_date is not None:
            if result.block_timestamp.astimezone(_LOCAL_TZ).date() < invoice.issue_date:
                result.problems.append(
                    f"transfer ({result.block_timestamp.astimezone(_LOCAL_TZ).date()}) predates the invoice "
                    f"issue date ({invoice.issue_date})"
                )
        if result.verified:
            own = {
                (addr or "").lower()
                for (addr,) in (
                    await db.execute(select(Account.wallet_address).where(Account.wallet_address.is_not(None)))
                ).all()
            }
            internal = sorted(own & set(result.from_addresses))
            if internal:
                result.problems.append(f"sent from our own wallet {', '.join(internal)} (internal transfer)")
        result.verified = not result.problems
        if not result.verified:
            logger.warning(
                "On-chain verification failed for invoice %s tx %s on %s: %s",
                invoice.invoice_number, tx_hash, chain_id, "; ".join(result.problems),
            )
            raise onchain.OnchainVerificationError(
                "On-chain verification failed: " + "; ".join(result.problems) + f" ({result.explorer_url})",
                result,
            )
        verification = result.to_json()
        if payment_date is None and result.block_timestamp is not None:
            payment_date = result.block_timestamp.astimezone(_LOCAL_TZ).date()

    await lock_invoice(db, invoice_id)  # serialise concurrent receipts for this invoice
    await precheck()

    mapping = await get_ledger_accounts(db)
    if not mapping.configured:
        raise ValueError("Ledger accounts are not configured; run `acct ledger set` first")
    ar_line = await receivable_line(db, invoice)
    receivable_id = ar_line.account_id

    paid_on = payment_date or today_local()
    quote = await resolve_fx_rate_to_sgd(currency, paid_on, fx_rate_to_sgd)
    label = invoice.invoice_number or str(invoice.id)

    payment = await payment_service.record_payment(
        db,
        PaymentCreate(
            payment_type="crypto",
            related_entity_type="invoice",
            related_entity_id=invoice.id,
            payment_date=paid_on,
            currency=currency,
            amount=amount,
            fx_rate_to_sgd=quote.rate,
            fx_rate_date=paid_on,
            fx_rate_source=quote.source,
            tx_hash=tx_hash,
            chain_id=chain_id,
            notes=notes,
        ),
        created_by=actor_id,
    )

    lines = build_receipt_lines(
        amount=amount,
        currency=currency,
        receipt_rate=quote.rate,
        wallet_id=wallet_account_id,
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
            entry_date=paid_on,
            description=(
                f"{currency} {amount} received for invoice {label} @ {quote.rate} SGD ({quote.source})"
                + (f", tx {tx_hash}" if tx_hash else "")
            ),
            source_type="payment",
            source_id=payment.id,
            is_confirmed=True,
            lines=lines,
        ),
        created_by=actor_id,
    )
    payment.journal_entry_id = entry.id
    payment.onchain_verification = verification
    await db.flush()

    await AuditService(db).log(
        action="payment.onchain_verification_skipped" if skip_verification else "payment.onchain_verified",
        entity_type="payment",
        entity_id=payment.id,
        actor_id=actor_id,
        output_data=verification,
    )

    await invoice_service.mark_paid(db=db, invoice=invoice, payment_id=payment.id, user_id=actor_id)
    return payment
