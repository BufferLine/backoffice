"""Unit tests for Singapore jurisdiction calculations."""

import pytest
from decimal import Decimal

from app.jurisdiction import get_jurisdiction
from app.jurisdiction.singapore import SingaporeJurisdiction, singapore


class TestGetJurisdiction:
    def test_sg_returns_singapore_instance(self):
        result = get_jurisdiction("SG")
        assert isinstance(result, SingaporeJurisdiction)

    def test_sg_returns_singleton(self):
        assert get_jurisdiction("SG") is singapore

    def test_unknown_code_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown jurisdiction: XX"):
            get_jurisdiction("XX")

    def test_empty_code_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown jurisdiction"):
            get_jurisdiction("")

    def test_lowercase_sg_raises_value_error(self):
        with pytest.raises(ValueError, match="Unknown jurisdiction: sg"):
            get_jurisdiction("sg")


class TestSdlCalculation:
    """SDL rate is 0.25%, capped at $11.25 for salary <= $4,500."""

    def setup_method(self):
        self.jur = SingaporeJurisdiction()

    def _get_sdl(self, deductions):
        return next(d for d in deductions if d.deduction_type == "sdl")

    def test_sdl_below_threshold_under_cap(self):
        # $1000 * 0.0025 = $2.50, well under $11.25 cap
        deductions = self.jur.calculate_deductions(Decimal("1000"), "ep")
        sdl = self._get_sdl(deductions)
        assert sdl.amount == Decimal("2.50")

    def test_sdl_at_threshold_hits_cap(self):
        # $4500 * 0.0025 = $11.25 exactly at cap
        deductions = self.jur.calculate_deductions(Decimal("4500"), "ep")
        sdl = self._get_sdl(deductions)
        assert sdl.amount == Decimal("11.25")

    def test_sdl_just_below_threshold_capped(self):
        # $4000 * 0.0025 = $10.00, under cap — no clamp needed
        deductions = self.jur.calculate_deductions(Decimal("4000"), "ep")
        sdl = self._get_sdl(deductions)
        assert sdl.amount == Decimal("10.00")

    def test_sdl_above_threshold_no_cap(self):
        # $5000 * 0.0025 = $12.50, above threshold so no cap applies
        deductions = self.jur.calculate_deductions(Decimal("5000"), "ep")
        sdl = self._get_sdl(deductions)
        assert sdl.amount == Decimal("12.50")

    def test_sdl_well_above_threshold(self):
        # $10000 * 0.0025 = $25.00
        deductions = self.jur.calculate_deductions(Decimal("10000"), "ep")
        sdl = self._get_sdl(deductions)
        assert sdl.amount == Decimal("25.00")

    def test_sdl_very_high_salary(self):
        # $100000 * 0.0025 = $250.00
        deductions = self.jur.calculate_deductions(Decimal("100000"), "ep")
        sdl = self._get_sdl(deductions)
        assert sdl.amount == Decimal("250.00")

    def test_sdl_deduction_type(self):
        deductions = self.jur.calculate_deductions(Decimal("3000"), "ep")
        sdl = self._get_sdl(deductions)
        assert sdl.deduction_type == "sdl"

    def test_sdl_description(self):
        deductions = self.jur.calculate_deductions(Decimal("3000"), "ep")
        sdl = self._get_sdl(deductions)
        assert sdl.description == "Skills Development Levy"

    def test_sdl_rate_field(self):
        deductions = self.jur.calculate_deductions(Decimal("3000"), "ep")
        sdl = self._get_sdl(deductions)
        assert sdl.rate == Decimal("0.0025")

    def test_sdl_cap_amount_set_when_below_threshold(self):
        deductions = self.jur.calculate_deductions(Decimal("3000"), "ep")
        sdl = self._get_sdl(deductions)
        assert sdl.cap_amount == Decimal("11.25")

    def test_sdl_cap_amount_none_when_above_threshold(self):
        deductions = self.jur.calculate_deductions(Decimal("5000"), "ep")
        sdl = self._get_sdl(deductions)
        assert sdl.cap_amount is None

    def test_sdl_metadata_employer_cost(self):
        deductions = self.jur.calculate_deductions(Decimal("3000"), "ep")
        sdl = self._get_sdl(deductions)
        assert sdl.metadata["employer_cost"] is True
        assert sdl.metadata["jurisdiction"] == "SG"

    def test_sdl_present_for_all_work_pass_types(self):
        for wpt in ("citizen", "pr", "ep", "wp", "sp"):
            deductions = self.jur.calculate_deductions(Decimal("3000"), wpt)
            types = [d.deduction_type for d in deductions]
            assert "sdl" in types, f"SDL missing for work_pass_type={wpt!r}"

    def test_sdl_rounding(self):
        # $1 * 0.0025 = $0.0025, rounds to $0.00 (ROUND_HALF_UP)
        deductions = self.jur.calculate_deductions(Decimal("1"), "ep")
        sdl = self._get_sdl(deductions)
        assert sdl.amount == Decimal("0.00")

    def test_sdl_amount_is_decimal(self):
        deductions = self.jur.calculate_deductions(Decimal("3000"), "ep")
        sdl = self._get_sdl(deductions)
        assert isinstance(sdl.amount, Decimal)


