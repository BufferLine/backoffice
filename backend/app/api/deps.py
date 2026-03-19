import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import select

from app.database import get_db
from app.models.user import Role, User
from app.services.auth import get_user_permissions, verify_api_token, verify_token

bearer_scheme = HTTPBearer(auto_error=False)


class AuthenticatedUser:
    """Wrapper that carries the ORM User plus pre-loaded permissions list."""

    def __init__(self, user: User, permissions: list[str]) -> None:
        self.user = user
        self.permissions = permissions
        # Proxy common attributes so callers can treat this as a User-like object.
        self.id = user.id
        self.email = user.email
        self.name = user.name
        self.is_active = user.is_active
        self.roles = user.roles
        self.created_at = user.created_at
        self.updated_at = user.updated_at


async def _load_user(db: AsyncSession, user_id: uuid.UUID) -> User | None:
    result = await db.execute(
        select(User)
        .where(User.id == user_id)
        .options(selectinload(User.roles).selectinload(Role.permissions))
    )
    return result.scalar_one_or_none()


async def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AuthenticatedUser:
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = credentials.credentials
    user_id: uuid.UUID | None = None

    # Distinguish JWT (three dot-separated segments) from opaque API tokens.
    if token.count(".") == 2:
        try:
            payload = verify_token(token)
            if payload.get("type") != "access":
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid token type",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            user_id = uuid.UUID(payload["sub"])
        except (JWTError, KeyError, ValueError):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )

        user = await _load_user(db, user_id)
        if user is None or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Permissions are embedded in the JWT for access tokens.
        permissions: list[str] = payload.get("permissions", [])
    else:
        # Opaque API token path.
        user_id = await verify_api_token(db, token)
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or revoked API token",
                headers={"WWW-Authenticate": "Bearer"},
            )

        user = await _load_user(db, user_id)
        if user is None or not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found or inactive",
                headers={"WWW-Authenticate": "Bearer"},
            )

        permissions = await get_user_permissions(db, user_id)

    return AuthenticatedUser(user=user, permissions=permissions)


def require_permission(*perms: str) -> Depends:
    """Dependency factory: checks that the current user has ALL listed permissions."""

    async def checker(
        current_user: Annotated[AuthenticatedUser, Depends(get_current_user)],
    ) -> AuthenticatedUser:
        user_perms = set(current_user.permissions)
        missing = [p for p in perms if p not in user_perms]
        if missing:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return current_user

    return Depends(checker)
