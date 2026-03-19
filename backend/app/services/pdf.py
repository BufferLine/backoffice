from decimal import Decimal
from pathlib import Path
from typing import Any

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


def render_invoice_pdf(data: dict[str, Any]) -> bytes:
    """Render invoice data to PDF bytes using WeasyPrint."""
    try:
        from weasyprint import HTML
    except ImportError:
        raise RuntimeError("WeasyPrint is not installed")

    template = _env.get_template("invoice.html")
    html_content = template.render(**data)
    return HTML(string=html_content).write_pdf()


def render_payslip_pdf(data: dict[str, Any]) -> bytes:
    """Render payslip data to PDF bytes using WeasyPrint."""
    try:
        from weasyprint import HTML
    except ImportError:
        raise RuntimeError("WeasyPrint is not installed")

    template = _env.get_template("payslip.html")
    html_content = template.render(**data)
    return HTML(string=html_content).write_pdf()
