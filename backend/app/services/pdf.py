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
    return f"{d * 100:.1f}"


_env.filters["money"] = _money
_env.filters["pct"] = _pct


def _encode_stamp(stamp_bytes: Optional[bytes], mime_type: str = "image/png") -> Optional[str]:
    """Encode stamp image bytes as a data URI for embedding in HTML."""
    if not stamp_bytes:
        return None
    b64 = base64.b64encode(stamp_bytes).decode("ascii")
    return f"data:{mime_type};base64,{b64}"


def render_invoice_pdf(data: dict[str, Any], stamp_bytes: Optional[bytes] = None, stamp_mime: str = "image/png") -> bytes:
    """Render invoice data to PDF bytes using WeasyPrint."""
    try:
        from weasyprint import HTML
    except ImportError:
        raise RuntimeError("WeasyPrint is not installed")

    data["stamp_uri"] = _encode_stamp(stamp_bytes, stamp_mime)
    template = _env.get_template("invoice.html")
    html_content = template.render(**data)
    return HTML(string=html_content).write_pdf()


def render_payslip_pdf(data: dict[str, Any], stamp_bytes: Optional[bytes] = None, stamp_mime: str = "image/png") -> bytes:
    """Render payslip data to PDF bytes using WeasyPrint."""
    try:
        from weasyprint import HTML
    except ImportError:
        raise RuntimeError("WeasyPrint is not installed")

    data["stamp_uri"] = _encode_stamp(stamp_bytes, stamp_mime)
    template = _env.get_template("payslip.html")
    html_content = template.render(**data)
    return HTML(string=html_content).write_pdf()
