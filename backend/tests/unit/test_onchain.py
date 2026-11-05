"""Unit tests for on-chain stablecoin receipt verification (RPC mocked)."""

import json
from decimal import Decimal

import httpx
import pytest

from app.services import onchain
from app.services.onchain import (
    TRANSFER_TOPIC,
    OnchainRPCError,
    OnchainVerificationError,
    normalize_chain,
    transfers_to,
    verify_stablecoin_transfer,
)

_RealAsyncClient = httpx.AsyncClient

BASE_USDC = onchain.TOKENS[("base", "USDC")].address
OURS = "0x" + "ab" * 20
OTHER = "0x" + "cd" * 20
SENDER = "0x" + "ef" * 20
TX = "0x" + "12" * 32


def _topic(addr: str) -> str:
    return "0x" + "0" * 24 + addr[2:]


def _log(contract: str, to: str, raw: int, sender: str = SENDER) -> dict:
    return {
        "address": contract,
        "topics": [TRANSFER_TOPIC, _topic(sender), _topic(to)],
        "data": hex(raw),
    }


BLOCK_HASH = "0x" + "bb" * 32


def _rpc_handler(receipt, latest=1100, chain_id=8453, block_ts=1_762_300_000, safe=1050, canonical_hash=BLOCK_HASH):
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        method = body["method"]
        if method == "eth_getBlockByNumber":
            tag = body["params"][0]
            result = {"number": hex(safe)} if tag == "safe" else {"timestamp": hex(block_ts), "hash": canonical_hash}
        else:
            result = {
                "eth_chainId": hex(chain_id),
                "eth_getTransactionReceipt": receipt,
                "eth_blockNumber": hex(latest),
            }[method]
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": result})

    return handler


@pytest.fixture
def mock_rpc(monkeypatch):
    def install(handler):
        transport = httpx.MockTransport(handler)
        monkeypatch.setattr(onchain.httpx, "AsyncClient", lambda **kw: _RealAsyncClient(transport=transport, **kw))

    return install


def _receipt(logs, status="0x1", block=1000):
    return {"status": status, "blockNumber": hex(block), "blockHash": BLOCK_HASH, "transactionHash": TX, "logs": logs}


class TestParsing:
    def test_sums_only_canonical_contract_to_us(self):
        logs = [
            _log(BASE_USDC, OURS, 1_000_000),
            _log(BASE_USDC, OURS, 2_500_000, sender=OTHER),
            _log(BASE_USDC, OTHER, 9_000_000),  # to someone else
            _log("0x" + "99" * 20, OURS, 7_000_000),  # fake "USDC" contract
        ]
        raw, senders, out = transfers_to(logs, BASE_USDC, OURS)
        assert raw == 3_500_000
        assert senders == [SENDER, OTHER]
        assert out == 0

    def test_counts_outbound_from_us(self):
        logs = [_log(BASE_USDC, OURS, 5_000_000), _log(BASE_USDC, OTHER, 5_000_000, sender=OURS)]
        assert transfers_to(logs, BASE_USDC, OURS) == (5_000_000, [SENDER], 5_000_000)

    def test_ignores_non_transfer_events(self):
        approval = {"address": BASE_USDC, "topics": ["0x8c5be1e5" + "0" * 56, _topic(SENDER), _topic(OURS)], "data": "0x10"}
        assert transfers_to([approval], BASE_USDC, OURS) == (0, [], 0)

    def test_canonical_tx_hash(self):
        body = "AB" * 32
        assert onchain.canonical_tx_hash("0x" + body) == "0x" + body.lower()
        assert onchain.canonical_tx_hash(body) == "0x" + body.lower()  # missing 0x is the same tx
        assert onchain.canonical_tx_hash(" 5VfYmGv ") == "5VfYmGv"  # non-EVM kept case-sensitive

    def test_chain_aliases_and_unsupported(self):
        assert normalize_chain("ETH") == "ethereum"
        assert normalize_chain("Base") == "base"
        with pytest.raises(OnchainVerificationError, match="Unsupported chain"):
            normalize_chain("solana")

    def test_unsupported_token_on_chain(self):
        with pytest.raises(OnchainVerificationError, match="USDT on base is not supported"):
            onchain.token_for("base", "USDT")

    def test_bad_address_and_hash(self):
        with pytest.raises(OnchainVerificationError, match="Not an EVM address"):
            onchain.normalize_address("0x123")
        with pytest.raises(OnchainVerificationError, match="Not an EVM transaction hash"):
            onchain.normalize_tx_hash("abc")


