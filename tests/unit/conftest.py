"""Test configuration and fixtures.

This file provides fixtures for the test suite, including:
- Autouse fixture to prevent real event-loop from being driven via asyncio.run
- Environment variable reset to ensure clean test state
"""

from unittest.mock import AsyncMock

import pytest

from external_dns_technitium_webhook.technitium_client import TechnitiumClient


@pytest.fixture(autouse=True)
def _disable_asyncio_run(monkeypatch):
    """Replace asyncio.run in the main module with a harmless stub.

    This prevents accidental server startup when tests import or call
    `external_dns_technitium_webhook.main.main()` without explicitly
    mocking `asyncio.run`.
    """
    try:
        import external_dns_technitium_webhook.main as main_mod

        # If the module exposes asyncio, patch its run function. Use a lambda
        # that returns None to mimic the behavior of a completed call.
        if hasattr(main_mod, "asyncio"):
            monkeypatch.setattr(main_mod.asyncio, "run", lambda coro: None)
    except Exception:
        # If import fails for some reason, don't block tests; they will fail
        # normally and provide more context.
        pass

    yield


@pytest.fixture(autouse=True)
def reset_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reset environment variables for each test."""
    # Clear any existing environment variables that might interfere
    monkeypatch.delenv("TECHNITIUM_URL", raising=False)
    monkeypatch.delenv("TECHNITIUM_USERNAME", raising=False)
    monkeypatch.delenv("TECHNITIUM_PASSWORD", raising=False)
    monkeypatch.delenv("ZONE", raising=False)
    monkeypatch.delenv("DOMAIN_FILTERS", raising=False)


@pytest.fixture(autouse=True)
def mock_technitium_client(monkeypatch):
    """Mock the Technitium client."""
    mock_client = AsyncMock(spec=TechnitiumClient)
    mock_client.login.return_value = None
    mock_client.get_records.return_value = []
    mock_client.add_record.return_value = None
    mock_client.delete_record.return_value = None

    monkeypatch.setattr(
        "external_dns_technitium_webhook.technitium_client.TechnitiumClient",
        lambda *args, **kwargs: mock_client,
    )
