import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import bcrypt
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.models.user import ApiToken, Permission, Role, User, role_permissions, user_roles

ALGORITHM = "HS256"


# --- Password helpers ---

def hash_password(password: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


# --- JWT helpers ---

def create_access_token(user_id: uuid.UUID, permissions: list[str]) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {
        "sub": str(user_id),
        "type": "access",
        "permissions": permissions,
        "exp": expire,
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=ALGORITHM)


def create_refresh_token(user_id: uuid.UUID) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        days=settings.JWT_REFRESH_TOKEN_EXPIRE_DAYS
    )
    payload = {
        "sub": str(user_id),
        "type": "refresh",
        "jti": str(uuid.uuid4()),
        "exp": expire,
    }
    return jwt.encode(payload, settings.JWT_SECRET, algorithm=ALGORITHM)


def verify_token(token: str) -> dict:
    """Decode and return JWT payload, raising JWTError on failure."""
    return jwt.decode(token, settings.JWT_SECRET, algorithms=[ALGORITHM])


# --- API token helpers ---

def _hash_api_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()


async def create_api_token(
    db: AsyncSession,
    user_id: uuid.UUID,
    name: str,
    expires_at: datetime | None = None,
) -> tuple[str, ApiToken]:
    """Generate a raw token, store its hash, return (raw_token, ApiToken record)."""
    raw_token = secrets.token_urlsafe(32)
    token_hash = _hash_api_token(raw_token)

    api_token = ApiToken(
        user_id=user_id,
        token_hash=token_hash,
        name=name,
        expires_at=expires_at,
    )
    db.add(api_token)
    await db.flush()
    await db.refresh(api_token)
    return raw_token, api_token


async def verify_api_token(db: AsyncSession, raw_token: str) -> uuid.UUID | None:
    """Verify raw API token, update last_used_at, return user_id or None."""
    token_hash = _hash_api_token(raw_token)
    result = await db.execute(
        select(ApiToken).where(ApiToken.token_hash == token_hash)
    )
    api_token = result.scalar_one_or_none()
    if api_token is None:
        return None
    if api_token.revoked_at is not None:
        return None
    now = datetime.now(timezone.utc)
    if api_token.expires_at is not None and api_token.expires_at < now:
        return None

    api_token.last_used_at = now
    await db.flush()
    return api_token.user_id


# --- User authentication ---

async def authenticate_user(db: AsyncSession, email: str, password: str) -> User | None:
    result = await db.execute(
        select(User)
        .where(User.email == email)
        .options(selectinload(User.roles).selectinload(Role.permissions))
    )
    user = result.scalar_one_or_none()
    if user is None:
        return None
    if not user.is_active:
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


async def get_user_permissions(db: AsyncSession, user_id: uuid.UUID) -> list[str]:
    """Return list of 'domain:action' strings for the user."""
    result = await db.execute(
        select(Permission)
        .join(role_permissions, Permission.id == role_permissions.c.permission_id)
        .join(Role, Role.id == role_permissions.c.role_id)
        .join(user_roles, Role.id == user_roles.c.role_id)
        .where(user_roles.c.user_id == user_id)
    )
    permissions = result.scalars().all()
    return [f"{p.domain}:{p.action}" for p in permissions]


# --- Seed / bootstrap helpers ---

_DEFAULT_PERMISSIONS: list[tuple[str, str, str]] = [
    ("invoice", "read", "Read invoices"),
    ("invoice", "write", "Create and update invoices"),
    ("payroll", "read", "Read payroll runs"),
    ("payroll", "write", "Create and update payroll runs"),
    ("payroll", "finalize", "Finalize payroll runs"),
    ("expense", "read", "Read expenses"),
    ("expense", "write", "Create and update expenses"),
    ("payment", "read", "Read payments"),
    ("payment", "write", "Create and update payments"),
    ("export", "read", "Read exports"),
    ("export", "write", "Create exports"),
    ("admin", "manage_users", "Manage users"),
    ("admin", "manage_roles", "Manage roles"),
    ("integration", "read", "Read integration status and events"),
    ("integration", "write", "Trigger integration syncs and manage providers"),
]

_DEFAULT_ROLES: list[tuple[str, str, list[str]]] = [
    (
        "superadmin",
        "Super administrator with full access",
        [f"{d}:{a}" for d, a, _ in _DEFAULT_PERMISSIONS],
    ),
    (
        "admin",
        "Administrator",
        [
            "invoice:read", "invoice:write",
            "payroll:read", "payroll:write",
            "expense:read", "expense:write",
            "payment:read", "payment:write",
            "export:read", "export:write",
            "admin:manage_users", "admin:manage_roles",
            "integration:read", "integration:write",
        ],
    ),
    (
        "accountant",
        "Accountant with read/write on financial records",
        [
            "invoice:read", "invoice:write",
            "payroll:read", "payroll:write", "payroll:finalize",
            "expense:read", "expense:write",
            "payment:read", "payment:write",
            "export:read", "export:write",
        ],
    ),
    (
        "viewer",
        "Read-only access to all financial records",
        [
            "invoice:read",
            "payroll:read",
            "expense:read",
            "payment:read",
            "export:read",
        ],
    ),
]


async def seed_permissions(db: AsyncSession) -> dict[str, Permission]:
    """Ensure all default permissions exist; return mapping of 'domain:action' → Permission."""
    result = await db.execute(select(Permission))
    existing = {f"{p.domain}:{p.action}": p for p in result.scalars().all()}

    for domain, action, description in _DEFAULT_PERMISSIONS:
        key = f"{domain}:{action}"
        if key not in existing:
            perm = Permission(domain=domain, action=action, description=description)
            db.add(perm)
            existing[key] = perm

    await db.flush()
    return existing


async def seed_roles(db: AsyncSession, permissions_map: dict[str, Permission]) -> None:
    """Ensure all default roles exist with correct permissions."""
    from app.models.user import role_permissions as rp_table

    result = await db.execute(select(Role))
    existing_roles = {r.name: r for r in result.scalars().all()}

    for role_name, description, perm_keys in _DEFAULT_ROLES:
        if role_name not in existing_roles:
            role = Role(name=role_name, description=description, is_system=True)
            db.add(role)
            await db.flush()
            existing_roles[role_name] = role

        role = existing_roles[role_name]

        # Get existing permission links via junction table
        existing_links = await db.execute(
            select(rp_table.c.permission_id).where(rp_table.c.role_id == role.id)
        )
        existing_perm_ids = {row[0] for row in existing_links.all()}

        for key in perm_keys:
            perm = permissions_map.get(key)
            if perm and perm.id not in existing_perm_ids:
                await db.execute(
                    rp_table.insert().values(role_id=role.id, permission_id=perm.id)
                )
                existing_perm_ids.add(perm.id)

    await db.flush()


async def create_superadmin(db: AsyncSession, email: str, password: str) -> None:
    """Create superadmin user if it does not exist."""
    result = await db.execute(select(User).where(User.email == email))
    if result.scalar_one_or_none() is not None:
        return

    # Ensure superadmin role exists
    role_result = await db.execute(
        select(Role)
        .where(Role.name == "superadmin")
        .options(selectinload(Role.permissions))
    )
    superadmin_role = role_result.scalar_one_or_none()

    user = User(
        email=email,
        name="Super Admin",
        password_hash=hash_password(password),
        is_active=True,
    )
    db.add(user)
    await db.flush()

    if superadmin_role is not None:
        # Use direct insert into junction table to avoid lazy-load issues
        from app.models.user import user_roles
        await db.execute(
            user_roles.insert().values(user_id=user.id, role_id=superadmin_role.id)
        )

    await db.flush()
