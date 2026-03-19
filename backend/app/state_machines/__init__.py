class InvalidTransitionError(Exception):
    def __init__(self, entity_type: str, current_state: str, action: str):
        self.entity_type = entity_type
        self.current_state = current_state
        self.action = action
        super().__init__(f"Cannot {action} {entity_type} in '{current_state}' state")


class StateMachine:
    """Generic state machine with transition validation."""

    def __init__(self, entity_type: str, transitions: dict[str, dict[str, str]]):
        """
        transitions: {action: {current_state: next_state}}
        Example: {"issue": {"draft": "issued"}, "cancel": {"draft": "cancelled", "issued": "cancelled"}}
        """
        self._entity_type = entity_type
        self._transitions = transitions

    def transition(self, current_state: str, action: str) -> str:
        """Returns new state or raises InvalidTransitionError."""
        action_transitions = self._transitions.get(action)
        if not action_transitions:
            raise InvalidTransitionError(self._entity_type, current_state, action)
        new_state = action_transitions.get(current_state)
        if new_state is None:
            raise InvalidTransitionError(self._entity_type, current_state, action)
        return new_state

    def can_transition(self, current_state: str, action: str) -> bool:
        try:
            self.transition(current_state, action)
            return True
        except InvalidTransitionError:
            return False

    def available_actions(self, current_state: str) -> list[str]:
        return [action for action, states in self._transitions.items() if current_state in states]
