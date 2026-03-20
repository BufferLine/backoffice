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


def _generate_paynow_qr(uen: str, amount: Decimal, reference: str = "") -> Optional[str]:
    """Generate PayNow QR code as base64 data URI."""
    try:
        import qrcode
        from io import BytesIO

        # SGQR PayNow format (simplified)
        # Format: UEN + amount for basic PayNow transfer
        payload = f"https://www.paynow.sg/pay?uen={uen}&amount={amount}"
        if reference:
            payload += f"&ref={reference}"

        qr = qrcode.make(payload, box_size=4, border=2)
        buffer = BytesIO()
        qr.save(buffer, format="PNG")
        b64 = base64.b64encode(buffer.getvalue()).decode("ascii")
        return f"data:image/png;base64,{b64}"
    except ImportError:
        return None


def render_invoice_pdf(
    data: dict[str, Any],
    stamp_bytes: Optional[bytes] = None,
    stamp_mime: str = "image/png",
    logo_bytes: Optional[bytes] = None,
    logo_mime: str = "image/png",
    theme: Optional[dict] = None,
) -> bytes:
    """Render invoice data to PDF bytes using WeasyPrint."""
    try:
        from weasyprint import HTML
    except ImportError:
        raise RuntimeError("WeasyPrint is not installed")

    data["stamp_uri"] = _encode_image(stamp_bytes, stamp_mime)
    data["logo_uri"] = _encode_image(logo_bytes, logo_mime)
    data["theme"] = {**_DEFAULT_THEME, **(theme or {})}
    template = _env.get_template("invoice.html")
    html_content = template.render(**data)
    return HTML(string=html_content).write_pdf()


def render_payslip_pdf(
    data: dict[str, Any],
    stamp_bytes: Optional[bytes] = None,
    stamp_mime: str = "image/png",
    logo_bytes: Optional[bytes] = None,
    logo_mime: str = "image/png",
    theme: Optional[dict] = None,
) -> bytes:
    """Render payslip data to PDF bytes using WeasyPrint."""
    try:
        from weasyprint import HTML
    except ImportError:
        raise RuntimeError("WeasyPrint is not installed")

    data["stamp_uri"] = _encode_image(stamp_bytes, stamp_mime)
    data["logo_uri"] = _encode_image(logo_bytes, logo_mime)
    data["theme"] = {**_DEFAULT_THEME, **(theme or {})}
    template = _env.get_template("payslip.html")
    html_content = template.render(**data)
    return HTML(string=html_content).write_pdf()
