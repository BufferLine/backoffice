import mimetypes
from pathlib import Path
from typing import Optional

import typer

from acct.amounts import decimal_amount
from acct.api_client import api_get, api_post
from acct.formatters import print_json, print_success, print_table

app = typer.Typer(help="Payment recording commands")


@app.command()
def record(
    type: str = typer.Option(..., "--type", help="Payment type: bank_transfer|crypto|cash"),
    entity: str = typer.Option(
        ..., "--entity", help="Entity reference, e.g. invoice:<id> or payroll_run:<id>"
    ),
    amount: str = typer.Option(..., "--amount", help="Payment amount", callback=decimal_amount),
    currency: str = typer.Option("SGD", "--currency", help="Currency code"),
    tx_hash: Optional[str] = typer.Option(None, "--tx-hash", help="Crypto transaction hash"),
    chain: Optional[str] = typer.Option(None, "--chain", help="Blockchain network name"),
    date: Optional[str] = typer.Option(None, "--date", help="Payment date (YYYY-MM-DD)"),
    reference: Optional[str] = typer.Option(None, "--reference", help="Bank reference number"),
) -> None:
    """Record a payment against an entity."""
    entity_type, _, entity_id = entity.partition(":")
    payload: dict = {
        "payment_type": type,
        "related_entity_type": entity_type,
        "related_entity_id": entity_id,
        "amount": amount,
        "currency": currency,
    }
    if tx_hash:
        payload["tx_hash"] = tx_hash
    if chain:
        payload["chain_id"] = chain
    if date:
        payload["payment_date"] = date
    if reference:
        payload["bank_reference"] = reference
    data = api_post("/api/payments", json_data=payload)
    print_success(f"Payment recorded: {data['id']}")
    print_json(data)


@app.command()
def receive_crypto(
    invoice: str = typer.Option(..., "--invoice", help="Issued invoice ID"),
    account: str = typer.Option(..., "--account", help="Wallet account ID that received the coins (e.g. Coinbase USDC)"),
    amount: str = typer.Option(..., "--amount", help="Amount received (must equal the invoice total)", callback=decimal_amount),
    currency: str = typer.Option("USDC", "--currency", help="Coin received: USDC|USDT (settles a USD invoice)"),
    tx_hash: Optional[str] = typer.Option(None, "--tx-hash", help="On-chain transaction hash (required unless --skip-verify)"),
    chain: Optional[str] = typer.Option(None, "--chain", help="Network: base|ethereum (required unless --skip-verify)"),
    date: Optional[str] = typer.Option(None, "--date", help="Receipt date (YYYY-MM-DD; default: block date in SGT)"),
    fx_rate: Optional[str] = typer.Option(
        None, "--fx-rate",
        help="SGD per 1 coin on the receipt date. Required unless the receipt date (default: the block's "
        "SGT date) is today, when Airwallex USD/SGD is used",
        callback=decimal_amount,
    ),
    notes: Optional[str] = typer.Option(None, "--notes", help="Notes"),
    skip_verify: bool = typer.Option(
        False, "--skip-verify", help="Do not verify on-chain (e.g. split transfer); requires --skip-reason",
    ),
    skip_reason: Optional[str] = typer.Option(
        None, "--skip-reason", help="Why verification is skipped, >= 15 chars (audited; needs payment:skip_verification)",
    ),
) -> None:
    """Record a stablecoin receipt: on-chain check + payment + receipt journal + invoice paid.

    The transaction is verified on-chain first: the canonical USDC/USDT contract on the
    chain, sent to the wallet account's wallet_address, for exactly --amount, with enough
    confirmations. Any mismatch rejects the receipt and nothing is recorded.
    """
    if skip_verify and not skip_reason:
        raise typer.BadParameter("--skip-verify requires --skip-reason")
    payload: dict = {
        "invoice_id": invoice,
        "wallet_account_id": account,
        "amount": amount,
        "currency": currency.upper(),
    }
    for key, value in (
        ("tx_hash", tx_hash), ("chain_id", chain), ("payment_date", date),
        ("fx_rate_to_sgd", fx_rate), ("notes", notes), ("skip_reason", skip_reason),
    ):
        if value:
            payload[key] = value
    if skip_verify:
        payload["skip_verification"] = True
    data = api_post("/api/payments/receive-crypto", json_data=payload)
    print_success(f"Crypto receipt recorded: {data['id']} ({data['currency']} {data['amount']})")
    print_success(f"SGD value {data.get('sgd_value')} @ {data.get('fx_rate_to_sgd')} ({data.get('fx_rate_source')})")
    if data.get("journal_entry_id"):
        print_success(f"Journal entry created: {data['journal_entry_id']}")
    verification = data.get("onchain_verification") or {}
    if verification.get("skipped"):
        typer.echo(f"WARNING: on-chain verification skipped: {verification.get('reason')}")
    elif verification:
        print_success(
            f"Verified on {verification.get('chain')}: {verification.get('amount_to_us')} "
            f"{verification.get('currency')}, {verification.get('confirmations')} confirmations "
            f"({verification.get('explorer_url')})"
        )
    print_success(f"Invoice {invoice} marked as paid")
    print_json(data)


