from app.jurisdiction.base import Deduction, JurisdictionBase, TaxResult
from app.jurisdiction.singapore import SingaporeJurisdiction, singapore

_jurisdictions: dict[str, JurisdictionBase] = {
    "SG": singapore,
}


def get_jurisdiction(code: str) -> JurisdictionBase:
    jurisdiction = _jurisdictions.get(code)
    if not jurisdiction:
        raise ValueError(f"Unknown jurisdiction: {code}")
    return jurisdiction
