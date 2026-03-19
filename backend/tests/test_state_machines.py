"""
Unit tests for state machines — no DB required.
These test the transition logic directly without going through the API.
"""

import pytest

from app.state_machines import InvalidTransitionError, StateMachine
from app.state_machines.invoice import invoice_machine
from app.state_machines.payroll import payroll_machine
from app.state_machines.expense import expense_machine


# ---------------------------------------------------------------------------
# Invoice state machine
# ---------------------------------------------------------------------------

class TestInvoiceStateMachine:
    def test_draft_to_issued(self):
        result = invoice_machine.transition("draft", "issue")
        assert result == "issued"

    def test_issued_to_paid(self):
        result = invoice_machine.transition("issued", "mark_paid")
        assert result == "paid"

    def test_draft_to_cancelled(self):
        result = invoice_machine.transition("draft", "cancel")
        assert result == "cancelled"

    def test_issued_to_cancelled(self):
        result = invoice_machine.transition("issued", "cancel")
        assert result == "cancelled"

    def test_cannot_issue_cancelled(self):
        with pytest.raises(InvalidTransitionError) as exc_info:
            invoice_machine.transition("cancelled", "issue")
        assert "cancelled" in str(exc_info.value)

    def test_cannot_issue_paid(self):
        with pytest.raises(InvalidTransitionError):
            invoice_machine.transition("paid", "issue")

    def test_cannot_cancel_paid(self):
        with pytest.raises(InvalidTransitionError):
            invoice_machine.transition("paid", "cancel")

    def test_cannot_mark_paid_from_draft(self):
        with pytest.raises(InvalidTransitionError):
            invoice_machine.transition("draft", "mark_paid")

    def test_cannot_mark_paid_from_cancelled(self):
        with pytest.raises(InvalidTransitionError):
            invoice_machine.transition("cancelled", "mark_paid")

    def test_unknown_action_raises(self):
        with pytest.raises(InvalidTransitionError):
            invoice_machine.transition("draft", "nonexistent_action")

    def test_can_transition_true(self):
        assert invoice_machine.can_transition("draft", "issue") is True

    def test_can_transition_false(self):
        assert invoice_machine.can_transition("cancelled", "issue") is False

    def test_available_actions_draft(self):
        actions = invoice_machine.available_actions("draft")
        assert "issue" in actions
        assert "cancel" in actions
        assert "mark_paid" not in actions

    def test_available_actions_issued(self):
        actions = invoice_machine.available_actions("issued")
        assert "mark_paid" in actions
        assert "cancel" in actions
        assert "issue" not in actions

    def test_available_actions_paid(self):
        actions = invoice_machine.available_actions("paid")
        assert actions == []

    def test_available_actions_cancelled(self):
        actions = invoice_machine.available_actions("cancelled")
        assert actions == []


# ---------------------------------------------------------------------------
# Payroll state machine
# ---------------------------------------------------------------------------

class TestPayrollStateMachine:
    def test_draft_to_reviewed(self):
        result = payroll_machine.transition("draft", "review")
        assert result == "reviewed"

    def test_reviewed_to_finalized(self):
        result = payroll_machine.transition("reviewed", "finalize")
        assert result == "finalized"

    def test_finalized_to_paid(self):
        result = payroll_machine.transition("finalized", "mark_paid")
        assert result == "paid"

    def test_cannot_finalize_from_draft(self):
        with pytest.raises(InvalidTransitionError):
            payroll_machine.transition("draft", "finalize")

    def test_cannot_mark_paid_from_reviewed(self):
        with pytest.raises(InvalidTransitionError):
            payroll_machine.transition("reviewed", "mark_paid")

    def test_cannot_mark_paid_from_draft(self):
        with pytest.raises(InvalidTransitionError):
            payroll_machine.transition("draft", "mark_paid")

    def test_cannot_review_finalized(self):
        with pytest.raises(InvalidTransitionError):
            payroll_machine.transition("finalized", "review")

    def test_cannot_review_paid(self):
        with pytest.raises(InvalidTransitionError):
            payroll_machine.transition("paid", "review")

    def test_error_message_contains_state_and_action(self):
        with pytest.raises(InvalidTransitionError) as exc_info:
            payroll_machine.transition("paid", "finalize")
        err = str(exc_info.value)
        assert "finalize" in err
        assert "paid" in err

    def test_can_transition_valid(self):
        assert payroll_machine.can_transition("draft", "review") is True

    def test_can_transition_invalid(self):
        assert payroll_machine.can_transition("draft", "finalize") is False

    def test_available_actions_draft(self):
        actions = payroll_machine.available_actions("draft")
        assert "review" in actions
        assert "finalize" not in actions

    def test_available_actions_reviewed(self):
        actions = payroll_machine.available_actions("reviewed")
        assert "finalize" in actions
        assert "review" not in actions
        assert "mark_paid" not in actions

    def test_available_actions_paid(self):
        assert payroll_machine.available_actions("paid") == []


# ---------------------------------------------------------------------------
# Expense state machine
# ---------------------------------------------------------------------------

class TestExpenseStateMachine:
    def test_draft_to_confirmed(self):
        result = expense_machine.transition("draft", "confirm")
        assert result == "confirmed"

    def test_confirmed_to_reimbursed(self):
        result = expense_machine.transition("confirmed", "reimburse")
        assert result == "reimbursed"

    def test_cannot_reimburse_from_draft(self):
        with pytest.raises(InvalidTransitionError):
            expense_machine.transition("draft", "reimburse")

    def test_cannot_confirm_reimbursed(self):
        with pytest.raises(InvalidTransitionError):
            expense_machine.transition("reimbursed", "confirm")

    def test_cannot_confirm_confirmed(self):
        with pytest.raises(InvalidTransitionError):
            expense_machine.transition("confirmed", "confirm")

    def test_can_transition_valid(self):
        assert expense_machine.can_transition("draft", "confirm") is True

    def test_can_transition_invalid(self):
        assert expense_machine.can_transition("draft", "reimburse") is False

    def test_available_actions_draft(self):
        actions = expense_machine.available_actions("draft")
        assert "confirm" in actions
        assert "reimburse" not in actions

    def test_available_actions_confirmed(self):
        actions = expense_machine.available_actions("confirmed")
        assert "reimburse" in actions
        assert "confirm" not in actions

    def test_available_actions_reimbursed(self):
        assert expense_machine.available_actions("reimbursed") == []


# ---------------------------------------------------------------------------
# Generic StateMachine
# ---------------------------------------------------------------------------

class TestStateMachineGeneric:
    def setup_method(self):
        self.machine = StateMachine(
            "widget",
            {
                "activate": {"idle": "active"},
                "deactivate": {"active": "idle"},
                "destroy": {"idle": "destroyed", "active": "destroyed"},
            },
        )

    def test_valid_transition(self):
        assert self.machine.transition("idle", "activate") == "active"

    def test_valid_transition_multiple_sources(self):
        assert self.machine.transition("active", "destroy") == "destroyed"
        assert self.machine.transition("idle", "destroy") == "destroyed"

    def test_invalid_state_for_action(self):
        with pytest.raises(InvalidTransitionError) as exc_info:
            self.machine.transition("destroyed", "activate")
        err = exc_info.value
        assert err.entity_type == "widget"
        assert err.current_state == "destroyed"
        assert err.action == "activate"

    def test_invalid_action(self):
        with pytest.raises(InvalidTransitionError):
            self.machine.transition("idle", "fly")

    def test_error_repr(self):
        err = InvalidTransitionError("foo", "bar", "baz")
        assert "foo" in str(err)
        assert "bar" in str(err)
        assert "baz" in str(err)
