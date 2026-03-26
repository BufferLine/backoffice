from app.statement_parsers.airwallex import AirwallexParser
from app.statement_parsers.base import StatementParser
from app.statement_parsers.dbs import DBSParser
from app.statement_parsers.generic import GenericParser

_parsers: dict[str, type[StatementParser]] = {
    "airwallex": AirwallexParser,
    "dbs": DBSParser,
    "generic": GenericParser,
}


def get_parser(source: str) -> StatementParser:
    parser_cls = _parsers.get(source)
    if parser_cls is None:
        raise ValueError(f"Unknown statement source: {source!r}. Available: {list(_parsers.keys())}")
    return parser_cls()