class TestCpfCitizen:
    """CPF: employee 20%, employer 17% for citizen."""

    def setup_method(self):
        self.jur = SingaporeJurisdiction()

    def _get_deduction(self, deductions, dtype):
        return next(d for d in deductions if d.deduction_type == dtype)

    def test_cpf_employee_rate_citizen(self):
        deductions = self.jur.calculate_deductions(Decimal("3000"), "citizen")
        emp = self._get_deduction(deductions, "cpf_employee")
        # $3000 * 0.20 = $600.00
        assert emp.amount == Decimal("600.00")

    def test_cpf_employer_rate_citizen(self):
        deductions = self.jur.calculate_deductions(Decimal("3000"), "citizen")
        er = self._get_deduction(deductions, "cpf_employer")
        # $3000 * 0.17 = $510.00
        assert er.amount == Decimal("510.00")

    def test_cpf_employee_description(self):
        deductions = self.jur.calculate_deductions(Decimal("3000"), "citizen")
        emp = self._get_deduction(deductions, "cpf_employee")
        assert emp.description == "CPF Employee Contribution"

    def test_cpf_employer_description(self):
        deductions = self.jur.calculate_deductions(Decimal("3000"), "citizen")
        er = self._get_deduction(deductions, "cpf_employer")
        assert er.description == "CPF Employer Contribution"

    def test_cpf_employee_rate_field(self):
        deductions = self.jur.calculate_deductions(Decimal("3000"), "citizen")
        emp = self._get_deduction(deductions, "cpf_employee")
        assert emp.rate == Decimal("0.20")

    def test_cpf_employer_rate_field(self):
        deductions = self.jur.calculate_deductions(Decimal("3000"), "citizen")
        er = self._get_deduction(deductions, "cpf_employer")
        assert er.rate == Decimal("0.17")

    def test_cpf_employer_metadata_employer_cost(self):
        deductions = self.jur.calculate_deductions(Decimal("3000"), "citizen")
        er = self._get_deduction(deductions, "cpf_employer")
        assert er.metadata["employer_cost"] is True

    def test_citizen_has_three_deductions(self):
        # SDL + CPF employee + CPF employer
        deductions = self.jur.calculate_deductions(Decimal("3000"), "citizen")
        assert len(deductions) == 3

    def test_cpf_amounts_are_decimal(self):
        deductions = self.jur.calculate_deductions(Decimal("3000"), "citizen")
        emp = self._get_deduction(deductions, "cpf_employee")
        er = self._get_deduction(deductions, "cpf_employer")
        assert isinstance(emp.amount, Decimal)
        assert isinstance(er.amount, Decimal)

    def test_cpf_citizen_high_salary(self):
        deductions = self.jur.calculate_deductions(Decimal("8000"), "citizen")
        emp = self._get_deduction(deductions, "cpf_employee")
        er = self._get_deduction(deductions, "cpf_employer")
        assert emp.amount == Decimal("1600.00")
        assert er.amount == Decimal("1360.00")


