from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class LedgerAccountsResponse(BaseModel):
    receivable: dict[str, UUID] = {}
    revenue: Optional[UUID] = None
    gst_output: Optional[UUID] = None
    fx_gain_loss: Optional[UUID] = None
    configured: bool = False


class LedgerAccountsUpdate(BaseModel):
    """Mappings to set; omitted fields keep their current value."""

    receivable: Optional[dict[str, UUID]] = None
    revenue: Optional[UUID] = None
    gst_output: Optional[UUID] = None
    fx_gain_loss: Optional[UUID] = None
