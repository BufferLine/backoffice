import pytest

from app.state_machines import InvalidTransitionError, StateMachine
from app.state_machines.expense import expense_machine
from app.state_machines.invoice import invoice_machine
from app.state_machines.payroll import payroll_machine


class TestInvalidTransitionError:
    def test_stores_entity_type(self):
        err = InvalidTransitionError("invoice", "draft", "mark_paid")
        assert err.entity_type == "invoice"

    def test_stores_current_state(self):
        err = InvalidTransitionError("invoice", "draft", "mark_paid")
        assert err.current_state == "draft"

    def test_stores_action(self):
        err = InvalidTransitionError("invoice", "draft", "mark_paid")
        assert err.action == "mark_paid"

    def test_message_includes_action_entity_state(self):
        err = InvalidTransitionError("invoice", "draft", "mark_paid")
        msg = str(err)
        assert "mark_paid" in msg
        assert "invoice" in msg
        assert "draft" in msg

    def test_is_exception_subclass(self):
        err = InvalidTransitionError("invoice", "draft", "mark_paid")
        assert isinstance(err, Exception)


class TestStateMachineCore:
    def setup_method(self):
        self.machine = StateMachine(
            "widget",
            {
                "activate": {"idle": "active"},
                "deactivate": {"active": "idle"},
                "archive": {"idle": "archived", "active": "archived"},
            },
        )

    def test_valid_transition_returns_new_state(self):
        assert self.machine.transition("idle", "activate") == "active"

    def test_valid_transition_multiple_sources(self):
        assert self.machine.transition("idle", "archive") == "archived"
        assert self.machine.transition("active", "archive") == "archived"

    def test_invalid_action_raises_error(self):
        with pytest.raises(InvalidTransitionError) as exc_info:
            self.machine.transition("idle", "nonexistent_action")
        assert exc_info.value.entity_type == "widget"
        assert exc_info.value.current_state == "idle"
        assert exc_info.value.action == "nonexistent_action"

    def test_valid_action_wrong_state_raises_error(self):
        with pytest.raises(InvalidTransitionError) as exc_info:
            self.machine.transition("archived", "activate")
        assert exc_info.value.entity_type == "widget"
        assert exc_info.value.current_state == "archived"
        assert exc_info.value.action == "activate"

    def test_can_transition_returns_true_for_valid(self):
        assert self.machine.can_transition("idle", "activate") is True

    def test_can_transition_returns_false_for_invalid_action(self):
        assert self.machine.can_transition("idle", "nonexistent_action") is False

    def test_can_transition_returns_false_for_wrong_state(self):
        assert self.machine.can_transition("archived", "activate") is False

    def test_available_actions_returns_valid_actions_for_state(self):
        actions = self.machine.available_actions("idle")
        assert set(actions) == {"activate", "archive"}

    def test_available_actions_single_action_state(self):
        actions = self.machine.available_actions("active")
        assert set(actions) == {"deactivate", "archive"}

    def test_available_actions_terminal_state_returns_empty(self):
        actions = self.machine.available_actions("archived")
        assert actions == []

    def test_available_actions_unknown_state_returns_empty(self):
        actions = self.machine.available_actions("unknown_state")
        assert actions == []


