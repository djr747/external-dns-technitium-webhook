"""Test configuration and fixtures."""

import pytest


@pytest.fixture(autouse=True)
def reset_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reset environment variables for each test."""
    # Clear any existing environment variables that might interfere
    monkeypatch.delenv("TECHNITIUM_URL", raising=False)
    monkeypatch.delenv("TECHNITIUM_USERNAME", raising=False)
    monkeypatch.delenv("TECHNITIUM_PASSWORD", raising=False)
    monkeypatch.delenv("ZONE", raising=False)
    monkeypatch.delenv("DOMAIN_FILTERS", raising=False)
