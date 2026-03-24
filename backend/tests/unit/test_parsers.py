"""Unit tests for statement parsers (AirwallexParser, GenericParser, get_parser)."""

from datetime import date
from decimal import Decimal
from io import BytesIO

import pytest

from app.statement_parsers import get_parser
from app.statement_parsers.airwallex import AirwallexParser
from app.statement_parsers.base import ParsedTransaction, StatementParser
from app.statement_parsers.generic import GenericParser


# ---------------------------------------------------------------------------
# ParsedTransaction dataclass
# ---------------------------------------------------------------------------


class TestParsedTransaction:
    def test_required_fields(self):
        tx = ParsedTransaction(
            source_tx_id="TX001",
            tx_date=date(2026, 1, 15),
            amount=Decimal("100.00"),
            currency="SGD",
        )
        assert tx.source_tx_id == "TX001"
        assert tx.tx_date == date(2026, 1, 15)
        assert tx.amount == Decimal("100.00")
        assert tx.currency == "SGD"

    def test_optional_fields_default_to_none(self):
        tx = ParsedTransaction(
            source_tx_id="TX002",
            tx_date=date(2026, 1, 15),
            amount=Decimal("50.00"),
            currency="USD",
        )
        assert tx.counterparty is None
        assert tx.reference is None
        assert tx.description is None
        assert tx.raw_data is None

    def test_all_fields(self):
        tx = ParsedTransaction(
            source_tx_id="TX003",
            tx_date=date(2026, 3, 1),
            amount=Decimal("-200.50"),
            currency="SGD",
            counterparty="Acme Corp",
            reference="REF-99",
            description="Vendor payment",
            raw_data={"raw": "value"},
        )
        assert tx.counterparty == "Acme Corp"
        assert tx.reference == "REF-99"
        assert tx.description == "Vendor payment"
        assert tx.raw_data == {"raw": "value"}

    def test_negative_amount(self):
        tx = ParsedTransaction(
            source_tx_id="TX004",
            tx_date=date(2026, 1, 1),
            amount=Decimal("-999.99"),
            currency="SGD",
        )
        assert tx.amount == Decimal("-999.99")


# ---------------------------------------------------------------------------
# get_parser registry
# ---------------------------------------------------------------------------


class TestGetParser:
    def test_get_airwallex_parser(self):
        parser = get_parser("airwallex")
        assert isinstance(parser, AirwallexParser)

    def test_get_generic_parser(self):
        parser = get_parser("generic")
        assert isinstance(parser, GenericParser)

    def test_all_parsers_are_statement_parsers(self):
        assert isinstance(get_parser("airwallex"), StatementParser)
        assert isinstance(get_parser("generic"), StatementParser)

    def test_unknown_source_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown statement source"):
            get_parser("unknown")

    def test_unknown_source_names_available_parsers(self):
        with pytest.raises(ValueError, match="airwallex"):
            get_parser("does_not_exist")

    def test_case_sensitive_lookup(self):
        with pytest.raises(ValueError):
            get_parser("Airwallex")

    def test_empty_string_raises_value_error(self):
        with pytest.raises(ValueError):
            get_parser("")


# ---------------------------------------------------------------------------
# AirwallexParser
# ---------------------------------------------------------------------------


