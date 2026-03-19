from abc import ABC, abstractmethod


class ExportFormatter(ABC):
    """Base class for export formatters."""

    @abstractmethod
    def format_invoices(self, invoices: list[dict]) -> bytes:
        ...

    @abstractmethod
    def format_payroll(self, payroll_runs: list[dict]) -> bytes:
        ...

    @abstractmethod
    def format_expenses(self, expenses: list[dict]) -> bytes:
        ...

    @abstractmethod
    def format_payments(self, payments: list[dict]) -> bytes:
        ...
