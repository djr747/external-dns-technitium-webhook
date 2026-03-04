"""Unit tests for AppState behavior."""

import asyncio
from typing import cast
from unittest.mock import MagicMock  # noqa: F401 - used in cast() for type checking

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
        mocker.patch.object(state.client, "close", shutdown_mock)

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
async def test_ensure_ready_not_ready_raises_error(config: Config) -> None:
    """ensure_ready should raise RuntimeError when not ready."""
    state = AppState(config)
    try:
        state.is_ready = False
        with pytest.raises(RuntimeError, match="Service not ready yet"):
            state.ensure_ready()
    finally:
        await state.close()


@pytest.mark.asyncio
async def test_ensure_writable(config: Config) -> None:
    """ensure_writable should raise when connected endpoint is read-only."""

    state = AppState(config)
    try:
        state.is_ready = True
        state.is_writable = False
        with pytest.raises(RuntimeError, match="read-only"):
            state.ensure_writable()
    finally:
        await state.close()


@pytest.mark.asyncio
async def test_close_cancels_token_task(config: Config, mocker: MockerFixture) -> None:
    """close should cancel the renewal task and close the client."""

    state = AppState(config)
    close_mock = mocker.AsyncMock()
    mocker.patch.object(state.client, "close", close_mock)

    async def sleeper() -> None:
        await asyncio.sleep(3600)

    state._token_task = asyncio.create_task(sleeper())

    await state.close()

    assert state._token_task.cancelled()
    close_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_try_failover_endpoints_success(mocker: MockerFixture) -> None:
    """Test successful failover to alternate endpoint."""
    config = Config(
        technitium_url="http://primary.example.com:5380",
        technitium_username="admin",
        technitium_password="password",
        zone="example.com",
        technitium_failover_urls="http://secondary.example.com:5380",
    )

    state = AppState(config)

    try:
        # Mock the login response
        from unittest.mock import AsyncMock, MagicMock

        login_response = MagicMock()
        login_response.token = "new_token_123"

        # We need to mock the client replacement process to avoid actual network calls
        call_count = 0

        async def mock_set_active_endpoint(url: str) -> None:
            """Mock set_active_endpoint that doesn't try to connect."""
            nonlocal call_count
            call_count += 1
            # Just update the endpoint without replacing the client
            state.active_endpoint = url
            if hasattr(state.client, "base_url"):
                state.client.base_url = url

        # Replace set_active_endpoint with our mock
        mocker.patch.object(state, "set_active_endpoint", side_effect=mock_set_active_endpoint)

        # Mock the client login method
        mocker.patch.object(
            state.client, "login", new_callable=AsyncMock, return_value=login_response
        )

        # Call failover
        result = await state.try_failover_endpoints()

        assert result == (True, True)  # (failover_ok, is_writable)
        assert state.client.token == "new_token_123"
        assert state.active_endpoint == "http://secondary.example.com:5380"
        cast(MagicMock, state.client.login).assert_called_once_with(
            username="admin",
            password="password",
        )
    finally:
        await state.close()


@pytest.mark.asyncio
async def test_try_failover_endpoints_no_alternatives(config: Config) -> None:
    """Test failover when no alternate endpoints are available."""
    state = AppState(config)

    try:
        # Call failover with no failover_urls configured
        result = await state.try_failover_endpoints()

        assert result == (False, False)
    finally:
        await state.close()


@pytest.mark.asyncio
async def test_try_failover_endpoints_all_fail(mocker: MockerFixture) -> None:
    """Test failover when all alternate endpoints fail."""
    from unittest.mock import AsyncMock

    from external_dns_technitium_webhook.technitium_client import TechnitiumError

    config = Config(
        technitium_url="http://primary.example.com:5380",
        technitium_username="admin",
        technitium_password="password",
        zone="example.com",
        technitium_failover_urls="http://secondary.example.com:5380;http://tertiary.example.com:5380",
    )

    state = AppState(config)

    try:
        # Mock set_active_endpoint to succeed but login to fail
        mocker.patch.object(state, "set_active_endpoint", new_callable=AsyncMock)

        login_error = TechnitiumError("Connection refused")
        mocker.patch.object(state.client, "login", new_callable=AsyncMock, side_effect=login_error)

        # Call failover
        result = await state.try_failover_endpoints()

        assert result == (False, False)
    finally:
        await state.close()