class TestCpfPr:
    """CPF for permanent residents uses same rates as citizen."""

    def setup_method(self):
        self.jur = SingaporeJurisdiction()

    def _get_deduction(self, deductions, dtype):
        return next(d for d in deductions if d.deduction_type == dtype)

    def test_cpf_employee_rate_pr(self):
        deductions = self.jur.calculate_deductions(Decimal("3000"), "pr")
        emp = self._get_deduction(deductions, "cpf_employee")
        assert emp.amount == Decimal("600.00")

    def test_cpf_employer_rate_pr(self):
        deductions = self.jur.calculate_deductions(Decimal("3000"), "pr")
        er = self._get_deduction(deductions, "cpf_employer")
        assert er.amount == Decimal("510.00")

    def test_pr_has_three_deductions(self):
        deductions = self.jur.calculate_deductions(Decimal("3000"), "pr")
        assert len(deductions) == 3

    def test_pr_cpf_matches_citizen_cpf(self):
        citizen = self.jur.calculate_deductions(Decimal("5000"), "citizen")
        pr = self.jur.calculate_deductions(Decimal("5000"), "pr")
        citizen_emp = next(d for d in citizen if d.deduction_type == "cpf_employee")
        pr_emp = next(d for d in pr if d.deduction_type == "cpf_employee")
        assert citizen_emp.amount == pr_emp.amount


class TestNoCpfForWorkPass:
    """Work pass types other than citizen/pr do not get CPF."""

    def setup_method(self):
        self.jur = SingaporeJurisdiction()

    def test_no_cpf_for_ep(self):
        deductions = self.jur.calculate_deductions(Decimal("5000"), "ep")
        types = [d.deduction_type for d in deductions]
        assert "cpf_employee" not in types
        assert "cpf_employer" not in types

    def test_no_cpf_for_wp(self):
        deductions = self.jur.calculate_deductions(Decimal("2000"), "wp")
        types = [d.deduction_type for d in deductions]
        assert "cpf_employee" not in types
        assert "cpf_employer" not in types

    def test_no_cpf_for_sp(self):
        deductions = self.jur.calculate_deductions(Decimal("3000"), "sp")
        types = [d.deduction_type for d in deductions]
        assert "cpf_employee" not in types
        assert "cpf_employer" not in types

    def test_ep_has_only_sdl(self):
        deductions = self.jur.calculate_deductions(Decimal("5000"), "ep")
        assert len(deductions) == 1
        assert deductions[0].deduction_type == "sdl"

    def test_wp_has_only_sdl(self):
        deductions = self.jur.calculate_deductions(Decimal("2000"), "wp")
        assert len(deductions) == 1
        assert deductions[0].deduction_type == "sdl"


class TestGstExclusive:
    """GST exclusive: tax = subtotal × rate."""

    def setup_method(self):
        self.jur = SingaporeJurisdiction()
        self.gst_rate = Decimal("0.09")  # 9% GST

    def test_basic_exclusive_gst(self):
        result = self.jur.calculate_invoice_tax(
            subtotal=Decimal("1000"),
            gst_registered=True,
            gst_rate=self.gst_rate,
            tax_inclusive=False,
        )
        assert result.tax_amount == Decimal("90.00")

    def test_exclusive_gst_rate_stored(self):
        result = self.jur.calculate_invoice_tax(
            subtotal=Decimal("1000"),
            gst_registered=True,
            gst_rate=self.gst_rate,
        )
        assert result.tax_rate == self.gst_rate

    def test_exclusive_not_inclusive_flag(self):
        result = self.jur.calculate_invoice_tax(
            subtotal=Decimal("1000"),
            gst_registered=True,
            gst_rate=self.gst_rate,
        )
        assert result.is_inclusive is False

    def test_exclusive_pre_tax_amount_is_none(self):
        result = self.jur.calculate_invoice_tax(
            subtotal=Decimal("1000"),
            gst_registered=True,
            gst_rate=self.gst_rate,
        )
        assert result.pre_tax_amount is None

    def test_exclusive_gst_rounding(self):
        # $333.33 * 0.09 = $29.9997, rounds to $30.00
        result = self.jur.calculate_invoice_tax(
            subtotal=Decimal("333.33"),
            gst_registered=True,
            gst_rate=self.gst_rate,
        )
        assert result.tax_amount == Decimal("30.00")

    def test_exclusive_zero_subtotal(self):
        result = self.jur.calculate_invoice_tax(
            subtotal=Decimal("0"),
            gst_registered=True,
            gst_rate=self.gst_rate,
        )
        assert result.tax_amount == Decimal("0.00")

    def test_exclusive_tax_amount_is_decimal(self):
        result = self.jur.calculate_invoice_tax(
            subtotal=Decimal("500"),
            gst_registered=True,
            gst_rate=self.gst_rate,
        )
        assert isinstance(result.tax_amount, Decimal)

    def test_exclusive_description_contains_rate(self):
        result = self.jur.calculate_invoice_tax(
            subtotal=Decimal("1000"),
            gst_registered=True,
            gst_rate=self.gst_rate,
        )
        assert "9" in result.description
        assert "GST" in result.description

    def test_exclusive_different_rate(self):
        # 8% rate
        result = self.jur.calculate_invoice_tax(
            subtotal=Decimal("1000"),
            gst_registered=True,
            gst_rate=Decimal("0.08"),
        )
        assert result.tax_amount == Decimal("80.00")


