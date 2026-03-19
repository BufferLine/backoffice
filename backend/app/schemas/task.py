from datetime import date, datetime
from typing import Any, Optional
from uuid import UUID

from pydantic import BaseModel


class TaskTemplateCreate(BaseModel):
    title: str
    description: Optional[str] = None
    category: Optional[str] = None
    jurisdiction: Optional[str] = None
    frequency: str
    due_day: Optional[int] = None
    due_month: Optional[int] = None
    priority: Optional[str] = "medium"
    auto_generate: Optional[bool] = True


class TaskTemplateUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    frequency: Optional[str] = None
    due_day: Optional[int] = None
    due_month: Optional[int] = None
    priority: Optional[str] = None
    is_active: Optional[bool] = None
    auto_generate: Optional[bool] = None


class TaskTemplateResponse(BaseModel):
    id: UUID
    title: str
    description: Optional[str]
    category: Optional[str]
    jurisdiction: Optional[str]
    frequency: str
    due_day: Optional[int]
    due_month: Optional[int]
    priority: str
    is_system: bool
    is_active: bool
    auto_generate: bool
    metadata_json: Optional[Any]
    created_by: Optional[UUID]
    created_at: datetime

    model_config = {"from_attributes": True}


class TaskInstanceCreate(BaseModel):
    template_id: Optional[UUID] = None
    title: str
    description: Optional[str] = None
    category: Optional[str] = None
    priority: Optional[str] = "medium"
    period: Optional[str] = None
    due_date: Optional[date] = None
    notes: Optional[str] = None


class TaskInstanceUpdate(BaseModel):
    status: Optional[str] = None
    notes: Optional[str] = None
    priority: Optional[str] = None


class TaskInstanceResponse(BaseModel):
    id: UUID
    template_id: Optional[UUID]
    title: str
    description: Optional[str]
    category: Optional[str]
    priority: str
    period: Optional[str]
    due_date: Optional[date]
    status: str
    completed_at: Optional[datetime]
    completed_by: Optional[UUID]
    notes: Optional[str]
    metadata_json: Optional[Any]
    created_by: Optional[UUID]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TaskListResponse(BaseModel):
    items: list[TaskInstanceResponse]
    total: int


class TodoSummary(BaseModel):
    period: str
    pending: int
    in_progress: int
    completed: int
    overdue: int
    items: list[TaskInstanceResponse]
