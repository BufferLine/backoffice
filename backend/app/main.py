from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import auth, automation, bank_reconciliation, clients, expenses, exports, invoices, payments, payroll, tasks, users
from app.api import settings as settings_router
from app.api.payroll import employees_router
from app.config import settings
from app.database import AsyncSessionLocal
from app.services.auth import create_superadmin, seed_permissions, seed_roles
from app.services.task import seed_compliance_tasks


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: seed permissions, roles, and superadmin
    async with AsyncSessionLocal() as session:
        try:
            permissions_map = await seed_permissions(session)
            await seed_roles(session, permissions_map)
            await create_superadmin(session, settings.SUPERADMIN_EMAIL, settings.SUPERADMIN_PASSWORD)
            await seed_compliance_tasks(session)
            await session.commit()
        except Exception:
            await session.rollback()
            raise
    yield
    # Shutdown


app = FastAPI(
    title="Backoffice Operations API",
    version="0.1.0",
    description="Backoffice operations system for Singapore-based entity",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(users.router, prefix="/api/users", tags=["users"])
app.include_router(clients.router, prefix="/api/clients", tags=["clients"])
app.include_router(invoices.router, prefix="/api/invoices", tags=["invoices"])
app.include_router(payroll.router, prefix="/api/payroll", tags=["payroll"])
app.include_router(employees_router, prefix="/api/employees", tags=["employees"])
app.include_router(expenses.router, prefix="/api/expenses", tags=["expenses"])
app.include_router(payments.router, prefix="/api/payments", tags=["payments"])
app.include_router(exports.router, prefix="/api/exports", tags=["exports"])
app.include_router(automation.router, prefix="/api/automation", tags=["automation"])
app.include_router(bank_reconciliation.router, prefix="/api", tags=["bank-reconciliation"])
app.include_router(settings_router.router, prefix="/api/settings", tags=["settings"])
app.include_router(tasks.router, prefix="/api/tasks", tags=["tasks"])


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
