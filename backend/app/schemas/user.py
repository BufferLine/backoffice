import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, field_validator


class PermissionResponse(BaseModel):
    id: uuid.UUID
    domain: str
    action: str
    description: str | None

    model_config = {"from_attributes": True}


class RoleResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    is_system: bool

    model_config = {"from_attributes": True}


class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    name: str
    is_active: bool
    roles: list[RoleResponse]
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MeResponse(UserResponse):
    permissions: list[str]  # "domain:action" strings


def _validate_password(v: str) -> str:
    if len(v) < 8:
        raise ValueError("Password must be at least 8 characters")
    return v


class UserCreate(BaseModel):
    email: EmailStr
    name: str
    password: str

    @field_validator("password")
    @classmethod
    def check_password(cls, v: str) -> str:
        return _validate_password(v)


class UserUpdate(BaseModel):
    name: str | None = None
    is_active: bool | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    refresh_token: str


class ApiTokenCreate(BaseModel):
    name: str
    expires_at: datetime | None = None


class ApiTokenResponse(BaseModel):
    id: uuid.UUID
    name: str
    last_used_at: datetime | None
    expires_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class ApiTokenCreated(BaseModel):
    id: uuid.UUID
    name: str
    token: str
    created_at: datetime


class RoleAssign(BaseModel):
    role_id: uuid.UUID