@pytest.mark.asyncio
async def test_try_failback_to_primary_success(mocker: MockerFixture) -> None:
    """Test successful failback to primary endpoint."""
    from unittest.mock import AsyncMock

    config = Config(
        technitium_url="http://primary.example.com:5380",
        technitium_username="admin",
        technitium_password="password",
        zone="example.com",
        technitium_failover_urls="http://secondary.example.com:5380",
    )

    state = AppState(config)

    try:
        # Mock login response
        login_response = MagicMock()
        login_response.token = "token_123"

        # Mock zone options response for primary being writable
        zone_options = MagicMock()
        zone_options.is_read_only = False
        zone_options.catalog_zone_name = None

        # Simulate being on secondary endpoint
        state.active_endpoint = "http://secondary.example.com:5380"
        state.client.base_url = "http://secondary.example.com:5380"
        state.is_writable = True
        state.server_role = "secondary"

        # Mock set_active_endpoint
        async def mock_set_active_endpoint(url: str) -> None:
            state.active_endpoint = url
            if hasattr(state.client, "base_url"):
                state.client.base_url = url

        mocker.patch.object(state, "set_active_endpoint", side_effect=mock_set_active_endpoint)

        # Mock client methods
        mocker.patch.object(
            state.client, "login", new_callable=AsyncMock, return_value=login_response
        )
        mocker.patch.object(
            state.client, "get_zone_options", new_callable=AsyncMock, return_value=zone_options
        )

        # Call failback
        result = await state.try_failback_to_primary()

        assert result is True
        assert state.active_endpoint == "http://primary.example.com:5380"
        assert state.server_role == "primary"
    finally:
        await state.close()


@pytest.mark.asyncio
async def test_try_failback_to_primary_not_yet_ready(mocker: MockerFixture) -> None:
    """Test failback when primary is not yet ready."""
    from unittest.mock import AsyncMock

    from external_dns_technitium_webhook.technitium_client import TechnitiumError

    config = Config(
        technitium_url="http://primary.example.com:5380",
        technitium_username="admin",
        technitium_password="password",
        zone="example.com",
        technitium_failover_urls="http://secondary.example.com:5380",
    )

    state = AppState(config)

    try:
        # Simulate being on secondary endpoint
        state.active_endpoint = "http://secondary.example.com:5380"

        # Mock set_active_endpoint and login to fail
        mocker.patch.object(state, "set_active_endpoint", new_callable=AsyncMock)
        login_error = TechnitiumError("Connection refused")
        mocker.patch.object(state.client, "login", new_callable=AsyncMock, side_effect=login_error)

        # Call failback
        result = await state.try_failback_to_primary()

        assert result is False
        # Should stay on secondary
        assert state.active_endpoint == "http://secondary.example.com:5380"
    finally:
        await state.close()


@pytest.mark.asyncio
async def test_try_failback_already_on_primary(config: Config) -> None:
    """Test failback when already on primary endpoint."""
    state = AppState(config)

    try:
        # Confirm we're on primary
        assert state.active_endpoint == state.config.technitium_endpoints[0]

        # Call failback - should do nothing
        result = await state.try_failback_to_primary()

        assert result is False
    finally:
        await state.close()


@pytest.mark.asyncio
async def test_try_failback_primary_is_readonly(mocker: MockerFixture) -> None:
    """Test failback when primary is read-only (secondary)."""
    from unittest.mock import AsyncMock

    config = Config(
        technitium_url="http://primary.example.com:5380",
        technitium_username="admin",
        technitium_password="password",
        zone="example.com",
        technitium_failover_urls="http://secondary.example.com:5380",
    )

    state = AppState(config)

    try:
        # Mock login response
        login_response = MagicMock()
        login_response.token = "token_123"

        # Mock zone options - primary is read-only (became a secondary)
        zone_options = MagicMock()
        zone_options.is_read_only = True
        zone_options.catalog_zone_name = None

        # Simulate being on secondary endpoint
        state.active_endpoint = "http://secondary.example.com:5380"
        state.client.base_url = "http://secondary.example.com:5380"
        state.is_writable = True

        # Mock set_active_endpoint
        async def mock_set_active_endpoint(url: str) -> None:
            state.active_endpoint = url
            if hasattr(state.client, "base_url"):
                state.client.base_url = url

        mocker.patch.object(state, "set_active_endpoint", side_effect=mock_set_active_endpoint)

        # Mock client methods
        mocker.patch.object(
            state.client, "login", new_callable=AsyncMock, return_value=login_response
        )
        mocker.patch.object(
            state.client, "get_zone_options", new_callable=AsyncMock, return_value=zone_options
        )

        # Call failback
        result = await state.try_failback_to_primary()

        assert result is False
        # Should stay on secondary
        assert state.active_endpoint == "http://secondary.example.com:5380"
    finally:
        await state.close()
