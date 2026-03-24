from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.config import settings

limiter = Limiter(key_func=get_remote_address)
from app.api import auth, automation, bank_reconciliation, changelog, clients, expenses, exports, files, invoices, payments, payroll, setup, tasks, users
from app.api import settings as settings_router
from app.api import accounts, transactions, recurring_commitments
from app.api import payment_methods
from app.api import integrations as integrations_router
from app.api.payroll import employees_router
from app.database import AsyncSessionLocal
from app.services.auth import seed_permissions, seed_roles
from app.services.task import seed_compliance_tasks

_DEFAULT_CURRENCIES = [
    ("SGD", "Singapore Dollar", "S$", 2, 6, False, None),
    ("USD", "US Dollar", "$", 2, 6, False, None),
    ("KRW", "Korean Won", "₩", 0, 6, False, None),
    ("USDC", "USD Coin", "USDC", 2, 6, True, "ethereum"),
    ("USDT", "Tether", "USDT", 2, 6, True, "ethereum"),
]


async def _seed_currencies(session):
    from sqlalchemy import select
    from app.models.currency import Currency
    result = await session.execute(select(Currency.code))
    existing = {row[0] for row in result.all()}
    for code, name, symbol, display_prec, storage_prec, is_crypto, chain_id in _DEFAULT_CURRENCIES:
        if code not in existing:
            session.add(Currency(
                code=code, name=name, symbol=symbol,
                display_precision=display_prec, storage_precision=storage_prec,
                is_crypto=is_crypto, chain_id=chain_id, is_active=True,
            ))
    await session.flush()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: seed currencies; seed permissions/roles only if users exist (post-onboarding)
    from sqlalchemy import select, func
    from app.models.user import User
    async with AsyncSessionLocal() as session:
        try:
            await _seed_currencies(session)
            result = await session.execute(select(func.count()).select_from(User))
            user_count = result.scalar()
            if user_count and user_count > 0:
                permissions_map = await seed_permissions(session)
                await seed_roles(session, permissions_map)
                await seed_compliance_tasks(session)
            await session.commit()
        except Exception:
            await session.rollback()
            raise

    if settings.ENABLE_SYNC_SCHEDULER:
        from app.scheduler import start_scheduler
        await start_scheduler()

    yield

    # Shutdown
    if settings.ENABLE_SYNC_SCHEDULER:
        from app.scheduler import stop_scheduler
        await stop_scheduler()


app = FastAPI(
    title="Backoffice Operations API",
    version="0.1.0",
    description="Backoffice operations system for Singapore-based entity",
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, lambda req, exc: Response(
    status_code=429, content=f'{{"detail": "Rate limit exceeded: {exc.detail}"}}',
    media_type="application/json",
))

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS.split(","),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    if settings.ENVIRONMENT == "production":
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response

app.include_router(setup.router, prefix="/api/setup", tags=["setup"])
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(clients.router, prefix="/api/clients", tags=["clients"])
app.include_router(invoices.router, prefix="/api/invoices", tags=["invoices"])
app.include_router(payroll.router, prefix="/api/payroll", tags=["payroll"])
app.include_router(employees_router, prefix="/api/employees", tags=["employees"])
app.include_router(expenses.router, prefix="/api/expenses", tags=["expenses"])
app.include_router(payments.router, prefix="/api/payments", tags=["payments"])
app.include_router(exports.router, prefix="/api/exports", tags=["exports"])
app.include_router(files.router, prefix="/api/files", tags=["files"])
app.include_router(automation.router, prefix="/api/automation", tags=["automation"])
app.include_router(bank_reconciliation.router, prefix="/api", tags=["bank-reconciliation"])
app.include_router(settings_router.router, prefix="/api/settings", tags=["settings"])
app.include_router(tasks.router, prefix="/api/tasks", tags=["tasks"])
app.include_router(changelog.router, prefix="/api/changelog", tags=["changelog"])
app.include_router(accounts.router, prefix="/api/accounts", tags=["accounts"])
app.include_router(transactions.router, prefix="/api/transactions", tags=["transactions"])
app.include_router(recurring_commitments.router, prefix="/api/recurring-commitments", tags=["recurring-commitments"])
app.include_router(payment_methods.router, prefix="/api/payment-methods", tags=["payment-methods"])
app.include_router(integrations_router.router, prefix="/api", tags=["integrations"])


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
