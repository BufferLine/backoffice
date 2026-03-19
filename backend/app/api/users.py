import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import AuthenticatedUser, require_permission
from app.database import get_db
from app.models.user import Role, User
from app.schemas.user import (
    MeResponse,
    RoleAssign,
    RoleResponse,
    UserCreate,
    UserResponse,
    UserUpdate,
)
from app.services.auth import get_user_permissions, hash_password

router = APIRouter()


def _user_to_response(user: User) -> UserResponse:
    return UserResponse(
        id=user.id,
        email=user.email,
        name=user.name,
        is_active=user.is_active,
        roles=[
            RoleResponse(
                id=r.id,
                name=r.name,
                description=r.description,
                is_system=r.is_system,
            )
            for r in user.roles
        ],
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


@router.post("/invite", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def invite_user(
    body: UserCreate,
    _: Annotated[AuthenticatedUser, require_permission("admin:manage_users")],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserResponse:
    result = await db.execute(select(User).where(User.email == body.email))
    if result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists",
        )

    user = User(
        email=body.email,
        name=body.name,
        password_hash=hash_password(body.password),
        is_active=True,
    )
    db.add(user)
    await db.flush()
    await db.refresh(user, attribute_names=["roles"])

    return _user_to_response(user)


@router.get("", response_model=list[UserResponse])
async def list_users(
    _: Annotated[AuthenticatedUser, require_permission("admin:manage_users")],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> list[UserResponse]:
    result = await db.execute(
        select(User)
        .options(selectinload(User.roles))
        .order_by(User.created_at)
    )
    users = result.scalars().all()
    return [_user_to_response(u) for u in users]


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: uuid.UUID,
    _: Annotated[AuthenticatedUser, require_permission("admin:manage_users")],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserResponse:
    result = await db.execute(
        select(User)
        .where(User.id == user_id)
        .options(selectinload(User.roles))
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return _user_to_response(user)


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: uuid.UUID,
    body: UserUpdate,
    _: Annotated[AuthenticatedUser, require_permission("admin:manage_users")],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserResponse:
    result = await db.execute(
        select(User)
        .where(User.id == user_id)
        .options(selectinload(User.roles))
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    if body.name is not None:
        user.name = body.name
    if body.is_active is not None:
        user.is_active = body.is_active

    await db.flush()
    await db.refresh(user)
    return _user_to_response(user)


@router.post("/{user_id}/roles", response_model=UserResponse)
async def assign_role(
    user_id: uuid.UUID,
    body: RoleAssign,
    _: Annotated[AuthenticatedUser, require_permission("admin:manage_roles")],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserResponse:
    result = await db.execute(
        select(User)
        .where(User.id == user_id)
        .options(selectinload(User.roles))
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    role_result = await db.execute(select(Role).where(Role.id == body.role_id))
    role = role_result.scalar_one_or_none()
    if role is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Role not found")

    if role not in user.roles:
        user.roles.append(role)
        await db.flush()

    return _user_to_response(user)


@router.delete("/{user_id}/roles/{role_id}", response_model=UserResponse)
async def remove_role(
    user_id: uuid.UUID,
    role_id: uuid.UUID,
    _: Annotated[AuthenticatedUser, require_permission("admin:manage_roles")],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserResponse:
    result = await db.execute(
        select(User)
        .where(User.id == user_id)
        .options(selectinload(User.roles))
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")

    role_to_remove = next((r for r in user.roles if r.id == role_id), None)
    if role_to_remove is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Role not assigned to this user",
        )

    user.roles.remove(role_to_remove)
    await db.flush()

    return _user_to_response(user)