class TestInvoiceStateMachine:
    # --- valid transitions ---

    def test_draft_to_issued_via_issue(self):
        assert invoice_machine.transition("draft", "issue") == "issued"

    def test_issued_to_paid_via_mark_paid(self):
        assert invoice_machine.transition("issued", "mark_paid") == "paid"

    def test_draft_to_cancelled_via_cancel(self):
        assert invoice_machine.transition("draft", "cancel") == "cancelled"

    def test_issued_to_cancelled_via_cancel(self):
        assert invoice_machine.transition("issued", "cancel") == "cancelled"

    # --- invalid transitions ---

    def test_cannot_mark_paid_from_draft(self):
        with pytest.raises(InvalidTransitionError) as exc_info:
            invoice_machine.transition("draft", "mark_paid")
        assert exc_info.value.entity_type == "invoice"
        assert exc_info.value.current_state == "draft"
        assert exc_info.value.action == "mark_paid"

    def test_cannot_issue_from_issued(self):
        with pytest.raises(InvalidTransitionError):
            invoice_machine.transition("issued", "issue")

    def test_cannot_issue_from_cancelled(self):
        with pytest.raises(InvalidTransitionError) as exc_info:
            invoice_machine.transition("cancelled", "issue")
        assert exc_info.value.current_state == "cancelled"

    def test_cannot_issue_from_paid(self):
        with pytest.raises(InvalidTransitionError):
            invoice_machine.transition("paid", "issue")

    def test_cannot_cancel_from_paid(self):
        with pytest.raises(InvalidTransitionError):
            invoice_machine.transition("paid", "cancel")

    def test_cannot_cancel_from_cancelled(self):
        with pytest.raises(InvalidTransitionError):
            invoice_machine.transition("cancelled", "cancel")

    def test_cannot_mark_paid_from_cancelled(self):
        with pytest.raises(InvalidTransitionError):
            invoice_machine.transition("cancelled", "mark_paid")

    def test_cannot_mark_paid_from_paid(self):
        with pytest.raises(InvalidTransitionError):
            invoice_machine.transition("paid", "mark_paid")

    def test_unknown_action_raises_error(self):
        with pytest.raises(InvalidTransitionError) as exc_info:
            invoice_machine.transition("draft", "approve")
        assert exc_info.value.action == "approve"

    def test_unknown_state_raises_error(self):
        with pytest.raises(InvalidTransitionError) as exc_info:
            invoice_machine.transition("pending", "issue")
        assert exc_info.value.current_state == "pending"

    # --- can_transition ---

    def test_can_transition_draft_issue_true(self):
        assert invoice_machine.can_transition("draft", "issue") is True

    def test_can_transition_issued_mark_paid_true(self):
        assert invoice_machine.can_transition("issued", "mark_paid") is True

    def test_can_transition_draft_cancel_true(self):
        assert invoice_machine.can_transition("draft", "cancel") is True

    def test_can_transition_issued_cancel_true(self):
        assert invoice_machine.can_transition("issued", "cancel") is True

    def test_can_transition_paid_cancel_false(self):
        assert invoice_machine.can_transition("paid", "cancel") is False

    def test_can_transition_cancelled_issue_false(self):
        assert invoice_machine.can_transition("cancelled", "issue") is False

    def test_can_transition_unknown_action_false(self):
        assert invoice_machine.can_transition("draft", "unknown") is False

    def test_can_transition_unknown_state_false(self):
        assert invoice_machine.can_transition("bogus", "issue") is False

    # --- available_actions ---

    def test_available_actions_draft(self):
        actions = invoice_machine.available_actions("draft")
        assert set(actions) == {"issue", "cancel"}

    def test_available_actions_issued(self):
        actions = invoice_machine.available_actions("issued")
        assert set(actions) == {"mark_paid", "cancel"}

    def test_available_actions_paid(self):
        actions = invoice_machine.available_actions("paid")
        assert actions == []

    def test_available_actions_cancelled(self):
        actions = invoice_machine.available_actions("cancelled")
        assert actions == []

    def test_available_actions_unknown_state(self):
        actions = invoice_machine.available_actions("nonexistent")
        assert actions == []


class TestPayrollStateMachine:
    # --- valid transitions ---

    def test_draft_to_reviewed_via_review(self):
        assert payroll_machine.transition("draft", "review") == "reviewed"

    def test_reviewed_to_finalized_via_finalize(self):
        assert payroll_machine.transition("reviewed", "finalize") == "finalized"

    def test_finalized_to_paid_via_mark_paid(self):
        assert payroll_machine.transition("finalized", "mark_paid") == "paid"

    # --- invalid transitions (skip steps) ---

    def test_cannot_finalize_from_draft(self):
        with pytest.raises(InvalidTransitionError) as exc_info:
            payroll_machine.transition("draft", "finalize")
        assert exc_info.value.entity_type == "payroll"
        assert exc_info.value.current_state == "draft"
        assert exc_info.value.action == "finalize"

    def test_cannot_mark_paid_from_draft(self):
        with pytest.raises(InvalidTransitionError) as exc_info:
            payroll_machine.transition("draft", "mark_paid")
        assert exc_info.value.current_state == "draft"
        assert exc_info.value.action == "mark_paid"

    def test_cannot_mark_paid_from_reviewed(self):
        with pytest.raises(InvalidTransitionError) as exc_info:
            payroll_machine.transition("reviewed", "mark_paid")
        assert exc_info.value.current_state == "reviewed"
        assert exc_info.value.action == "mark_paid"

    def test_cannot_review_from_reviewed(self):
        with pytest.raises(InvalidTransitionError) as exc_info:
            payroll_machine.transition("reviewed", "review")
        assert exc_info.value.current_state == "reviewed"
        assert exc_info.value.action == "review"

    def test_cannot_review_from_finalized(self):
        with pytest.raises(InvalidTransitionError):
            payroll_machine.transition("finalized", "review")

    def test_cannot_finalize_from_finalized(self):
        with pytest.raises(InvalidTransitionError) as exc_info:
            payroll_machine.transition("finalized", "finalize")
        assert exc_info.value.entity_type == "payroll"
        assert exc_info.value.current_state == "finalized"
        assert exc_info.value.action == "finalize"

    def test_cannot_review_from_paid(self):
        with pytest.raises(InvalidTransitionError):
            payroll_machine.transition("paid", "review")

    def test_cannot_finalize_from_paid(self):
        with pytest.raises(InvalidTransitionError):
            payroll_machine.transition("paid", "finalize")

    def test_cannot_mark_paid_from_paid(self):
        with pytest.raises(InvalidTransitionError):
            payroll_machine.transition("paid", "mark_paid")

    def test_unknown_action_raises_error(self):
        with pytest.raises(InvalidTransitionError) as exc_info:
            payroll_machine.transition("draft", "approve")
        assert exc_info.value.action == "approve"

    def test_unknown_state_raises_error(self):
        with pytest.raises(InvalidTransitionError) as exc_info:
            payroll_machine.transition("pending", "review")
        assert exc_info.value.current_state == "pending"

    # --- can_transition ---

    def test_can_transition_draft_review_true(self):
        assert payroll_machine.can_transition("draft", "review") is True

    def test_can_transition_reviewed_finalize_true(self):
        assert payroll_machine.can_transition("reviewed", "finalize") is True

    def test_can_transition_finalized_mark_paid_true(self):
        assert payroll_machine.can_transition("finalized", "mark_paid") is True

    def test_can_transition_draft_finalize_false(self):
        assert payroll_machine.can_transition("draft", "finalize") is False

    def test_can_transition_paid_review_false(self):
        assert payroll_machine.can_transition("paid", "review") is False

    def test_can_transition_unknown_action_false(self):
        assert payroll_machine.can_transition("draft", "unknown") is False

    def test_can_transition_unknown_state_false(self):
        assert payroll_machine.can_transition("bogus", "review") is False

    # --- available_actions ---

    def test_available_actions_draft(self):
        actions = payroll_machine.available_actions("draft")
        assert actions == ["review"]

    def test_available_actions_reviewed(self):
        actions = payroll_machine.available_actions("reviewed")
        assert actions == ["finalize"]

    def test_available_actions_finalized(self):
        actions = payroll_machine.available_actions("finalized")
        assert actions == ["mark_paid"]

    def test_available_actions_paid(self):
        actions = payroll_machine.available_actions("paid")
        assert actions == []

    def test_available_actions_unknown_state(self):
        actions = payroll_machine.available_actions("nonexistent")
        assert actions == []


