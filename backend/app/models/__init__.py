# Import all models here so Alembic can discover them via Base.metadata

from app.models.audit import AuditLog  # noqa: F401
from app.models.bank_transaction import BankTransaction  # noqa: F401
from app.models.client import Client  # noqa: F401
from app.models.company import CompanySettings  # noqa: F401
from app.models.currency import Currency  # noqa: F401
from app.models.expense import Expense  # noqa: F401
from app.models.export import ExportPack  # noqa: F401
from app.models.file import File  # noqa: F401
from app.models.invoice import Invoice, InvoiceLineItem, RecurringInvoiceRule  # noqa: F401
from app.models.payment import Payment  # noqa: F401
from app.models.payroll import Employee, PayrollDeduction, PayrollRun  # noqa: F401
from app.models.task import TaskInstance, TaskTemplate  # noqa: F401
from app.models.user import ApiToken, Permission, Role, User, role_permissions, user_roles  # noqa: F401
from app.models.changelog import ChangeLog  # noqa: F401
from app.models.account import Account  # noqa: F401
from app.models.transaction import Transaction  # noqa: F401
from app.models.recurring_commitment import RecurringCommitment  # noqa: F401
