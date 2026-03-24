# Unit Test Writing Guide

## Location & Structure

- All unit tests go in `backend/tests/unit/`
- File naming: `test_{module}.py` (e.g., `test_state_machines.py`)
- The `conftest.py` in this dir overrides the DB fixture — **no database needed**

## Conventions

### Class-based grouping
```python
class TestInvoiceStateMachine:
    def test_draft_to_issued(self):
        ...

    def test_cannot_issue_cancelled(self):
        ...
```

### Naming
- `test_{what_it_does}` — positive case
- `test_{what_fails}_when_{condition}` — negative case
- `test_{edge_case_description}` — edge case

### Imports
```python
# Direct imports from app modules
from app.state_machines import StateMachine, InvalidTransitionError
from app.jurisdiction.singapore import SingaporeJurisdiction
from decimal import Decimal
```

### Async tests (when mocking async methods)
```python
import pytest
from unittest.mock import AsyncMock, patch

class TestSomethingAsync:
    @pytest.mark.asyncio
    async def test_async_method(self):
        ...
```

### Sync tests (prefer when possible)
```python
class TestPureFunctions:
    def test_simple_case(self):
        result = my_function(input)
        assert result == expected
```

## What to Test

### DO test (pure logic, no DB):
- State machine transitions (valid + invalid)
- Jurisdiction calculations (CPF, SDL, GST, proration)
- Statement parsers (CSV → ParsedTransaction)
- PDF helpers (money formatting, TLV encoding)
- Schema validation (Pydantic models)
- Config validation
- File storage validation (MIME types, filename sanitization)
- Export formatters

### DO NOT test in unit tests:
- Database queries (that's integration tests)
- API endpoints with DB (that's `tests/test_*.py`)
- External API calls (mock them)

## Patterns

### Testing calculations with Decimal
```python
from decimal import Decimal

def test_sdl_calculation(self):
    result = jurisdiction.calculate_deductions(Decimal("5000"), "ep")
    sdl = next(d for d in result if d.deduction_type == "sdl")
    assert sdl.amount == Decimal("12.50")
```

### Testing state machine transitions
```python
from app.state_machines import StateMachine, InvalidTransitionError
import pytest

def test_valid_transition(self):
    assert machine.transition("draft", "issue") == "issued"

def test_invalid_transition(self):
    with pytest.raises(InvalidTransitionError):
        machine.transition("cancelled", "issue")
```

### Testing CSV parsers
```python
from io import BytesIO

def test_parse_csv(self):
    csv_data = b"date,amount,currency\n2026-01-15,100.00,SGD\n"
    result = parser.parse(BytesIO(csv_data))
    assert len(result) == 1
    assert result[0].amount == Decimal("100.00")
```

### Testing Pydantic validation
```python
import pytest

def test_rejects_invalid_input(self):
    with pytest.raises(Exception, match="some error"):
        MySchema(field="bad_value")
```

## Running

```bash
# All unit tests
python -m pytest backend/tests/unit/ -v

# With coverage
python -m pytest backend/tests/unit/ --cov=backend/app --cov-report=term-missing

# Single file
python -m pytest backend/tests/unit/test_state_machines.py -v
```
