from app.state_machines import StateMachine

# States: draft, confirmed, reimbursed
expense_machine = StateMachine(
    "expense",
    {
        "confirm": {"draft": "confirmed"},
        "reimburse": {"confirmed": "reimbursed"},
    },
)