class TestGstInclusive:
    """GST inclusive: tax = subtotal × rate / (1 + rate)."""

    def setup_method(self):
        self.jur = SingaporeJurisdiction()
        self.gst_rate = Decimal("0.09")

    def test_basic_inclusive_gst(self):
        # $1090 inclusive at 9%: tax = 1090 * 0.09 / 1.09 = $90.00
        result = self.jur.calculate_invoice_tax(
            subtotal=Decimal("1090"),
            gst_registered=True,
            gst_rate=self.gst_rate,
            tax_inclusive=True,
        )
        assert result.tax_amount == Decimal("90.00")

    def test_inclusive_flag_set(self):
        result = self.jur.calculate_invoice_tax(
            subtotal=Decimal("1090"),
            gst_registered=True,
            gst_rate=self.gst_rate,
            tax_inclusive=True,
        )
        assert result.is_inclusive is True

    def test_inclusive_pre_tax_amount(self):
        # $1090 inclusive: pre-tax = 1090 - 90 = $1000
        result = self.jur.calculate_invoice_tax(
            subtotal=Decimal("1090"),
            gst_registered=True,
            gst_rate=self.gst_rate,
            tax_inclusive=True,
        )
        assert result.pre_tax_amount == Decimal("1000.00")

    def test_inclusive_rate_stored(self):
        result = self.jur.calculate_invoice_tax(
            subtotal=Decimal("1090"),
            gst_registered=True,
            gst_rate=self.gst_rate,
            tax_inclusive=True,
        )
        assert result.tax_rate == self.gst_rate

    def test_inclusive_description_contains_inclusive(self):
        result = self.jur.calculate_invoice_tax(
            subtotal=Decimal("1090"),
            gst_registered=True,
            gst_rate=self.gst_rate,
            tax_inclusive=True,
        )
        assert "inclusive" in result.description.lower()

    def test_inclusive_rounding(self):
        # $100 inclusive at 9%: tax = 100 * 0.09 / 1.09 = 8.2568... rounds to $8.26
        result = self.jur.calculate_invoice_tax(
            subtotal=Decimal("100"),
            gst_registered=True,
            gst_rate=self.gst_rate,
            tax_inclusive=True,
        )
        assert result.tax_amount == Decimal("8.26")

    def test_inclusive_pre_tax_plus_tax_equals_subtotal(self):
        result = self.jur.calculate_invoice_tax(
            subtotal=Decimal("500"),
            gst_registered=True,
            gst_rate=self.gst_rate,
            tax_inclusive=True,
        )
        # pre_tax_amount + tax_amount should equal subtotal (within rounding)
        assert result.pre_tax_amount + result.tax_amount == Decimal("500")

    def test_inclusive_tax_amount_is_decimal(self):
        result = self.jur.calculate_invoice_tax(
            subtotal=Decimal("1090"),
            gst_registered=True,
            gst_rate=self.gst_rate,
            tax_inclusive=True,
        )
        assert isinstance(result.tax_amount, Decimal)


