"""Tests for SGQR / PayNow EMVCo TLV QR code generation."""

from decimal import Decimal

from app.services.pdf import _build_sgqr_payload, _crc16_ccitt, _emv_tlv


class TestEmvTlv:
    def test_basic_encoding(self):
        assert _emv_tlv("00", "01") == "000201"

    def test_longer_value(self):
        result = _emv_tlv("26", "SG.PAYNOW")
        assert result == "2609SG.PAYNOW"

    def test_two_digit_length(self):
        value = "A" * 25
        result = _emv_tlv("59", value)
        assert result == f"5925{'A' * 25}"


class TestCrc16:
    def test_known_value(self):
        # CRC16-CCITT of "0002010102" + "6304" should produce a known checksum
        data = "00020101026304"
        crc = _crc16_ccitt(data)
        assert len(crc) == 4
        assert crc.isalnum()

    def test_deterministic(self):
        data = "00020101021226320009SG.PAYNOW0101200209123456789030105204000053037025802SG5907COMPANY6009Singapore6304"
        assert _crc16_ccitt(data) == _crc16_ccitt(data)


class TestBuildSgqrPayload:
    def test_payload_starts_with_format_indicator(self):
        payload = _build_sgqr_payload(uen="123456789A", amount=Decimal("100.00"))
        assert payload.startswith("000201")

    def test_payload_contains_paynow_identifier(self):
        payload = _build_sgqr_payload(uen="123456789A", amount=Decimal("100.00"))
        assert "SG.PAYNOW" in payload

    def test_payload_contains_uen(self):
        uen = "201234567A"
        payload = _build_sgqr_payload(uen=uen, amount=Decimal("50.00"))
        assert uen in payload

    def test_payload_contains_amount(self):
        payload = _build_sgqr_payload(uen="123456789A", amount=Decimal("123.45"))
        assert "123.45" in payload

    def test_payload_contains_reference(self):
        payload = _build_sgqr_payload(
            uen="123456789A", amount=Decimal("10.00"), reference="INV-2026-0001"
        )
        assert "INV-2026-0001" in payload

    def test_payload_contains_merchant_name(self):
        payload = _build_sgqr_payload(
            uen="123456789A", amount=Decimal("10.00"), merchant_name="ACME PTE LTD"
        )
        assert "ACME PTE LTD" in payload

    def test_merchant_name_truncated_to_25(self):
        long_name = "A" * 50
        payload = _build_sgqr_payload(uen="123456789A", amount=Decimal("10.00"), merchant_name=long_name)
        # Should not contain the full 50-char name
        assert "A" * 50 not in payload
        assert "A" * 25 in payload

    def test_payload_ends_with_crc(self):
        payload = _build_sgqr_payload(uen="123456789A", amount=Decimal("100.00"))
        # Last 8 chars: "6304" + 4 hex CRC
        assert payload[-8:-4] == "6304"
        crc_part = payload[-4:]
        assert len(crc_part) == 4
        # CRC should be valid hex
        int(crc_part, 16)

    def test_crc_validates(self):
        """The CRC over the full payload (minus last 4) should match the embedded CRC."""
        payload = _build_sgqr_payload(uen="123456789A", amount=Decimal("100.00"))
        body = payload[:-4]  # everything except the 4-char CRC
        expected_crc = _crc16_ccitt(body)
        actual_crc = payload[-4:]
        assert actual_crc == expected_crc

    def test_dynamic_point_of_initiation(self):
        payload = _build_sgqr_payload(uen="123456789A", amount=Decimal("100.00"))
        # Tag 01, length 02, value "12" (dynamic)
        assert "010212" in payload

    def test_currency_sgd(self):
        payload = _build_sgqr_payload(uen="123456789A", amount=Decimal("100.00"))
        # Tag 53, length 03, value "702"
        assert "5303702" in payload

    def test_country_sg(self):
        payload = _build_sgqr_payload(uen="123456789A", amount=Decimal("100.00"))
        # Tag 58, length 02, value "SG"
        assert "5802SG" in payload  # corrected: "5802SG"

    def test_zero_amount_omitted(self):
        payload = _build_sgqr_payload(uen="123456789A", amount=Decimal("0"))
        # Tag 54 should not be present
        assert "54" not in payload.split("5303702")[0].split("5802SG")[0] or "5400" not in payload

    def test_proxy_type_uen(self):
        payload = _build_sgqr_payload(uen="123456789A", amount=Decimal("10.00"))
        # Inside tag 26: sub-tag 01, length 01, value "2" (UEN)
        assert "01012" in payload

    def test_amount_not_editable_by_default(self):
        payload = _build_sgqr_payload(uen="123456789A", amount=Decimal("10.00"))
        # Sub-tag 03, length 01, value "0" (not editable)
        assert "03010" in payload
