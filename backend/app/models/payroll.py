import uuid
from datetime import date, datetime

from sqlalchemy import Date, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMPTZ, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.database import Base


class Employee(Base):
    __tablename__ = "employees"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    base_salary: Mapped[float] = mapped_column(Numeric(19, 6), nullable=False)
    salary_currency: Mapped[str] = mapped_column(
        String(10), ForeignKey("currencies.code", ondelete="RESTRICT"), nullable=False
    )
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    work_pass_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    tax_residency: Mapped[str | None] = mapped_column(String(10), nullable=True)
    bank_details_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    salary_currency_rel = relationship("Currency", foreign_keys=[salary_currency])
    payroll_runs: Mapped[list["PayrollRun"]] = relationship("PayrollRun", back_populates="employee")


class PayrollRun(Base):
    __tablename__ = "payroll_runs"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_payroll_runs_idempotency_key"),
        UniqueConstraint("employee_id", "month", name="uq_payroll_runs_employee_month"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    employee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("employees.id", ondelete="RESTRICT"), nullable=False
    )
    month: Mapped[date] = mapped_column(Date, nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    days_in_month: Mapped[int] = mapped_column(Integer, nullable=False)
    days_worked: Mapped[int] = mapped_column(Integer, nullable=False)
    monthly_base_salary: Mapped[float] = mapped_column(Numeric(19, 6), nullable=False)
    currency: Mapped[str] = mapped_column(
        String(10), ForeignKey("currencies.code", ondelete="RESTRICT"), nullable=False
    )
    prorated_gross_salary: Mapped[float] = mapped_column(Numeric(19, 6), nullable=False)
    total_deductions: Mapped[float] = mapped_column(Numeric(19, 6), nullable=False, default=0)
    net_salary: Mapped[float] = mapped_column(Numeric(19, 6), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    payslip_file_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("files.id", ondelete="SET NULL"), nullable=True
    )
    paid_at: Mapped[datetime | None] = mapped_column(TIMESTAMPTZ, nullable=True)
    payment_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payments.id", ondelete="SET NULL"), nullable=True
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(TIMESTAMPTZ, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ, nullable=False, server_default=func.now(), onupdate=func.now()
    )

    employee: Mapped["Employee"] = relationship("Employee", back_populates="payroll_runs")
    currency_rel = relationship("Currency", foreign_keys=[currency])
    payslip_file = relationship("File", foreign_keys=[payslip_file_id])
    payment = relationship("Payment", foreign_keys=[payment_id])
    creator = relationship("User", foreign_keys=[created_by])
    deductions: Mapped[list["PayrollDeduction"]] = relationship(
        "PayrollDeduction", back_populates="payroll_run", cascade="all, delete-orphan"
    )


class PayrollDeduction(Base):
    __tablename__ = "payroll_deductions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    payroll_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("payroll_runs.id", ondelete="CASCADE"), nullable=False
    )
    deduction_type: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)
    amount: Mapped[float] = mapped_column(Numeric(19, 6), nullable=False)
    rate: Mapped[float | None] = mapped_column(Numeric(10, 6), nullable=True)
    cap_amount: Mapped[float | None] = mapped_column(Numeric(19, 6), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    payroll_run: Mapped["PayrollRun"] = relationship("PayrollRun", back_populates="deductions")
