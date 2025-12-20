# GitHub Copilot Instructions for ActronAirAPI

## Project Overview
ActronAirAPI is a Python library providing a robust, type-safe interface to Actron Air HVAC systems. This library is designed for integration with Home Assistant and other automation platforms, emphasizing reliability, maintainability, and clean architecture.

## Core Development Principles

### 1. Code Quality Standards
- **Type Safety**: Use type hints everywhere (`typing` module, Pydantic models)
- **Error Handling**: Follow fail-fast for critical operations, graceful degradation for non-critical
- **Documentation**: All public APIs must have Google-style docstrings
- **Testing**: Write tests for new features and bug fixes

### 2. Pre-commit Compliance
**CRITICAL**: All code must pass pre-commit checks before committing. Run:
```bash
pre-commit run --all-files
```

Our pre-commit pipeline includes:
- **ruff**: Linting and auto-formatting (E, F, W, I rules)
- **mypy**: Type checking with strict mode
- **pydocstyle**: Google convention docstrings
- **File hygiene**: trailing whitespace, line endings, YAML/TOML validation

### 3. Exception Handling Philosophy

**Fail Fast (raise exceptions):**
- Authentication failures (`ActronAirAuthError`)
- API communication errors (`ActronAirAPIError`)
- Control command failures (turn on/off, mode changes)
- Missing required configuration
- Invalid API responses that break core functionality

