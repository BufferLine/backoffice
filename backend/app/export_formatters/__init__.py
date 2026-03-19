from app.export_formatters.base import ExportFormatter
from app.export_formatters.generic_csv import GenericCsvFormatter

_formatters = {
    "generic_csv": GenericCsvFormatter,
}


def get_formatter(name: str = "generic_csv") -> ExportFormatter:
    cls = _formatters.get(name)
    if not cls:
        raise ValueError(f"Unknown formatter: {name}")
    return cls()