class TestAirwallexParser:
    def _parser(self) -> AirwallexParser:
        return AirwallexParser()

    def _csv(self, *rows: str) -> BytesIO:
        return BytesIO("\n".join(rows).encode("utf-8"))

    # --- valid data ---------------------------------------------------------

    def test_parse_single_row(self):
        data = self._csv(
            "Transaction ID,Date,Amount,Currency,Counterparty,Reference,Status",
            "TX-001,2026-01-15,100.00,SGD,Acme Corp,INV-001,COMPLETED",
        )
        result = self._parser().parse(data)
        assert len(result) == 1
        tx = result[0]
        assert tx.source_tx_id == "TX-001"
        assert tx.tx_date == date(2026, 1, 15)
        assert tx.amount == Decimal("100.00")
        assert tx.currency == "SGD"
        assert tx.counterparty == "Acme Corp"
        assert tx.reference == "INV-001"

    def test_parse_multiple_rows(self):
        data = self._csv(
            "Transaction ID,Date,Amount,Currency",
            "TX-001,2026-01-15,100.00,SGD",
            "TX-002,2026-01-16,200.50,USD",
            "TX-003,2026-01-17,-50.00,SGD",
        )
        result = self._parser().parse(data)
        assert len(result) == 3
        assert result[0].source_tx_id == "TX-001"
        assert result[1].amount == Decimal("200.50")
        assert result[2].amount == Decimal("-50.00")

    def test_currency_uppercased(self):
        data = self._csv(
            "Transaction ID,Date,Amount,Currency",
            "TX-001,2026-01-15,10.00,sgd",
        )
        result = self._parser().parse(data)
        assert result[0].currency == "SGD"

    def test_amount_with_commas(self):
        data = self._csv(
            "Transaction ID,Date,Amount,Currency",
            'TX-001,2026-01-15,"1,500.00",SGD',
        )
        result = self._parser().parse(data)
        assert result[0].amount == Decimal("1500.00")

    def test_raw_data_populated(self):
        data = self._csv(
            "Transaction ID,Date,Amount,Currency",
            "TX-001,2026-01-15,10.00,SGD",
        )
        result = self._parser().parse(data)
        assert result[0].raw_data is not None
        assert "Transaction ID" in result[0].raw_data

    def test_skips_blank_rows(self):
        data = self._csv(
            "Transaction ID,Date,Amount,Currency",
            "TX-001,2026-01-15,100.00,SGD",
            "   ,  ,  ,  ",
            "TX-002,2026-01-16,200.00,SGD",
        )
        result = self._parser().parse(data)
        assert len(result) == 2

    # --- date format variants -----------------------------------------------

    def test_date_iso_format(self):
        data = self._csv(
            "Transaction ID,Date,Amount,Currency",
            "TX-001,2026-03-24,50.00,SGD",
        )
        result = self._parser().parse(data)
        assert result[0].tx_date == date(2026, 3, 24)

    def test_date_iso_datetime_format(self):
        data = self._csv(
            "Transaction ID,Date,Amount,Currency",
            "TX-001,2026-03-24T14:30:00,50.00,SGD",
        )
        result = self._parser().parse(data)
        assert result[0].tx_date == date(2026, 3, 24)

    def test_date_iso_datetime_z_format(self):
        data = self._csv(
            "Transaction ID,Date,Amount,Currency",
            "TX-001,2026-03-24T14:30:00Z,50.00,SGD",
        )
        result = self._parser().parse(data)
        assert result[0].tx_date == date(2026, 3, 24)

    def test_date_dmy_format(self):
        data = self._csv(
            "Transaction ID,Date,Amount,Currency",
            "TX-001,24/03/2026,50.00,SGD",
        )
        result = self._parser().parse(data)
        assert result[0].tx_date == date(2026, 3, 24)

    # --- header variants (case-insensitive) ---------------------------------

    def test_header_case_insensitive(self):
        data = self._csv(
            "TRANSACTION ID,DATE,AMOUNT,CURRENCY",
            "TX-001,2026-01-15,75.00,SGD",
        )
        result = self._parser().parse(data)
        assert len(result) == 1
        assert result[0].source_tx_id == "TX-001"

    def test_alternative_header_names(self):
        # transaction_id instead of transaction id; transaction currency, etc.
        data = self._csv(
            "transaction_id,transaction date,transaction amount,transaction currency",
            "TX-ALT,2026-02-01,300.00,usd",
        )
        result = self._parser().parse(data)
        assert len(result) == 1
        assert result[0].source_tx_id == "TX-ALT"
        assert result[0].currency == "USD"

    def test_extra_columns_ignored(self):
        data = self._csv(
            "Transaction ID,Date,Amount,Currency,Extra1,Extra2",
            "TX-001,2026-01-15,10.00,SGD,foo,bar",
        )
        result = self._parser().parse(data)
        assert len(result) == 1

    def test_optional_fields_absent_become_none(self):
        # Only required columns — no counterparty, reference, description
        data = self._csv(
            "Transaction ID,Date,Amount,Currency",
            "TX-001,2026-01-15,10.00,SGD",
        )
        result = self._parser().parse(data)
        assert result[0].counterparty is None
        assert result[0].reference is None
        assert result[0].description is None

    def test_empty_optional_fields_become_none(self):
        data = self._csv(
            "Transaction ID,Date,Amount,Currency,Counterparty,Reference",
            "TX-001,2026-01-15,10.00,SGD,,",
        )
        result = self._parser().parse(data)
        assert result[0].counterparty is None
        assert result[0].reference is None

    # --- error cases --------------------------------------------------------

    def test_headers_only_returns_empty_list(self):
        data = self._csv(
            "Transaction ID,Date,Amount,Currency,Counterparty,Reference,Status",
        )
        result = self._parser().parse(data)
        assert result == []

    def test_missing_required_column_raises_value_error(self):
        # Missing Transaction ID
        data = self._csv(
            "Date,Amount,Currency",
            "2026-01-15,100.00,SGD",
        )
        with pytest.raises(ValueError, match="missing required columns"):
            self._parser().parse(data)

    def test_missing_amount_column_raises_value_error(self):
        data = self._csv(
            "Transaction ID,Date,Currency",
            "TX-001,2026-01-15,SGD",
        )
        with pytest.raises(ValueError, match="missing required columns"):
            self._parser().parse(data)

    def test_bom_handled(self):
        # UTF-8 BOM prefix
        csv_bytes = b"\xef\xbb\xbfTransaction ID,Date,Amount,Currency\nTX-001,2026-01-15,10.00,SGD\n"
        result = self._parser().parse(BytesIO(csv_bytes))
        assert len(result) == 1
        assert result[0].source_tx_id == "TX-001"

    def test_empty_file_raises_stop_iteration(self):
        # Completely empty file — no header row at all
        with pytest.raises(StopIteration):
            self._parser().parse(BytesIO(b""))

    def test_incomplete_row_skipped(self):
        """Rows with fewer columns than required should be silently skipped."""
        csv_data = (
            b"Transaction ID,Date,Amount,Currency,Counterparty,Reference\n"
            b"TX-001,2026-01-15,100.00,SGD,Acme,REF-001\n"
            b"TX-002,2026-01-16\n"  # incomplete — missing amount and currency
            b"TX-003,2026-01-17,200.00,USD,Beta,REF-003\n"
        )
        result = self._parser().parse(BytesIO(csv_data))
        assert len(result) == 2
        assert result[0].source_tx_id == "TX-001"
        assert result[1].source_tx_id == "TX-003"

    def test_row_with_unparseable_date_skipped(self):
        csv_data = (
            b"Transaction ID,Date,Amount,Currency\n"
            b"TX-001,not-a-date,100.00,SGD\n"
            b"TX-002,2026-03-01,50.00,USD\n"
        )
        result = self._parser().parse(BytesIO(csv_data))
        assert len(result) == 1
        assert result[0].source_tx_id == "TX-002"

    def test_row_with_unparseable_amount_skipped(self):
        csv_data = (
            b"Transaction ID,Date,Amount,Currency\n"
            b"TX-001,2026-01-15,abc,SGD\n"
            b"TX-002,2026-01-16,75.00,USD\n"
        )
        result = self._parser().parse(BytesIO(csv_data))
        assert len(result) == 1
        assert result[0].source_tx_id == "TX-002"


