"""Unit tests for Airwallex provider FX rate and payment link methods."""

from unittest.mock import AsyncMock, patch

import pytest

from app.integrations.base import FXRateProvider, PaymentLinkProvider
from app.integrations.capabilities import Capability
from app.integrations.providers.airwallex import AirwallexProvider


class TestAirwallexCapabilities:
    def test_has_fx_rate_capability(self):
        p = AirwallexProvider()
        assert Capability.FETCH_FX_RATE in p.capabilities

    def test_has_payment_link_capability(self):
        p = AirwallexProvider()
        assert Capability.CREATE_PAYMENT_LINK in p.capabilities

    def test_is_fx_rate_provider(self):
        p = AirwallexProvider()
        assert isinstance(p, FXRateProvider)

    def test_is_payment_link_provider(self):
        p = AirwallexProvider()
        assert isinstance(p, PaymentLinkProvider)

    def test_all_capabilities(self):
        p = AirwallexProvider()
        cap_values = {c.value for c in p.capabilities}
        assert "sync_transactions" in cap_values
        assert "sync_balance" in cap_values
        assert "receive_webhook" in cap_values
        assert "create_payment_link" in cap_values
        assert "initiate_transfer" in cap_values
        assert "fetch_fx_rate" in cap_values


class TestAirwallexFXRate:
    @pytest.mark.asyncio
    async def test_fetch_fx_rate(self):
        p = AirwallexProvider()
        mock_response = {
            "client_rate": "0.7432",
            "inverse_rate": "1.3455",
            "valid_to": "2026-03-21T12:00:00Z",
        }
        with patch.object(p, "_request", new_callable=AsyncMock, return_value=mock_response):
            result = await p.fetch_fx_rate(sell_currency="USD", buy_currency="SGD")

        assert result.sell_currency == "USD"
        assert result.buy_currency == "SGD"
        assert str(result.rate) == "0.7432"
        assert str(result.inverse_rate) == "1.3455"
        assert result.valid_until is not None

    @pytest.mark.asyncio
    async def test_fetch_fx_rate_no_inverse(self):
        p = AirwallexProvider()
        mock_response = {"rate": "1.35", "client_rate": "1.35"}
        with patch.object(p, "_request", new_callable=AsyncMock, return_value=mock_response):
            result = await p.fetch_fx_rate(sell_currency="SGD", buy_currency="USD")

        assert str(result.rate) == "1.35"
        assert result.inverse_rate is None
        assert result.valid_until is None

    @pytest.mark.asyncio
    async def test_fetch_fx_rate_passes_amounts(self):
        p = AirwallexProvider()
        mock_request = AsyncMock(return_value={"client_rate": "1.0"})
        with patch.object(p, "_request", mock_request):
            await p.fetch_fx_rate(
                sell_currency="USD",
                buy_currency="SGD",
                sell_amount="1000",
            )

        mock_request.assert_called_once_with(
            "GET",
            "/api/v1/fx/rates/current",
            params={"sell_currency": "USD", "buy_currency": "SGD", "sell_amount": "1000"},
        )


class TestAirwallexPaymentLink:
    @pytest.mark.asyncio
    async def test_create_payment_link(self):
        p = AirwallexProvider()
        mock_response = {
            "id": "pl_abc123",
            "url": "https://checkout.airwallex.com/pay/pl_abc123",
            "expires_at": "2026-04-01T00:00:00Z",
        }
        with patch.object(p, "_request", new_callable=AsyncMock, return_value=mock_response):
            result = await p.create_payment_link(
                amount="100.00",
                currency="USD",
                reference="INV-2026-0001",
            )

        assert result.url == "https://checkout.airwallex.com/pay/pl_abc123"
        assert result.provider_id == "pl_abc123"
        assert result.expires_at is not None

    @pytest.mark.asyncio
    async def test_create_payment_link_request_body(self):
        p = AirwallexProvider()
        mock_request = AsyncMock(return_value={"id": "pl_x", "url": "https://example.com"})
        with patch.object(p, "_request", mock_request):
            await p.create_payment_link(
                amount="50.00",
                currency="SGD",
                reference="INV-TEST",
                metadata={"invoice_id": "123"},
            )

        mock_request.assert_called_once_with(
            "POST",
            "/api/v1/pa/payment_links/create",
            json={
                "amount": 50.0,
                "currency": "SGD",
                "title": "INV-TEST",
                "reusable": False,
                "metadata": {"invoice_id": "123"},
            },
        )

    @pytest.mark.asyncio
    async def test_create_payment_link_no_expiry(self):
        p = AirwallexProvider()
        mock_response = {"id": "pl_y", "url": "https://example.com/pay"}
        with patch.object(p, "_request", new_callable=AsyncMock, return_value=mock_response):
            result = await p.create_payment_link(
                amount="10.00", currency="USD", reference="REF"
            )

        assert result.expires_at is None
