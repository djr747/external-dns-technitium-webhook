"""Unit tests for AppState behavior."""

import asyncio

import pytest
from pytest_mock import MockerFixture

from external_dns_technitium_webhook.app_state import AppState
from external_dns_technitium_webhook.config import Config


@pytest.fixture
def config() -> Config:
    """Return a minimal configuration for AppState tests."""
    return Config(
        technitium_url="http://primary:5380",
        technitium_username="admin",
        technitium_password="password",
        zone="example.com",
    )


@pytest.mark.asyncio
async def test_set_active_endpoint_no_change(config: Config) -> None:
    """Calling set_active_endpoint with the same URL should reuse the client."""

    state = AppState(config)
    try:
        original_client = state.client
        await state.set_active_endpoint(config.technitium_url)
        assert state.client is original_client
        assert state.active_endpoint == original_client.base_url
    finally:
        await state.close()


@pytest.mark.asyncio
async def test_set_active_endpoint_switches_client(config: Config, mocker: MockerFixture) -> None:
    """Switching to a new endpoint should replace the client and close the old one."""

    state = AppState(config)
    try:
        shutdown_mock = mocker.AsyncMock()
        state.client.close = shutdown_mock  # type: ignore[assignment]

        await state.set_active_endpoint("http://failover:5380")

        assert state.active_endpoint == "http://failover:5380"
        assert state.client.base_url == "http://failover:5380"
        shutdown_mock.assert_awaited_once()
    finally:
        await state.close()


@pytest.mark.asyncio
async def test_start_token_renewal_idempotent(config: Config) -> None:
    """start_token_renewal should only schedule one task while the first is running."""

    state = AppState(config)
    try:
        async def _dummy(_state: AppState) -> None:
            await asyncio.sleep(0)

        state.start_token_renewal(_dummy)
        first_task = state._token_task
        assert first_task is not None
        await asyncio.sleep(0)
        state.start_token_renewal(_dummy)
        assert state._token_task is first_task
    finally:
        await state.close()


@pytest.mark.asyncio
async def test_update_status_sets_flags(config: Config) -> None:
    """update_status should atomically update readiness metadata."""

    state = AppState(config)
    try:
        await state.update_status(
            ready=True,
            writable=True,
            server_role="primary",
            catalog_membership="catalog.example.com",
        )

        assert state.is_ready is True
        assert state.is_writable is True
        assert state.server_role == "primary"
        assert state.catalog_membership == "catalog.example.com"
    finally:
        await state.close()


@pytest.mark.asyncio
async def test_ensure_writable_requires_primary(config: Config) -> None:
    """ensure_writable should raise when connected endpoint is read-only."""

    state = AppState(config)
    try:
        state.is_ready = True
        state.is_writable = False
        with pytest.raises(RuntimeError, match="read-only"):
            await state.ensure_writable()
    finally:
        await state.close()


@pytest.mark.asyncio
async def test_close_cancels_token_task(config: Config, mocker: MockerFixture) -> None:
    """close should cancel the renewal task and close the client."""

    state = AppState(config)
    close_mock = mocker.AsyncMock()
    state.client.close = close_mock  # type: ignore[assignment]

    async def sleeper() -> None:
        await asyncio.sleep(3600)

    state._token_task = asyncio.create_task(sleeper())

    await state.close()

    assert state._token_task.cancelled()
    close_mock.assert_awaited_once()
