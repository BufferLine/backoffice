from abc import ABC, abstractmethod
from typing import Any

from app.integrations.capabilities import (
    BalanceInfo,
    Capability,
    PaymentLinkResult,
    PaymentVerification,
    SyncedTransaction,
    TransferResult,
    WebhookEvent,
)


class IntegrationProvider(ABC):
    """Base class for all integration providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique provider identifier, e.g. 'airwallex'."""
        ...

    @property
    @abstractmethod
    def display_name(self) -> str:
        """Human-readable provider name."""
        ...

    @property
    def capabilities(self) -> list[Capability]:
        """Return list of capabilities this provider supports."""
        caps: list[Capability] = []
        if isinstance(self, TransactionSyncProvider):
            caps.append(Capability.SYNC_TRANSACTIONS)
        if isinstance(self, BalanceSyncProvider):
            caps.append(Capability.SYNC_BALANCE)
        if isinstance(self, WebhookProvider):
            caps.append(Capability.RECEIVE_WEBHOOK)
        if isinstance(self, PaymentLinkProvider):
            caps.append(Capability.CREATE_PAYMENT_LINK)
        if isinstance(self, TransferProvider):
            caps.append(Capability.INITIATE_TRANSFER)
        if isinstance(self, PaymentVerificationProvider):
            caps.append(Capability.VERIFY_PAYMENT)
        if isinstance(self, AccountingPushProvider):
            caps.append(Capability.PUSH_INVOICE)
        return caps

    def has_capability(self, capability: Capability) -> bool:
        return capability in self.capabilities

    async def test_connection(self) -> dict[str, Any]:
        """Test the provider connection. Returns status dict."""
        return {"status": "ok", "provider": self.name}


class TransactionSyncProvider(ABC):
    """Mixin for providers that support transaction syncing."""

    @abstractmethod
    async def sync_transactions(
        self,
        since: str | None = None,
        cursor: str | None = None,
    ) -> tuple[list[SyncedTransaction], str | None]:
        """
        Fetch transactions from the provider.

        Returns (transactions, next_cursor). next_cursor is None when done.
        """
        ...


class BalanceSyncProvider(ABC):
    """Mixin for providers that support balance syncing."""

    @abstractmethod
    async def sync_balances(self) -> list[BalanceInfo]:
        """Fetch current balances from the provider."""
        ...


class WebhookProvider(ABC):
    """Mixin for providers that send webhooks."""

    @abstractmethod
    def verify_webhook(self, body: bytes, headers: dict[str, str]) -> None:
        """
        Verify webhook signature. Raises WebhookSignatureError on failure.
        """
        ...

    @abstractmethod
    def parse_webhook(self, body: bytes, headers: dict[str, str]) -> WebhookEvent:
        """Parse raw webhook body into a WebhookEvent."""
        ...

    @abstractmethod
    async def handle_event(self, event: WebhookEvent) -> dict[str, Any]:
        """Process a webhook event. Returns result dict."""
        ...


class PaymentLinkProvider(ABC):
    """Mixin for providers that support payment link creation."""

    @abstractmethod
    async def create_payment_link(
        self,
        amount: str,
        currency: str,
        reference: str,
        metadata: dict[str, Any] | None = None,
    ) -> PaymentLinkResult:
        ...


class TransferProvider(ABC):
    """Mixin for providers that support initiating transfers."""

    @abstractmethod
    async def initiate_transfer(
        self,
        amount: str,
        currency: str,
        destination: dict[str, Any],
        reference: str | None = None,
    ) -> TransferResult:
        ...


class PaymentVerificationProvider(ABC):
    """Mixin for providers that support verifying on-chain payments."""

    @abstractmethod
    async def verify_payment(
        self,
        tx_hash: str,
        expected_amount: str | None = None,
        expected_currency: str | None = None,
    ) -> PaymentVerification:
        ...


class AccountingPushProvider(ABC):
    """Mixin for providers that support pushing invoices/expenses."""

    @abstractmethod
    async def push_invoice(self, invoice_data: dict[str, Any]) -> dict[str, Any]:
        ...

    @abstractmethod
    async def push_expense(self, expense_data: dict[str, Any]) -> dict[str, Any]:
        ...
