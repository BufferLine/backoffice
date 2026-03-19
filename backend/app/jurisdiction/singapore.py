from decimal import ROUND_HALF_UP, Decimal

from app.jurisdiction.base import Deduction, JurisdictionBase, TaxResult


class SingaporeJurisdiction(JurisdictionBase):
    """Singapore payroll and tax rules."""

    SDL_RATE = Decimal("0.0025")  # 0.25%
    SDL_CAP_LOW = Decimal("11.25")  # Cap for salary <= $4,500
    SDL_THRESHOLD = Decimal("4500")

    def calculate_deductions(self, gross_salary: Decimal, work_pass_type: str, **kwargs) -> list[Deduction]:
        deductions = []

        # SDL applies to all employees
        sdl_amount = gross_salary * self.SDL_RATE
        if gross_salary <= self.SDL_THRESHOLD:
            sdl_amount = min(sdl_amount, self.SDL_CAP_LOW)
        sdl_amount = sdl_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        deductions.append(
            Deduction(
                deduction_type="sdl",
                description="Skills Development Levy",
                amount=sdl_amount,
                rate=self.SDL_RATE,
                cap_amount=self.SDL_CAP_LOW if gross_salary <= self.SDL_THRESHOLD else None,
                metadata={"jurisdiction": "SG"},
            )
        )

        # CPF for citizens and PRs
        if work_pass_type in ("citizen", "pr"):
            # Simplified CPF calculation — full implementation would use age bands
            employee_rate = Decimal("0.20")  # 20% for <=55
            employer_rate = Decimal("0.17")  # 17% for <=55

            cpf_employee = (gross_salary * employee_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            cpf_employer = (gross_salary * employer_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            deductions.append(
                Deduction(
                    deduction_type="cpf_employee",
                    description="CPF Employee Contribution",
                    amount=cpf_employee,
                    rate=employee_rate,
                    metadata={"jurisdiction": "SG"},
                )
            )
            deductions.append(
                Deduction(
                    deduction_type="cpf_employer",
                    description="CPF Employer Contribution",
                    amount=cpf_employer,
                    rate=employer_rate,
                    metadata={"jurisdiction": "SG", "employer_cost": True},
                )
            )

        return deductions

    def calculate_invoice_tax(self, subtotal: Decimal, gst_registered: bool, gst_rate: Decimal) -> TaxResult:
        if not gst_registered:
            return TaxResult(
                tax_rate=Decimal("0"),
                tax_amount=Decimal("0"),
                description="Not GST registered",
            )

        tax_amount = (subtotal * gst_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        return TaxResult(
            tax_rate=gst_rate,
            tax_amount=tax_amount,
            description=f"GST {gst_rate * 100}%",
        )

    def prorate_salary(self, monthly_salary: Decimal, days_worked: int, days_in_month: int) -> Decimal:
        """Calendar day proration (Singapore standard)."""
        if days_worked >= days_in_month:
            return monthly_salary
        prorated = monthly_salary * Decimal(days_worked) / Decimal(days_in_month)
        return prorated.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# Singleton
singapore = SingaporeJurisdiction()
