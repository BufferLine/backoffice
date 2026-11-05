"""On-chain verification of stablecoin receipts via EVM JSON-RPC (no API key needed).

A receipt is verified when the transaction:
1. exists and succeeded (``status == 0x1``),
2. contains ERC-20 ``Transfer`` logs emitted by the canonical token contract for the
   currency on that chain (a token merely *named* USDC elsewhere does not count),
3. whose transfers *to our wallet address* sum exactly to the expected amount, and
4. has at least the configured number of confirmations, sits at or below the chain's
   ``safe`` block (L1-included on Base, justified on Ethereum), and its block is still
   canonical (receipt block hash == canonical block hash at that height).

Transfers *out of* our wallet in the same transaction are netted off, so a tx that
pays us and pulls the funds back out does not verify.

Only the contracts listed in ``TOKENS`` are accepted. They were checked on-chain
(``symbol()``/``decimals()``) when added.
"""

import asyncio
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Optional
from urllib.parse import urlsplit

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# keccak256("Transfer(address,address,uint256)")
TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"


@dataclass(frozen=True)
class Token:
    address: str  # lower-case
    decimals: int


@dataclass(frozen=True)
class Chain:
    name: str
    chain_id: int
    explorer_tx_url: str


CHAINS: dict[str, Chain] = {
    "ethereum": Chain("ethereum", 1, "https://etherscan.io/tx/"),
    "base": Chain("base", 8453, "https://basescan.org/tx/"),
}

TOKENS: dict[tuple[str, str], Token] = {
    ("ethereum", "USDC"): Token("0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48", 6),
    ("ethereum", "USDT"): Token("0xdac17f958d2ee523a2206206994597c13d831ec7", 6),
    ("base", "USDC"): Token("0x833589fcd6edb6e08f4c7c32d4f71b54bda02913", 6),
}

CHAIN_ALIASES = {"eth": "ethereum", "mainnet": "ethereum", "ethereum-mainnet": "ethereum", "base-mainnet": "base"}


class OnchainVerificationError(ValueError):
    """Bad input, or the transaction does not match the expected receipt."""

    def __init__(self, message: str, result: Optional["VerificationResult"] = None):
        super().__init__(message)
        self.result = result


class OnchainRPCError(OnchainVerificationError):
    """The chain could not be queried (RPC unreachable or returned an error)."""


@dataclass
class VerificationResult:
    verified: bool
    chain: str
    tx_hash: str
    currency: str
    token_contract: str
    to_address: str
    amount_to_us: Decimal = Decimal("0")
    expected_amount: Optional[Decimal] = None
    confirmations: int = 0
    min_confirmations: int = 0
    block_number: Optional[int] = None
    block_timestamp: Optional[datetime] = None
    from_addresses: list[str] = field(default_factory=list)
    explorer_url: str = ""
    problems: list[str] = field(default_factory=list)
    checked_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_json(self) -> dict[str, Any]:
        data = asdict(self)
        for key in ("amount_to_us", "expected_amount"):
            data[key] = str(data[key]) if data[key] is not None else None
        for key in ("block_timestamp", "checked_at"):
            data[key] = data[key].isoformat() if data[key] is not None else None
        return data


def normalize_chain(chain: Optional[str]) -> str:
    if not chain:
        raise OnchainVerificationError(f"chain is required; supported: {sorted(CHAINS)}")
    name = CHAIN_ALIASES.get(chain.strip().lower(), chain.strip().lower())
    if name not in CHAINS:
        raise OnchainVerificationError(f"Unsupported chain {chain!r}; supported: {sorted(CHAINS)}")
    return name


def token_for(chain: str, currency: str) -> Token:
    token = TOKENS.get((chain, currency.upper()))
    if token is None:
        supported = sorted(c for ch, c in TOKENS if ch == chain)
        raise OnchainVerificationError(f"{currency.upper()} on {chain} is not supported; supported: {supported}")
    return token


