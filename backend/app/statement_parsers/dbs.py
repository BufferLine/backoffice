import hashlib
import re
import subprocess
import tempfile
from datetime import datetime
from decimal import Decimal
from typing import BinaryIO

from app.statement_parsers.base import ParsedTransaction, StatementParser

_DATE_RE = re.compile(r"^(\d{2}/\d{2}/\d{4})\s+(.+)")
_AMOUNT_RE = re.compile(r"([\d,]+\.\d{2})")
_CURRENCY_HEADER_RE = re.compile(r"CURRENCY:\s+(.+)")
_ACCT_RE = re.compile(r"Account No\.\s*([\d-]+)")
_NOISE_RE = re.compile(
    r"^(Page \d|SG\d{11}|PDS_|Transaction Details|Deposits$|My Account|"
    r"Date\s+Description|Withdrawal|Deposit\s*\(\+\)|^Balance$|^w$|"
    r"Messages For You|For Your Information|DEPOSIT INSURANCE)",
    re.IGNORECASE,
)

_CURRENCY_MAP = {
    "SINGAPORE DOLLAR": "SGD",
    "UNITED STATES DOLLAR": "USD",
    "BRITISH POUND": "GBP",
    "EURO": "EUR",
    "JAPANESE YEN": "JPY",
    "AUSTRALIAN DOLLAR": "AUD",
    "HONG KONG DOLLAR": "HKD",
}


class DBSParser(StatementParser):
    """Parser for DBS/POSB iBanking consolidated PDF statements.

    Requires ``pdftotext`` (poppler-utils) to be installed on the host.
    Handles multi-currency accounts and multi-page statements.
    """

    def parse(self, file_data: BinaryIO) -> list[ParsedTransaction]:
        text = self._extract_text(file_data)
        lines = text.split("\n")
        account_no = self._find_account_no(lines)
        return self._parse_lines(lines, account_no)

    # ------------------------------------------------------------------
    # PDF text extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_text(file_data: BinaryIO) -> str:
        with tempfile.NamedTemporaryFile(suffix=".pdf") as tmp:
            tmp.write(file_data.read())
            tmp.flush()
            result = subprocess.run(
                ["pdftotext", "-layout", tmp.name, "-"],
                capture_output=True,
                text=True,
                timeout=30,
            )
        if result.returncode != 0:
            raise ValueError(f"pdftotext failed: {result.stderr}")
        return result.stdout

    # ------------------------------------------------------------------
    # Line-level helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _find_account_no(lines: list[str]) -> str:
        for line in lines:
            m = _ACCT_RE.search(line)
            if m:
                return m.group(1)
        return "unknown"

    @staticmethod
    def _is_noise(line: str) -> bool:
        return bool(_NOISE_RE.match(line))

    @staticmethod
    def _extract_amounts(text: str) -> list[re.Match[str]]:
        return list(_AMOUNT_RE.finditer(text))

    # ------------------------------------------------------------------
    # Main parse loop
    # ------------------------------------------------------------------

    def _parse_lines(
        self, lines: list[str], account_no: str
    ) -> list[ParsedTransaction]:
        transactions: list[ParsedTransaction] = []
        currency = "SGD"
        prev_balance = Decimal(0)
        in_transactions = False

        for line in lines:
            stripped = line.strip()
            if not stripped or self._is_noise(stripped):
                continue

            # Currency section header
            m = _CURRENCY_HEADER_RE.match(stripped)
            if m:
                currency = _CURRENCY_MAP.get(m.group(1), m.group(1))
                prev_balance = Decimal(0)
                in_transactions = True
                continue

            # Balance brought forward (also appears at top of continuation pages)
            if "Balance Brought Forward" in stripped:
                m = re.search(r"[A-Z]{3}\s+([\d,]+\.\d{2})", stripped)
                if m:
                    prev_balance = Decimal(m.group(1).replace(",", ""))
                in_transactions = True
                continue

            # End of transaction section
            if "Balance Carried Forward" in stripped:
                in_transactions = False
                continue

            if not in_transactions:
                continue

            # Transaction line: starts with DD/MM/YYYY
            m = _DATE_RE.match(stripped)
            if m:
                tx_date = datetime.strptime(m.group(1), "%d/%m/%Y").date()
                rest = m.group(2)

                amounts = self._extract_amounts(rest)
                if len(amounts) < 2:
                    continue

                balance = Decimal(amounts[-1].group().replace(",", ""))
                signed_amount = balance - prev_balance

                # Description is everything before the first amount
                desc_end = amounts[-2].start()
                description = rest[:desc_end].strip()

                tx_id = _make_tx_id(
                    account_no, currency, tx_date, description,
                    amounts[-2].group(), balance,
                )

                transactions.append(
                    ParsedTransaction(
                        source_tx_id=tx_id,
                        tx_date=tx_date,
                        amount=signed_amount,
                        currency=currency,
                        counterparty=None,
                        reference=None,
                        description=description,
                        raw_data={
                            "account_no": account_no,
                            "withdrawal": str(-signed_amount) if signed_amount < 0 else None,
                            "deposit": str(signed_amount) if signed_amount > 0 else None,
                            "balance": str(balance),
                        },
                    )
                )
                prev_balance = balance
                continue

            # Continuation line: append to last transaction description
            if transactions and not re.match(r"Total Balance", stripped):
                last = transactions[-1]
                last_desc = last.description
                last.description = f"{last_desc} | {stripped}" if last_desc else stripped

                # First continuation line is often the counterparty
                if last.counterparty is None:
                    last.counterparty = stripped

                # Hex reference (e.g. FAST Collection ID)
                if last.reference is None and re.match(r"^[A-F0-9]{20,}$", stripped):
                    last.reference = stripped

        return transactions


def _make_tx_id(
    account_no: str,
    currency: str,
    tx_date: object,
    description: str,
    amount_str: str,
    balance: Decimal,
) -> str:
    raw = f"{account_no}|{currency}|{tx_date}|{description}|{amount_str}|{balance}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]
