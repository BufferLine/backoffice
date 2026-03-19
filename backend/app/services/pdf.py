from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader

TEMPLATE_DIR = Path(__file__).parent.parent / "templates"

_env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)), autoescape=True)


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