def normalize_address(address: Optional[str]) -> str:
    addr = (address or "").strip().lower()
    if not (addr.startswith("0x") and len(addr) == 42 and all(c in "0123456789abcdef" for c in addr[2:])):
        raise OnchainVerificationError(f"Not an EVM address: {address!r}")
    return addr


def normalize_tx_hash(tx_hash: Optional[str]) -> str:
    h = (tx_hash or "").strip().lower()
    if not (h.startswith("0x") and len(h) == 66 and all(c in "0123456789abcdef" for c in h[2:])):
        raise OnchainVerificationError(f"Not an EVM transaction hash: {tx_hash!r}")
    return h


_TIMEOUT = httpx.Timeout(10.0, connect=5.0)
_OVERALL_TIMEOUT_S = 30


def _redact(url: str) -> str:
    """Host only: provider URLs often embed an API key in the path or query."""
    return urlsplit(url).netloc or "rpc"


def canonical_tx_hash(tx_hash: str) -> str:
    """Canonical form for duplicate detection: EVM hashes lower-case with 0x; others as given."""
    h = tx_hash.strip()
    body = h[2:] if h.lower().startswith("0x") else h
    if len(body) == 64 and all(c in "0123456789abcdefABCDEF" for c in body):
        return "0x" + body.lower()
    return h


def rpc_url(chain: str) -> str:
    return {"ethereum": settings.ONCHAIN_RPC_ETHEREUM, "base": settings.ONCHAIN_RPC_BASE}[chain]


def min_confirmations(chain: str) -> int:
    return {"ethereum": settings.ONCHAIN_MIN_CONFIRMATIONS_ETHEREUM, "base": settings.ONCHAIN_MIN_CONFIRMATIONS_BASE}[chain]


