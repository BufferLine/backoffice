from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import BinaryIO, Optional


@dataclass
class ParsedTransaction:
    source_tx_id: str
    tx_date: date
    amount: Decimal
    currency: str
    counterparty: Optional[str] = None
    reference: Optional[str] = None
    description: Optional[str] = None
    raw_data: Optional[dict] = None


class StatementParser(ABC):
    @abstractmethod
    def parse(self, file_data: BinaryIO) -> list[ParsedTransaction]:
        ...