# ---------------------------------------------------------------------------
# GenericParser
# ---------------------------------------------------------------------------


class TestGenericParser:
    def _parser(self, column_mapping=None) -> GenericParser:
        return GenericParser(column_mapping=column_mapping)

    def _csv(self, *rows: str) -> BytesIO:
        return BytesIO("\n".join(rows).encode("utf-8"))

    # --- valid data ---------------------------------------------------------

    def test_parse_single_row_default_mapping(self):
        data = self._csv(
            "tx_id,date,amount,currency,counterparty,reference,description",
            "TX-001,2026-01-15,100.00,SGD,Vendor A,REF-001,Payment",
        )
        result = self._parser().parse(data)
        assert len(result) == 1
        tx = result[0]
        assert tx.source_tx_id == "TX-001"
        assert tx.tx_date == date(2026, 1, 15)
        assert tx.amount == Decimal("100.00")
        assert tx.currency == "SGD"
        assert tx.counterparty == "Vendor A"
        assert tx.reference == "REF-001"
        assert tx.description == "Payment"

    def test_parse_multiple_rows(self):
        data = self._csv(
            "id,date,amount,currency",
            "TX-001,2026-01-15,100.00,SGD",
            "TX-002,2026-01-16,200.00,USD",
            "TX-003,2026-01-17,300.00,SGD",
        )
        mapping = {"tx_id": 0, "date": 1, "amount": 2, "currency": 3}
        result = self._parser(column_mapping=mapping).parse(data)
        assert len(result) == 3

    def test_currency_uppercased(self):
        data = self._csv(
            "header",
            "TX-001,2026-01-15,10.00,sgd",
        )
        mapping = {"tx_id": 0, "date": 1, "amount": 2, "currency": 3}
        result = self._parser(column_mapping=mapping).parse(data)
        assert result[0].currency == "SGD"

    def test_amount_with_commas(self):
        data = self._csv(
            "header",
            'TX-001,2026-01-15,"1,500.00",SGD',
        )
        mapping = {"tx_id": 0, "date": 1, "amount": 2, "currency": 3}
        result = self._parser(column_mapping=mapping).parse(data)
        assert result[0].amount == Decimal("1500.00")

    def test_custom_column_mapping(self):
        # Columns reordered: currency first, then date, amount, id
        data = self._csv(
            "currency,date,amount,id",
            "SGD,2026-02-20,500.00,TX-CUSTOM",
        )
        mapping = {"tx_id": 3, "date": 1, "amount": 2, "currency": 0}
        result = self._parser(column_mapping=mapping).parse(data)
        assert len(result) == 1
        assert result[0].source_tx_id == "TX-CUSTOM"
        assert result[0].currency == "SGD"
        assert result[0].amount == Decimal("500.00")

    def test_raw_data_uses_column_indices(self):
        data = self._csv(
            "header",
            "TX-001,2026-01-15,10.00,SGD",
        )
        mapping = {"tx_id": 0, "date": 1, "amount": 2, "currency": 3}
        result = self._parser(column_mapping=mapping).parse(data)
        assert result[0].raw_data == {"0": "TX-001", "1": "2026-01-15", "2": "10.00", "3": "SGD"}

    def test_skips_blank_rows(self):
        data = self._csv(
            "header",
            "TX-001,2026-01-15,100.00,SGD",
            "  ,  ,  ,  ",
            "TX-002,2026-01-16,200.00,SGD",
        )
        mapping = {"tx_id": 0, "date": 1, "amount": 2, "currency": 3}
        result = self._parser(column_mapping=mapping).parse(data)
        assert len(result) == 2

    def test_skips_incomplete_rows(self):
        # Row missing currency → skipped
        data = self._csv(
            "header",
            "TX-001,2026-01-15,100.00,SGD",
            "TX-002,2026-01-16,200.00",
        )
        mapping = {"tx_id": 0, "date": 1, "amount": 2, "currency": 3}
        result = self._parser(column_mapping=mapping).parse(data)
        assert len(result) == 1
        assert result[0].source_tx_id == "TX-001"

    # --- date format variants -----------------------------------------------

    def test_date_iso_format(self):
        data = self._csv(
            "header",
            "TX-001,2026-03-24,50.00,SGD",
        )
        mapping = {"tx_id": 0, "date": 1, "amount": 2, "currency": 3}
        result = self._parser(column_mapping=mapping).parse(data)
        assert result[0].tx_date == date(2026, 3, 24)

    def test_date_dmy_slash_format(self):
        data = self._csv(
            "header",
            "TX-001,24/03/2026,50.00,SGD",
        )
        mapping = {"tx_id": 0, "date": 1, "amount": 2, "currency": 3}
        result = self._parser(column_mapping=mapping).parse(data)
        assert result[0].tx_date == date(2026, 3, 24)

    def test_date_dmy_dash_format(self):
        data = self._csv(
            "header",
            "TX-001,24-03-2026,50.00,SGD",
        )
        mapping = {"tx_id": 0, "date": 1, "amount": 2, "currency": 3}
        result = self._parser(column_mapping=mapping).parse(data)
        assert result[0].tx_date == date(2026, 3, 24)

    def test_date_compact_format(self):
        data = self._csv(
            "header",
            "TX-001,20260324,50.00,SGD",
        )
        mapping = {"tx_id": 0, "date": 1, "amount": 2, "currency": 3}
        result = self._parser(column_mapping=mapping).parse(data)
        assert result[0].tx_date == date(2026, 3, 24)

    def test_date_iso_datetime_format(self):
        data = self._csv(
            "header",
            "TX-001,2026-03-24T09:00:00,50.00,SGD",
        )
        mapping = {"tx_id": 0, "date": 1, "amount": 2, "currency": 3}
        result = self._parser(column_mapping=mapping).parse(data)
        assert result[0].tx_date == date(2026, 3, 24)

    # --- header skip heuristic ----------------------------------------------

    def test_header_row_is_auto_skipped(self):
        # Default mapping: col 0 = tx_id; header first cell "tx_id" is not a
        # date or number, so it should be skipped automatically.
        data = self._csv(
            "tx_id,date,amount,currency",
            "TX-001,2026-01-15,100.00,SGD",
        )
        result = self._parser().parse(data)
        assert len(result) == 1
        assert result[0].source_tx_id == "TX-001"

    def test_no_header_row_when_first_cell_is_id_like(self):
        # First cell that can be parsed as decimal is treated as data row
        data = self._csv(
            "100,2026-01-15,100.00,SGD",
        )
        mapping = {"tx_id": 0, "date": 1, "amount": 2, "currency": 3}
        result = self._parser(column_mapping=mapping).parse(data)
        assert len(result) == 1
        assert result[0].source_tx_id == "100"

    # --- edge cases ---------------------------------------------------------

    def test_headers_only_returns_empty_list(self):
        data = self._csv(
            "tx_id,date,amount,currency,counterparty,reference,description",
        )
        result = self._parser().parse(data)
        assert result == []

    def test_empty_file_returns_empty_list(self):
        result = self._parser().parse(BytesIO(b""))
        assert result == []

    def test_bom_handled(self):
        csv_bytes = b"\xef\xbb\xbfheader\nTX-001,2026-01-15,10.00,SGD\n"
        mapping = {"tx_id": 0, "date": 1, "amount": 2, "currency": 3}
        result = self._parser(column_mapping=mapping).parse(BytesIO(csv_bytes))
        assert len(result) == 1

    def test_optional_fields_absent_become_none(self):
        data = self._csv(
            "header",
            "TX-001,2026-01-15,10.00,SGD",
        )
        # Only 4-column mapping, no optional fields
        mapping = {"tx_id": 0, "date": 1, "amount": 2, "currency": 3}
        result = self._parser(column_mapping=mapping).parse(data)
        assert result[0].counterparty is None
        assert result[0].reference is None
        assert result[0].description is None

    def test_empty_optional_field_becomes_none(self):
        data = self._csv(
            "header",
            "TX-001,2026-01-15,10.00,SGD,,",
        )
        mapping = {"tx_id": 0, "date": 1, "amount": 2, "currency": 3, "counterparty": 4, "reference": 5}
        result = self._parser(column_mapping=mapping).parse(data)
        assert result[0].counterparty is None
        assert result[0].reference is None

    def test_default_column_mapping_is_independent_per_instance(self):
        # Verify two instances don't share mutable state
        p1 = GenericParser()
        p2 = GenericParser()
        assert p1._col is not p2._col
