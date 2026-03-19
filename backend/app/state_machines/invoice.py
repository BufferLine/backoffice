from app.state_machines import StateMachine

# States: draft, issued, paid, cancelled
invoice_machine = StateMachine(
    "invoice",
    {
        "issue": {"draft": "issued"},
        "mark_paid": {"issued": "paid"},
        "cancel": {"draft": "cancelled", "issued": "cancelled"},
    },
)