class TestExpenseStateMachine:
    # --- valid transitions ---

    def test_draft_to_confirmed_via_confirm(self):
        assert expense_machine.transition("draft", "confirm") == "confirmed"

    def test_confirmed_to_reimbursed_via_reimburse(self):
        assert expense_machine.transition("confirmed", "reimburse") == "reimbursed"

    # --- invalid transitions ---

    def test_cannot_reimburse_from_draft(self):
        with pytest.raises(InvalidTransitionError) as exc_info:
            expense_machine.transition("draft", "reimburse")
        assert exc_info.value.entity_type == "expense"
        assert exc_info.value.current_state == "draft"
        assert exc_info.value.action == "reimburse"

    def test_cannot_confirm_from_confirmed(self):
        with pytest.raises(InvalidTransitionError):
            expense_machine.transition("confirmed", "confirm")

    def test_cannot_confirm_from_reimbursed(self):
        with pytest.raises(InvalidTransitionError):
            expense_machine.transition("reimbursed", "confirm")

    def test_cannot_reimburse_from_reimbursed(self):
        with pytest.raises(InvalidTransitionError):
            expense_machine.transition("reimbursed", "reimburse")

    def test_unknown_action_raises_error(self):
        with pytest.raises(InvalidTransitionError) as exc_info:
            expense_machine.transition("draft", "approve")
        assert exc_info.value.action == "approve"

    def test_unknown_state_raises_error(self):
        with pytest.raises(InvalidTransitionError) as exc_info:
            expense_machine.transition("pending", "confirm")
        assert exc_info.value.current_state == "pending"

    # --- can_transition ---

    def test_can_transition_draft_confirm_true(self):
        assert expense_machine.can_transition("draft", "confirm") is True

    def test_can_transition_confirmed_reimburse_true(self):
        assert expense_machine.can_transition("confirmed", "reimburse") is True

    def test_can_transition_draft_reimburse_false(self):
        assert expense_machine.can_transition("draft", "reimburse") is False

    def test_can_transition_reimbursed_confirm_false(self):
        assert expense_machine.can_transition("reimbursed", "confirm") is False

    def test_can_transition_unknown_action_false(self):
        assert expense_machine.can_transition("draft", "unknown") is False

    def test_can_transition_unknown_state_false(self):
        assert expense_machine.can_transition("bogus", "confirm") is False

    # --- available_actions ---

    def test_available_actions_draft(self):
        actions = expense_machine.available_actions("draft")
        assert actions == ["confirm"]

    def test_available_actions_confirmed(self):
        actions = expense_machine.available_actions("confirmed")
        assert actions == ["reimburse"]

    def test_available_actions_reimbursed(self):
        actions = expense_machine.available_actions("reimbursed")
        assert actions == []

    def test_available_actions_unknown_state(self):
        actions = expense_machine.available_actions("nonexistent")
        assert actions == []