@app.command()
def verify_tx(
    chain: str = typer.Option(..., "--chain", help="Network: base|ethereum"),
    tx_hash: str = typer.Option(..., "--tx-hash", help="Transaction hash"),
    currency: str = typer.Option("USDC", "--currency", help="USDC|USDT"),
    account: Optional[str] = typer.Option(None, "--account", help="Wallet account ID (uses its wallet_address)"),
    to: Optional[str] = typer.Option(None, "--to", help="Recipient address (instead of --account)"),
    amount: Optional[str] = typer.Option(None, "--amount", help="Expected amount", callback=decimal_amount),
) -> None:
    """Check a stablecoin transfer on-chain without recording anything."""
    if not account and not to:
        raise typer.BadParameter("pass --account or --to")
    payload: dict = {"chain": chain, "tx_hash": tx_hash, "currency": currency.upper()}
    if account:
        payload["wallet_account_id"] = account
    if to:
        payload["to_address"] = to
    if amount:
        payload["expected_amount"] = amount
    data = api_post("/api/payments/verify-onchain", json_data=payload)
    if data.get("verified"):
        checked = "" if amount else " (amount NOT checked: pass --amount)"
        print_success(
            f"VERIFIED{checked}: {data['amount_to_us']} {data['currency']} to {data['to_address']} on "
            f"{data['chain']}, {data['confirmations']} confirmations, from {', '.join(data.get('from_addresses') or [])}"
        )
    else:
        typer.echo("NOT VERIFIED: " + "; ".join(data.get("problems") or []))
    print_json(data)
    if not data.get("verified"):
        raise typer.Exit(code=1)


@app.command(name="list")
def list_payments(
    entity_type: Optional[str] = typer.Option(
        None, "--entity-type", help="Filter by entity type: invoice|payroll_run|expense"
    ),
) -> None:
    """List payments."""
    params: dict = {}
    if entity_type:
        params["entity_type"] = entity_type
    data = api_get("/api/payments", params=params)
    items = data if isinstance(data, list) else data.get("items", [])
    print_table(
        "Payments",
        ["ID", "Type", "Entity", "Amount", "Currency", "Date"],
        [
            [
                p.get("id", ""),
                p.get("payment_type", ""),
                f"{p.get('related_entity_type', '')}:{p.get('related_entity_id', '')}",
                p.get("amount", ""),
                p.get("currency", ""),
                p.get("payment_date", ""),
            ]
            for p in items
        ],
    )


@app.command()
def show(
    payment_id: str = typer.Argument(..., help="Payment ID"),
) -> None:
    """Show payment details."""
    data = api_get(f"/api/payments/{payment_id}")
    print_json(data)


@app.command()
def pipeline(
    entity: str = typer.Option(
        ..., "--entity", help="Entity reference, e.g. payroll_run:<id> or invoice:<id> or loan:<id>"
    ),
    type: str = typer.Option("bank_transfer", "--type", help="Payment type: bank_transfer|crypto|cash"),
) -> None:
    """Auto-create payment from entity with proof attachment and bank matching."""
    entity_type, _, entity_id = entity.partition(":")
    payload: dict = {
        "entity_type": entity_type,
        "entity_id": entity_id,
        "payment_type": type,
    }
    data = api_post("/api/payments/pipeline", json_data=payload)
    payment = data.get("payment", {})
    print_success(f"Payment created: {payment.get('id', '')}")
    print_success(f"Reference: {payment.get('reference_number', 'N/A')}")
    if payment.get("proof_file_id"):
        print_success("Proof document auto-attached")
    if data.get("bank_match_tx_id"):
        print_success(
            f"Bank transaction matched: {data['bank_match_tx_id']} "
            f"(confidence: {data.get('bank_match_confidence', 'N/A')})"
        )
    else:
        typer.echo("No bank transaction match found (will retry on next statement import)")
    print_json(data)


@app.command()
def attach(
    payment_id: str = typer.Argument(..., help="Payment ID"),
    filepath: Path = typer.Argument(..., help="File path to attach", exists=True),
) -> None:
    """Attach a proof/evidence file to a payment."""
    mime_type, _ = mimetypes.guess_type(str(filepath))
    if not mime_type:
        mime_type = "application/octet-stream"
    with open(filepath, "rb") as f:
        files = {"file": (filepath.name, f, mime_type)}
        data = api_post(f"/api/payments/{payment_id}/attach-proof", files=files)
    print_success(f"Proof attached to payment {payment_id}")
    print_json(data)


@app.command()
def allocate(
    payment_id: str = typer.Argument(..., help="Payment ID"),
    entity: str = typer.Option(..., "--entity", help="Entity reference, e.g. loan:<id>"),
    amount: str = typer.Option(..., "--amount", help="Amount to allocate", callback=decimal_amount),
    notes: Optional[str] = typer.Option(None, "--notes", help="Allocation notes"),
) -> None:
    """Allocate a payment to an entity (e.g. loan)."""
    entity_type, _, entity_id = entity.partition(":")
    allocation: dict = {"entity_type": entity_type, "entity_id": entity_id, "amount": amount}
    if notes:
        allocation["notes"] = notes
    data = api_post(f"/api/payments/{payment_id}/allocate", json_data={"allocations": [allocation]})
    print_success(f"Payment {payment_id} allocated")
    print_json(data)