class TestVerify:
    @pytest.mark.asyncio
    async def test_verified(self, mock_rpc):
        mock_rpc(_rpc_handler(_receipt([_log(BASE_USDC, OURS, 3_750_000_000)])))
        r = await verify_stablecoin_transfer("base", TX.upper().replace("0X", "0x"), "usdc", OURS.upper().replace("0X", "0x"), Decimal("3750"))
        assert r.verified, r.problems
        assert r.amount_to_us == Decimal("3750")
        assert r.confirmations == 101
        assert r.from_addresses == [SENDER]
        assert r.block_timestamp.year == 2025
        assert r.explorer_url == f"https://basescan.org/tx/{TX}"
        js = r.to_json()
        assert js["amount_to_us"] == "3750.000000" and js["verified"] is True

    @pytest.mark.asyncio
    async def test_amount_mismatch(self, mock_rpc):
        mock_rpc(_rpc_handler(_receipt([_log(BASE_USDC, OURS, 3_749_990_000)])))
        r = await verify_stablecoin_transfer("base", TX, "USDC", OURS, Decimal("3750"))
        assert not r.verified
        assert any("!= expected 3750" in p for p in r.problems)

    @pytest.mark.asyncio
    async def test_not_enough_confirmations(self, mock_rpc):
        mock_rpc(_rpc_handler(_receipt([_log(BASE_USDC, OURS, 1_000_000)]), latest=1005))
        r = await verify_stablecoin_transfer("base", TX, "USDC", OURS, Decimal("1"))
        assert not r.verified
        assert r.problems == ["only 6 confirmations; need 30"]

    @pytest.mark.asyncio
    async def test_reverted_transaction(self, mock_rpc):
        mock_rpc(_rpc_handler(_receipt([_log(BASE_USDC, OURS, 1_000_000)], status="0x0")))
        r = await verify_stablecoin_transfer("base", TX, "USDC", OURS, Decimal("1"))
        assert not r.verified
        assert "transaction failed (reverted)" in r.problems

    @pytest.mark.asyncio
    async def test_fake_token_is_not_accepted(self, mock_rpc):
        mock_rpc(_rpc_handler(_receipt([_log("0x" + "99" * 20, OURS, 1_000_000)])))
        r = await verify_stablecoin_transfer("base", TX, "USDC", OURS, Decimal("1"))
        assert not r.verified
        assert any("no USDC" in p for p in r.problems)

    @pytest.mark.asyncio
    async def test_missing_transaction(self, mock_rpc):
        mock_rpc(_rpc_handler(None))
        r = await verify_stablecoin_transfer("base", TX, "USDC", OURS, Decimal("1"))
        assert not r.verified
        assert r.problems == ["transaction not found (wrong chain, or not yet mined)"]

    @pytest.mark.asyncio
    async def test_rpc_on_wrong_chain_is_an_rpc_error(self, mock_rpc):
        mock_rpc(_rpc_handler(_receipt([]), chain_id=1))
        with pytest.raises(OnchainRPCError, match="expected base"):
            await verify_stablecoin_transfer("base", TX, "USDC", OURS)

    @pytest.mark.asyncio
    async def test_rpc_unreachable(self, mock_rpc):
        def handler(request):
            raise httpx.ConnectError("down", request=request)

        mock_rpc(handler)
        with pytest.raises(OnchainRPCError, match="eth_chainId failed"):
            await verify_stablecoin_transfer("base", TX, "USDC", OURS)

    @pytest.mark.asyncio
    async def test_not_yet_safe(self, mock_rpc):
        mock_rpc(_rpc_handler(_receipt([_log(BASE_USDC, OURS, 1_000_000)]), safe=990))
        r = await verify_stablecoin_transfer("base", TX, "USDC", OURS, Decimal("1"))
        assert not r.verified
        assert r.problems == ["block 1000 is not yet safe (safe head 990); retry later"]

    @pytest.mark.asyncio
    async def test_reorged_block_is_rejected(self, mock_rpc):
        mock_rpc(_rpc_handler(_receipt([_log(BASE_USDC, OURS, 1_000_000)]), canonical_hash="0x" + "cc" * 32))
        r = await verify_stablecoin_transfer("base", TX, "USDC", OURS, Decimal("1"))
        assert not r.verified
        assert any("not canonical" in p for p in r.problems)

    @pytest.mark.asyncio
    async def test_pay_in_and_pull_out_does_not_verify(self, mock_rpc):
        logs = [_log(BASE_USDC, OURS, 1_000_000), _log(BASE_USDC, OTHER, 1_000_000, sender=OURS)]
        mock_rpc(_rpc_handler(_receipt(logs)))
        r = await verify_stablecoin_transfer("base", TX, "USDC", OURS, Decimal("1"))
        assert not r.verified
        assert any("out of" in p for p in r.problems)

    @pytest.mark.asyncio
    async def test_rpc_errors_do_not_leak_url(self, mock_rpc, monkeypatch):
        from app.config import settings

        monkeypatch.setattr(settings, "ONCHAIN_RPC_BASE", "https://base.example-rpc.io/v2/SECRETKEY123")

        def handler(request):
            raise httpx.ConnectError("down", request=request)

        mock_rpc(handler)
        with pytest.raises(OnchainRPCError) as exc:
            await verify_stablecoin_transfer("base", TX, "USDC", OURS)
        assert "SECRETKEY123" not in str(exc.value)
        assert "base.example-rpc.io" in str(exc.value)

    @pytest.mark.asyncio
    async def test_malformed_rpc_response_is_rpc_error(self, mock_rpc):
        def handler(request):
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": None})

        mock_rpc(handler)
        with pytest.raises(OnchainRPCError, match="invalid chain id"):
            await verify_stablecoin_transfer("base", TX, "USDC", OURS)