class TestGstNotRegistered:
    """When not GST registered, tax should be zero."""

    def setup_method(self):
        self.jur = SingaporeJurisdiction()

    def test_zero_tax_when_not_registered(self):
        result = self.jur.calculate_invoice_tax(
            subtotal=Decimal("1000"),
            gst_registered=False,
            gst_rate=Decimal("0.09"),
        )
        assert result.tax_amount == Decimal("0")

    def test_zero_rate_when_not_registered(self):
        result = self.jur.calculate_invoice_tax(
            subtotal=Decimal("1000"),
            gst_registered=False,
            gst_rate=Decimal("0.09"),
        )
        assert result.tax_rate == Decimal("0")

    def test_description_when_not_registered(self):
        result = self.jur.calculate_invoice_tax(
            subtotal=Decimal("1000"),
            gst_registered=False,
            gst_rate=Decimal("0.09"),
        )
        assert "not" in result.description.lower() or "registered" in result.description.lower()

    def test_not_registered_ignores_inclusive_flag(self):
        result = self.jur.calculate_invoice_tax(
            subtotal=Decimal("1000"),
            gst_registered=False,
            gst_rate=Decimal("0.09"),
            tax_inclusive=True,
        )
        assert result.tax_amount == Decimal("0")

    def test_not_registered_zero_subtotal(self):
        result = self.jur.calculate_invoice_tax(
            subtotal=Decimal("0"),
            gst_registered=False,
            gst_rate=Decimal("0.09"),
        )
        assert result.tax_amount == Decimal("0")


class TestSalaryProration:
    """Prorate salary by calendar days (Singapore standard)."""

    def setup_method(self):
        self.jur = SingaporeJurisdiction()

    def test_full_month_returns_full_salary(self):
        result = self.jur.prorate_salary(
            monthly_salary=Decimal("3000"),
            days_worked=31,
            days_in_month=31,
        )
        assert result == Decimal("3000")

    def test_full_month_28_days(self):
        result = self.jur.prorate_salary(
            monthly_salary=Decimal("3000"),
            days_worked=28,
            days_in_month=28,
        )
        assert result == Decimal("3000")

    def test_half_month_30_days(self):
        # 15/30 = 0.5 × $3000 = $1500.00
        result = self.jur.prorate_salary(
            monthly_salary=Decimal("3000"),
            days_worked=15,
            days_in_month=30,
        )
        assert result == Decimal("1500.00")

    def test_partial_month_rounding(self):
        # 10/31 × $3000 = $967.74193... rounds to $967.74
        result = self.jur.prorate_salary(
            monthly_salary=Decimal("3000"),
            days_worked=10,
            days_in_month=31,
        )
        assert result == Decimal("967.74")

    def test_one_day_of_31(self):
        # 1/31 × $3000 = $96.77419... rounds to $96.77
        result = self.jur.prorate_salary(
            monthly_salary=Decimal("3000"),
            days_worked=1,
            days_in_month=31,
        )
        assert result == Decimal("96.77")

    def test_zero_days_returns_zero(self):
        result = self.jur.prorate_salary(
            monthly_salary=Decimal("3000"),
            days_worked=0,
            days_in_month=31,
        )
        assert result == Decimal("0.00")

    def test_days_worked_exceeds_days_in_month_returns_full(self):
        # days_worked >= days_in_month → full salary (no proration)
        result = self.jur.prorate_salary(
            monthly_salary=Decimal("3000"),
            days_worked=35,
            days_in_month=31,
        )
        assert result == Decimal("3000")

    def test_result_is_decimal(self):
        result = self.jur.prorate_salary(
            monthly_salary=Decimal("3000"),
            days_worked=15,
            days_in_month=30,
        )
        assert isinstance(result, Decimal)

    def test_proration_two_decimal_places(self):
        result = self.jur.prorate_salary(
            monthly_salary=Decimal("5000"),
            days_worked=20,
            days_in_month=31,
        )
        # 20/31 × 5000 = 3225.8064... rounds to 3225.81
        assert result == Decimal("3225.81")

    def test_proration_february(self):
        # 14/28 × $4000 = $2000.00
        result = self.jur.prorate_salary(
            monthly_salary=Decimal("4000"),
            days_worked=14,
            days_in_month=28,
        )
        assert result == Decimal("2000.00")

    def test_days_worked_equals_days_in_month_exactly(self):
        result = self.jur.prorate_salary(
            monthly_salary=Decimal("5000"),
            days_worked=30,
            days_in_month=30,
        )
        assert result == Decimal("5000")