**Graceful Degradation (log and continue):**
- Observer callback failures (don't break status updates)
- Peripheral sensor parsing errors (log warning, continue with None)
- Invalid sensor data (temperature/humidity out of range)
- Missing optional data fields
- Non-critical nested component parsing

**Example Pattern:**
```python
# Critical operation - fail fast (no try-except needed, let exceptions propagate)
async def send_command(self, command: Dict[str, Any]) -> Dict[str, Any]:
    """Send command - any error should fail fast and propagate to caller."""
    endpoint = self._get_system_link(serial_number, "commands")
    if not endpoint:
        raise ActronAirAPIError(f"No commands link found")
    return await self._make_request("post", endpoint, json_data=command)

# Non-critical operation - graceful degradation
def _process_peripherals(self) -> None:
    """Process peripherals - skip invalid ones but continue with others."""
    for peripheral_data in peripherals_data:
        try:
            peripheral = ActronAirPeripheral.from_peripheral_data(peripheral_data)
            self.peripherals.append(peripheral)
        except (ValidationError, ValueError, TypeError) as e:
            # Catch specific exceptions for data parsing issues
            _LOGGER.warning("Failed to parse peripheral: %s", e)
            # Continue processing other peripherals - one bad peripheral shouldn't break all
```

### 4. Code Architecture

**Project Structure:**
```
src/actron_neo_api/
├── __init__.py          # Public API exports
├── actron.py            # Main API client
├── oauth.py             # OAuth2 authentication
├── state.py             # State management
├── const.py             # Constants
├── exceptions.py        # Custom exceptions
└── models/
    ├── __init__.py      # Model exports
    ├── base.py          # Base model functionality
    ├── status.py        # Status models
    ├── system.py        # System models
    ├── settings.py      # Settings models
    ├── zone.py          # Zone models
    └── schemas.py       # API schemas
```

**Design Patterns:**
- **Pydantic Models**: All API data structures use Pydantic for validation
- **Type Safety**: Full type hints with mypy compliance
- **Async/Await**: All I/O operations are async
- **Object-Oriented API**: Models have methods for direct control
- **State Manager**: Centralized state tracking with observer pattern

### 5. Common Patterns and Best Practices

#### Pydantic Models
```python
from pydantic import BaseModel, Field
from typing import Optional

class ActronAirZone(BaseModel):
    """Zone with sensor data."""

    zone_id: int = Field(..., alias="ZoneNumber")
    temperature: Optional[float] = Field(None, alias="LiveTemp_oC")
    is_enabled: bool = Field(False, alias="EnabledZone")

    class Config:
        populate_by_name = True  # Allow both alias and field name
```

#### Logging
```python
import logging

_LOGGER = logging.getLogger(__name__)

# Use appropriate log levels:
_LOGGER.debug("Detailed debug info")      # Development/troubleshooting
_LOGGER.info("Normal operations")          # Key state changes
_LOGGER.warning("Recoverable issues")      # Missing optional data
_LOGGER.error("Serious problems", exc_info=True)  # Failures requiring attention
```

#### Async API Methods
```python
async def get_status(self, serial_number: str) -> Dict[str, Any]:
    """Get AC status.

    Args:
        serial_number: System serial number

    Returns:
        Status data dictionary

    Raises:
        ActronAirAuthError: Authentication failed
        ActronAirAPIError: API request failed
    """
    await self._ensure_initialized()
    return await self._make_request("get", f"systems/{serial_number}/status")
```

#### Property Accessors with Error Handling
```python
@property
def min_temp(self) -> float:
    """Minimum settable temperature."""
    try:
        return self.last_known_state["NV_Limits"]["UserSetpoint_oC"]["setCool_Min"]
    except (KeyError, TypeError):
        return 16.0  # Sensible default
```

### 6. Testing Requirements

When adding new features:
1. Write unit tests in `tests/`
2. Test both success and failure paths
3. Mock external API calls with `aiohttp`
4. Verify exception handling behavior

### 7. Documentation Standards

**Module Docstrings:**
```python
"""Brief module description.

Longer description explaining the module's purpose, key classes,
and how it fits into the overall architecture.
"""
```

**Function/Method Docstrings:**
```python
def method(self, param: str, optional: bool = False) -> Dict[str, Any]:
    """Brief description.

    Longer explanation if needed, describing behavior,
    side effects, and any important details.

    Args:
        param: Description of param
        optional: Description with default behavior

    Returns:
        Description of return value

    Raises:
        ValueError: When param is invalid
        ActronAirAPIError: When API call fails

    Example:
        >>> api.method("test", optional=True)
        {'result': 'success'}
    """
```

### 8. Common Gotchas and Anti-Patterns

**❌ DON'T:**
- Catch exceptions without re-raising or logging with `exc_info=True`
- Access dictionary keys without handling `KeyError`
- Use bare `except:` clauses
- Import modules after code execution (fails E402)
- Leave TODO comments without GitHub issues
- Commit code that fails pre-commit checks

**✅ DO:**
- Use `dict.get()` with defaults for optional data
- Provide sensible defaults for missing optional configuration
- Add type hints to all function signatures
- Write docstrings for all public APIs
- Log errors with context before re-raising
- Use `_LOGGER` instead of `print()` statements
- Run `pre-commit run --all-files` before committing

### 9. Version Compatibility

- **Python**: >= 3.8 (maintain backward compatibility)
- **Dependencies**:
  - `aiohttp >= 3.8.0`: Async HTTP client
  - `pydantic >= 2.0.0`: Data validation
- Test against multiple Python versions (3.8, 3.9, 3.10, 3.11, 3.12)

### 10. API Client Best Practices

**Session Management:**
```python
async def __aenter__(self):
    """Context manager entry."""
    return self

async def __aexit__(self, exc_type, exc_val, exc_tb):
    """Context manager exit - clean up resources."""
    await self.close()
```

**Token Management:**
- Proactively refresh tokens 15 minutes before expiry
- Handle 401 responses with automatic token refresh and retry
- Track which platform issued tokens (Neo vs Que)

**State Updates:**
- Use state manager for centralized state tracking
- Support observer pattern for state change notifications
- Parse nested components lazily to improve performance

### 11. Making Changes Checklist

Before proposing any code changes:
1. ✅ Understand the fail-fast vs graceful degradation philosophy
2. ✅ Check if similar patterns exist in the codebase
3. ✅ Add appropriate type hints
4. ✅ Write Google-style docstrings
5. ✅ Add error handling following project patterns
6. ✅ Run `pre-commit run --all-files`
7. ✅ Test with `pytest` if tests exist
8. ✅ Update documentation if changing public API

### 12. Contact and Resources

- **Repository**: https://github.com/kclif9/actronneoapi
- **Issues**: Report bugs and feature requests on GitHub
- **Home Assistant Integration**: Designed for HA compatibility

---

## Development Workflow

### Virtual Environment
**CRITICAL**: Always activate the virtual environment before running any commands:
```bash
source .venv/bin/activate
```

### Before Completing Any Work
**MANDATORY**: Before considering any work complete, you MUST:
1. ✅ Activate the virtual environment (`source .venv/bin/activate`)
2. ✅ Run the full test suite with coverage (`pytest --cov=src --cov-report=term-missing`)
3. ✅ Verify test coverage has not regressed
4. ✅ Run all pre-commit checks (`pre-commit run --all-files`)
5. ✅ Ensure ALL tests pass and ALL checks pass

**Do NOT claim work is complete until all tests pass, all checks pass, and coverage is maintained.**

---

## Quick Reference Commands

```bash
# Activate virtual environment (ALWAYS DO THIS FIRST)
source .venv/bin/activate

# Install development dependencies
pip install -e ".[dev]"

# Run ALL tests (required before completing work)
pytest

# Run tests with coverage report (required before completing work)
pytest --cov=src --cov-report=term-missing

# Run pre-commit checks (required before completing work)
pre-commit run --all-files

# Install pre-commit hooks
pre-commit install

# Type checking
mypy src/

# Format code
ruff format .

# Lint and auto-fix
ruff check --fix .
```

---

## When Working on This Project

**Always consider:**
1. Will this change break existing integrations (Home Assistant)?
2. Does this follow the project's exception handling philosophy?
3. Will this pass all pre-commit checks?
4. Is the code type-safe and well-documented?
5. Does this maintain backward compatibility?

**Completion Checklist (MANDATORY):**
1. ✅ Virtual environment activated
2. ✅ All tests pass (`pytest` returns 0 exit code)
3. ✅ Test coverage verified and not regressed (`pytest --cov=src --cov-report=term-missing`)
4. ✅ All pre-commit checks pass
5. ✅ No new warnings or errors introduced

**Remember**: This library is used in production environments controlling real HVAC systems. Reliability and correctness are paramount. When in doubt, fail fast and provide clear error messages.
