import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import AuthenticatedUser, get_current_user
from app.database import get_db
from app.models.user import ApiToken, User
from app.schemas.user import (
    ApiTokenCreate,
    ApiTokenCreated,
    ApiTokenResponse,
    LoginRequest,
    LoginResponse,
    MeResponse,
    RoleResponse,
)
from app.services.auth import (
    authenticate_user,
    create_access_token,
    create_api_token,
    create_refresh_token,
    get_user_permissions,
    verify_token,
)

router = APIRouter()


@router.post("/login", response_model=LoginResponse)
async def login(
    body: LoginRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LoginResponse:
    user = await authenticate_user(db, body.email, body.password)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    permissions = await get_user_permissions(db, user.id)
    access_token = create_access_token(user.id, permissions)
    refresh_token = create_refresh_token(user.id)

    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
    )


@router.post("/refresh", response_model=LoginResponse)
async def refresh(
    body: dict,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LoginResponse:
    refresh_token = body.get("refresh_token")
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="refresh_token is required",
        )

    try:
        payload = verify_token(refresh_token)
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired refresh token",
        )

    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type",
        )

    try:
        user_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token subject",
        )

    user_result = await db.execute(select(User).where(User.id == user_id))
    user = user_result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )

    permissions = await get_user_permissions(db, user_id)
    new_access_token = create_access_token(user_id, permissions)
    new_refresh_token = create_refresh_token(user_id)

    return LoginResponse(
        access_token=new_access_token,
        refresh_token=new_refresh_token,
        token_type="bearer",
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> None:
    # JWT tokens are stateless; no server-side revocation for JWT-based sessions.
    # API token revocation is handled via DELETE /api/auth/api-tokens/{id}.
    return None


@router.post("/api-tokens", response_model=ApiTokenCreated, status_code=status.HTTP_201_CREATED)
async def create_token(
    body: ApiTokenCreate,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ApiTokenCreated:
    raw_token, api_token = await create_api_token(
        db=db,
        user_id=current_user.id,
        name=body.name,
        expires_at=body.expires_at,
    )

    return ApiTokenCreated(
        id=api_token.id,
        name=api_token.name,
        token=raw_token,
        created_at=api_token.created_at,
    )


@router.delete("/api-tokens/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_token(
    token_id: uuid.UUID,
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    result = await db.execute(
        select(ApiToken).where(
            ApiToken.id == token_id,
            ApiToken.user_id == current_user.id,
        )
    )
    api_token = result.scalar_one_or_none()
    if api_token is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="API token not found",
        )

    if api_token.revoked_at is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="API token already revoked",
        )

    api_token.revoked_at = datetime.now(timezone.utc)
    return None


@router.get("/me", response_model=MeResponse)
async def me(
    current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
) -> MeResponse:
    return MeResponse(
        id=current_user.id,
        email=current_user.email,
        name=current_user.name,
        is_active=current_user.is_active,
        roles=[
            RoleResponse(
                id=r.id,
                name=r.name,
                description=r.description,
                is_system=r.is_system,
            )
            for r in current_user.roles
        ],
        permissions=current_user.permissions,
        created_at=current_user.created_at,
        updated_at=current_user.updated_at,
    )
