import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.company import CompanySettings
from app.models.setup import SetupToken
from app.models.user import Role, User, user_roles
from app.schemas.user import LoginResponse
from app.services.auth import (
    create_access_token,
    create_refresh_token,
    get_user_permissions,
    hash_password,
    seed_permissions,
    seed_roles,
)
from app.services.task import seed_compliance_tasks

router = APIRouter()

_DEFAULT_CURRENCIES = [
    ("SGD", "Singapore Dollar", "S$", 2, 6, False, None),
    ("USD", "US Dollar", "$", 2, 6, False, None),
    ("KRW", "Korean Won", "₩", 0, 6, False, None),
    ("USDC", "USD Coin", "USDC", 2, 6, True, "ethereum"),
    ("USDT", "Tether", "USDT", 2, 6, True, "ethereum"),
]


def _hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


class SetupInitRequest(BaseModel):
    company_name: str
    jurisdiction: str = "SG"
    uen: Optional[str] = None


class SetupInitResponse(BaseModel):
    setup_url: str
    expires_in: int
    message: str


class SetupCompleteRequest(BaseModel):
    token: str
    email: str
    password: str
    name: str


@router.post("/init", response_model=SetupInitResponse)
async def setup_init(
    body: SetupInitRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> SetupInitResponse:
    # Check if any user exists
    result = await db.execute(select(func.count()).select_from(User))
    user_count = result.scalar()
    if user_count and user_count > 0:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="System already initialized",
        )

    # Create or update company settings
    company_result = await db.execute(select(CompanySettings).limit(1))
    company = company_result.scalar_one_or_none()
    if company is None:
        company = CompanySettings(
            legal_name=body.company_name,
            uen=body.uen,
            jurisdiction=body.jurisdiction,
        )
        db.add(company)
    else:
        company.legal_name = body.company_name
        if body.uen is not None:
            company.uen = body.uen
        company.jurisdiction = body.jurisdiction
    await db.flush()

    # Seed currencies if not exist
    from app.models.currency import Currency
    cur_result = await db.execute(select(Currency.code))
    existing_codes = {row[0] for row in cur_result.all()}
    for code, name, symbol, display_prec, storage_prec, is_crypto, chain_id in _DEFAULT_CURRENCIES:
        if code not in existing_codes:
            db.add(Currency(
                code=code, name=name, symbol=symbol,
                display_precision=display_prec, storage_precision=storage_prec,
                is_crypto=is_crypto, chain_id=chain_id, is_active=True,
            ))
    await db.flush()

    # Generate setup token
    raw_token = secrets.token_urlsafe(48)
    token_hash = _hash_token(raw_token)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

    setup_token = SetupToken(
        token_hash=token_hash,
        company_name=body.company_name,
        jurisdiction=body.jurisdiction,
        expires_at=expires_at,
    )
    db.add(setup_token)
    await db.flush()

    setup_url = f"http://localhost:3000/setup?token={raw_token}"

    return SetupInitResponse(
        setup_url=setup_url,
        expires_in=3600,
        message="Open this URL in your browser to create your admin account",
    )


@router.post("/complete", response_model=LoginResponse)
async def setup_complete(
    body: SetupCompleteRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LoginResponse:
    token_hash = _hash_token(body.token)

    result = await db.execute(
        select(SetupToken).where(SetupToken.token_hash == token_hash)
    )
    setup_token = result.scalar_one_or_none()

    if setup_token is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid setup token",
        )

    now = datetime.now(timezone.utc)
    if setup_token.expires_at < now:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Setup token has expired",
        )

    if setup_token.used_at is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Setup token has already been used",
        )

    # Seed permissions and roles
    permissions_map = await seed_permissions(db)
    await seed_roles(db, permissions_map)
    await seed_compliance_tasks(db)

    # Get superadmin role
    role_result = await db.execute(select(Role).where(Role.name == "superadmin"))
    superadmin_role = role_result.scalar_one_or_none()

    # Create the admin user
    user = User(
        email=body.email,
        name=body.name,
        password_hash=hash_password(body.password),
        is_active=True,
    )
    db.add(user)
    await db.flush()

    if superadmin_role is not None:
        await db.execute(
            user_roles.insert().values(user_id=user.id, role_id=superadmin_role.id)
        )

    # Mark token as used
    setup_token.used_at = now
    await db.flush()

    # Generate tokens for auto-login
    permissions = await get_user_permissions(db, user.id)
    access_token = create_access_token(user.id, permissions)
    refresh_token = create_refresh_token(user.id)

    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
    )
