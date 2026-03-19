from app.state_machines import StateMachine

# States: draft, reviewed, finalized, paid
payroll_machine = StateMachine(
    "payroll",
    {
        "review": {"draft": "reviewed"},
        "finalize": {"reviewed": "finalized"},
        "mark_paid": {"finalized": "paid"},
    },
)
