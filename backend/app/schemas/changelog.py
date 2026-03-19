from datetime import date, datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class ChangeLogResponse(BaseModel):
    id: UUID
    entity_type: str
    entity_id: UUID
    field_name: str
    old_value: Optional[str]
    new_value: Optional[str]
    effective_date: Optional[date]
    reason: Optional[str]
    changed_by: Optional[UUID]
    created_at: datetime
    model_config = {"from_attributes": True}


class ChangeLogListResponse(BaseModel):
    items: list[ChangeLogResponse]
    total: int
