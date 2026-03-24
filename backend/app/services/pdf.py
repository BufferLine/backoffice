import base64
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional

from jinja2 import Environment, FileSystemLoader

TEMPLATE_DIR = Path(__file__).parent.parent / "templates"

_env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), autoescape=True)


def _money(value, precision=2) -> str:
    """Format a Decimal/str/float as a money string with fixed precision."""
    d = Decimal(str(value)) if not isinstance(value, Decimal) else value
    return f"{d:.{precision}f}"


def _pct(value) -> str:
    """Format a rate as percentage (e.g., 0.09 → 9.0)."""
    d = Decimal(str(value)) if not isinstance(value, Decimal) else value
    return f"{d * 100:.2f}"


_env.filters["money"] = _money
_env.filters["pct"] = _pct


_DEFAULT_THEME = {
    "primary_color": "#1a56db",
    "accent_color": "#374151",
    "font_family": "Helvetica, Arial, sans-serif",
}


def _encode_image(image_bytes: Optional[bytes], mime_type: str = "image/png") -> Optional[str]:
    """Encode image bytes as a data URI for embedding in HTML."""
    if not image_bytes:
        return None
    b64 = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{mime_type};base64,{b64}"


# Keep backward-compatible alias
_encode_stamp = _encode_image


def _emv_tlv(tag: str, value: str) -> str:
    """Encode a single EMVCo TLV (Tag-Length-Value) data object.

    Length is measured in bytes (ASCII), not Python characters.
    Non-ASCII characters are stripped to ensure valid EMVCo payload.
    """
    ascii_value = value.encode("ascii", errors="ignore").decode("ascii")
    return f"{tag}{len(ascii_value):02d}{ascii_value}"


def _crc16_ccitt(data: str) -> str:
    """Compute CRC16-CCITT (0xFFFF) over a string and return 4-char hex."""
    crc = 0xFFFF
    for byte in data.encode("ascii"):
        crc ^= byte << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = (crc << 1) ^ 0x1021
            else:
                crc <<= 1
            crc &= 0xFFFF
    return f"{crc:04X}"


def _build_sgqr_payload(
    uen: str,
    amount: Decimal,
    reference: str = "",
    merchant_name: str = "",
    editable: bool = False,
) -> str:
    """Build EMVCo Merchant Presented QR payload for PayNow (SGQR).

    Follows EMVCo QR Code Specification for Payment Systems v1.1
    with PayNow-specific Merchant Account Information (tag 26).
    """
    # Tag 26: Merchant Account Information — PayNow
    mai_value = (
        _emv_tlv("00", "SG.PAYNOW")     # Globally unique identifier
        + _emv_tlv("01", "2")             # Proxy type: 2 = UEN
        + _emv_tlv("02", uen)             # Proxy value (UEN)
        + _emv_tlv("03", "0" if not editable else "1")  # Amount editable
    )

    parts = [
        _emv_tlv("00", "01"),             # Payload Format Indicator
        _emv_tlv("01", "12"),             # Point of Initiation: 12 = dynamic
        _emv_tlv("26", mai_value),        # PayNow merchant account info
        _emv_tlv("52", "0000"),           # Merchant Category Code (not applicable)
        _emv_tlv("53", "702"),            # Transaction Currency: 702 = SGD
    ]

    # Tag 54: Transaction Amount (omit for open amount)
    if amount and amount > 0:
        parts.append(_emv_tlv("54", f"{amount:.2f}"))

    parts.append(_emv_tlv("58", "SG"))   # Country Code

    # Tag 59: Merchant Name (max 25 chars per spec)
    name = (merchant_name or "COMPANY")[:25]
    parts.append(_emv_tlv("59", name))

    parts.append(_emv_tlv("60", "Singapore"))  # Merchant City

    # Tag 62: Additional Data Field Template
    if reference:
        ref_trimmed = reference[:25]  # max 25 chars per spec
        parts.append(_emv_tlv("62", _emv_tlv("01", ref_trimmed)))

    # Tag 63: CRC — placeholder "0000" first, then compute over full string
    payload_without_crc = "".join(parts) + "6304"
    crc = _crc16_ccitt(payload_without_crc)
    return payload_without_crc + crc


def _generate_paynow_qr(
    uen: str,
    amount: Decimal,
    reference: str = "",
    merchant_name: str = "",
) -> Optional[str]:
    """Generate PayNow SGQR code (EMVCo TLV format) as base64 data URI."""
    try:
        import qrcode
        from io import BytesIO

        payload = _build_sgqr_payload(
            uen=uen,
            amount=amount,
            reference=reference,
            merchant_name=merchant_name,
        )

        qr = qrcode.make(payload, box_size=4, border=2)
        buffer = BytesIO()
        qr.save(buffer, format="PNG")
        b64 = base64.b64encode(buffer.getvalue()).decode("ascii")
        return f"data:image/png;base64,{b64}"
    except ImportError:
        return None


def render_pdf(
    template_name: str,
    data: dict[str, Any],
    stamp_bytes: Optional[bytes] = None,
    stamp_mime: str = "image/png",
    logo_bytes: Optional[bytes] = None,
    logo_mime: str = "image/png",
    theme: Optional[dict] = None,
) -> bytes:
    """Render any document template to PDF bytes using WeasyPrint.

    Supported templates: invoice.html, payslip.html, loan_agreement.html
    All templates share base.css and receive stamp_uri, logo_uri, and theme.
    """
    try:
        from weasyprint import HTML
    except ImportError:
        raise RuntimeError("WeasyPrint is not installed")

    data["stamp_uri"] = _encode_image(stamp_bytes, stamp_mime)
    data["logo_uri"] = _encode_image(logo_bytes, logo_mime)
    data["theme"] = {**_DEFAULT_THEME, **(theme or {})}
    template = _env.get_template(template_name)
    html_content = template.render(**data)
    return HTML(string=html_content).write_pdf()


# Convenience wrappers for backward compatibility

def render_invoice_pdf(data: dict[str, Any], **kwargs) -> bytes:
    return render_pdf("invoice.html", data, **kwargs)


def render_payslip_pdf(data: dict[str, Any], **kwargs) -> bytes:
    return render_pdf("payslip.html", data, **kwargs)


def render_loan_agreement_pdf(data: dict[str, Any], **kwargs) -> bytes:
    return render_pdf("loan_agreement.html", data, **kwargs)