async def _rpc(client: httpx.AsyncClient, url: str, method: str, params: list) -> Any:
    try:
        resp = await client.post(url, json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
        resp.raise_for_status()
        body = resp.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise OnchainRPCError(f"RPC {method} failed at {_redact(url)}: {type(exc).__name__}") from exc
    if not isinstance(body, dict):
        raise OnchainRPCError(f"RPC {method} at {_redact(url)} returned a non-object response")
    if body.get("error"):
        raise OnchainRPCError(f"RPC {method} error at {_redact(url)}: {body['error']}")
    return body.get("result")


def _hex_int(value: Any, what: str) -> int:
    try:
        return int(value, 16)
    except (TypeError, ValueError) as exc:
        raise OnchainRPCError(f"RPC returned an invalid {what}: {value!r}") from exc


def transfers_to(
    logs: list[dict], token_contract: str, to_address: str
) -> tuple[int, list[str], int]:
    """Token flows for ``to_address`` in one transaction's logs.

    Returns (raw units received, senders, raw units sent out of ``to_address``),
    counting only ``Transfer`` logs emitted by ``token_contract``.
    """
    received = 0
    sent_out = 0
    senders: list[str] = []
    for log in logs or []:
        topics = [str(t).lower() for t in log.get("topics") or []]
        if (log.get("address") or "").lower() != token_contract:
            continue
        if len(topics) != 3 or topics[0] != TRANSFER_TOPIC:
            continue
        data = log.get("data") or "0x"
        value = int(data, 16) if data not in ("0x", "") else 0
        sender = "0x" + topics[1][-40:]
        recipient = "0x" + topics[2][-40:]
        if recipient == to_address:
            received += value
            if sender not in senders:
                senders.append(sender)
        if sender == to_address:
            sent_out += value
    return received, senders, sent_out


async def verify_stablecoin_transfer(
    chain: str,
    tx_hash: str,
    currency: str,
    to_address: str,
    expected_amount: Optional[Decimal] = None,
) -> VerificationResult:
    """Check a stablecoin transfer on-chain. Never raises for a mismatch: see ``result.problems``.

    Raises ``OnchainVerificationError`` only for bad input or an unreachable RPC.
    """
    chain = normalize_chain(chain)
    tx_hash = normalize_tx_hash(tx_hash)
    to_address = normalize_address(to_address)
    token = token_for(chain, currency)
    url = rpc_url(chain)
    needed = min_confirmations(chain)

    result = VerificationResult(
        verified=False,
        chain=chain,
        tx_hash=tx_hash,
        currency=currency.upper(),
        token_contract=token.address,
        to_address=to_address,
        expected_amount=expected_amount,
        min_confirmations=needed,
        explorer_url=CHAINS[chain].explorer_tx_url + tx_hash,
    )

    try:
        async with asyncio.timeout(_OVERALL_TIMEOUT_S):
            receipt, safe_number, latest, block = await _fetch(url, chain, tx_hash)
    except TimeoutError as exc:
        raise OnchainRPCError(f"RPC at {_redact(url)} timed out after {_OVERALL_TIMEOUT_S}s") from exc

    if receipt is None:
        result.problems.append("transaction not found (wrong chain, or not yet mined)")
        return result

    result.block_number = _hex_int(receipt.get("blockNumber"), "block number")
    result.confirmations = max(0, latest - result.block_number + 1)
    if block and block.get("timestamp"):
        result.block_timestamp = datetime.fromtimestamp(_hex_int(block["timestamp"], "timestamp"), tz=timezone.utc)

    if (receipt.get("transactionHash") or "").lower() != tx_hash:
        result.problems.append("RPC returned a receipt for a different transaction")
    if not block or (block.get("hash") or "").lower() != (receipt.get("blockHash") or "").lower():
        result.problems.append("receipt block is not canonical (possible reorg); retry later")
    if receipt.get("status") != "0x1":
        result.problems.append("transaction failed (reverted)")

    raw, senders, sent_out = transfers_to(receipt.get("logs") or [], token.address, to_address)
    result.amount_to_us = Decimal(raw).scaleb(-token.decimals)
    result.from_addresses = senders
    if sent_out:
        result.problems.append(
            f"transaction also moves {Decimal(sent_out).scaleb(-token.decimals)} {result.currency} out of {to_address}"
        )
    if raw == 0:
        result.problems.append(f"no {result.currency} ({token.address}) transfer to {to_address} in this transaction")
    elif expected_amount is not None and result.amount_to_us != expected_amount:
        result.problems.append(
            f"amount received {result.amount_to_us} {result.currency} != expected {expected_amount}"
        )
    if result.confirmations < needed:
        result.problems.append(f"only {result.confirmations} confirmations; need {needed}")
    if safe_number is not None and result.block_number > safe_number:
        result.problems.append(f"block {result.block_number} is not yet safe (safe head {safe_number}); retry later")

    result.verified = not result.problems
    return result


async def _fetch(url: str, chain: str, tx_hash: str):
    """Receipt, safe block number, latest block number, canonical block at the receipt's height."""
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        chain_id = _hex_int(await _rpc(client, url, "eth_chainId", []), "chain id")
        if chain_id != CHAINS[chain].chain_id:
            raise OnchainRPCError(
                f"RPC at {_redact(url)} is chain {chain_id}, expected {chain} ({CHAINS[chain].chain_id})"
            )
        receipt = await _rpc(client, url, "eth_getTransactionReceipt", [tx_hash])
        if receipt is None:
            return None, None, 0, None
        if not isinstance(receipt, dict):
            raise OnchainRPCError("RPC returned a malformed receipt")
        latest = _hex_int(await _rpc(client, url, "eth_blockNumber", []), "block number")
        safe = await _rpc(client, url, "eth_getBlockByNumber", ["safe", False])
        safe_number = _hex_int(safe["number"], "safe block number") if isinstance(safe, dict) and safe.get("number") else None
        if safe_number is None:
            raise OnchainRPCError(f"RPC at {_redact(url)} does not report a 'safe' block; cannot check finality")
        block = await _rpc(client, url, "eth_getBlockByNumber", [receipt.get("blockNumber"), False])
        return receipt, safe_number, latest, block if isinstance(block, dict) else None
