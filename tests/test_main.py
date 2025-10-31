"""Tests for main application module."""

import asyncio
import signal
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import ANY, AsyncMock, MagicMock

import pytest
from fastapi import FastAPI, Response
from fastapi.testclient import TestClient
from pytest_mock import MockerFixture

from external_dns_technitium_webhook.app_state import AppState
from external_dns_technitium_webhook.config import Config
from external_dns_technitium_webhook.main import (
    ZonePreparationResult,
    _fetch_zone_options,
    auto_renew_technitium_token,
    create_app,
    create_default_zone,
    create_state_dependency,
    ensure_catalog_membership,
    ensure_zone_ready,
    get_app_state,
    lifespan,
    main,
    setup_technitium_connection,
)
from external_dns_technitium_webhook.models import (
    CreateZoneResponse,
    GetZoneOptionsResponse,
    LoginResponse,
)
from external_dns_technitium_webhook.technitium_client import TechnitiumError


def test_app_creation(mocker: MockerFixture) -> None:
    """Test application creation with mocked dependencies."""
    # Mock config to avoid actual environment variables
    mocker.patch(
        "external_dns_technitium_webhook.main.AppConfig",
        return_value=Config(
            technitium_url="http://localhost:5380",
            technitium_username="admin",
            technitium_password="password",
            zone="example.com",
            domain_filters="example.com",
        ),
    )

    app = create_app()

    assert isinstance(app, FastAPI)
    assert hasattr(app, "router")
    # app_state is set during lifespan, not during create_app()


def test_app_has_middleware(mocker: MockerFixture) -> None:
    """Test middleware is properly configured."""
    mocker.patch(
        "external_dns_technitium_webhook.main.AppConfig",
        return_value=Config(
            technitium_url="http://localhost:5380",
            technitium_username="admin",
            technitium_password="password",
            zone="example.com",
            domain_filters="example.com",
        ),
    )

    app = create_app()

    # Check that middleware was added
    assert len(app.user_middleware) > 0


def test_app_cors_enabled(mocker: MockerFixture) -> None:
    """Test CORS middleware is enabled."""
    mocker.patch(
        "external_dns_technitium_webhook.main.AppConfig",
        return_value=Config(
            technitium_url="http://localhost:5380",
            technitium_username="admin",
            technitium_password="password",
            zone="example.com",
            domain_filters="example.com",
        ),
    )

    app = create_app()

    # Check for CORS middleware
    middleware_names = [str(m) for m in app.user_middleware]
    assert any("CORS" in name for name in middleware_names)


@pytest.mark.asyncio
async def test_ensure_zone_ready_existing_zone(mocker: MockerFixture) -> None:
    """Ensure existing zone returns writable status without creation."""

    config = Config(
        technitium_url="http://localhost:5380",
        technitium_username="admin",
        technitium_password="password",
        zone="example.com",
    )
    state = AppState(config=config)

    options = GetZoneOptionsResponse(
        zone=config.zone,
        isCatalogZone=False,
        isReadOnly=False,
        catalogZoneName=None,
        availableCatalogZoneNames=[],
    )

    mocker.patch.object(state.client, "get_zone_options", return_value=options)

    result = await ensure_zone_ready(state)

    assert result.zone_created is False
    assert result.is_writable is True
    assert result.server_role == "primary"
    assert result.catalog_membership is None


@pytest.mark.asyncio
async def test_ensure_zone_ready_creates_zone_when_missing(mocker: MockerFixture) -> None:
    """Ensure zone is created when missing."""

    config = Config(
        technitium_url="http://localhost:5380",
        technitium_username="admin",
        technitium_password="password",
        zone="example.com",
    )
    state = AppState(config=config)

    options_after_create = GetZoneOptionsResponse(
        zone=config.zone,
        isCatalogZone=False,
        isReadOnly=False,
        catalogZoneName=None,
        availableCatalogZoneNames=[],
    )

    mocker.patch.object(
        state.client,
        "get_zone_options",
        side_effect=[TechnitiumError("zone not found"), options_after_create],
    )

    mock_create = mocker.patch.object(
        state.client,
        "create_zone",
        new_callable=AsyncMock,
        return_value=CreateZoneResponse(domain=config.zone),
    )

    result = await ensure_zone_ready(state)

    assert result.zone_created is True
    assert result.is_writable is True
    mock_create.assert_awaited_once()


@pytest.mark.asyncio
async def test_ensure_zone_ready_secondary_skips_catalog(mocker: MockerFixture) -> None:
    """Read-only endpoints should not attempt catalog enrollment."""

    config = Config(
        technitium_url="http://localhost:5380",
        technitium_username="admin",
        technitium_password="password",
        zone="example.com",
        catalog_zone="catalog.example.com",
    )
    state = AppState(config=config)

    options = GetZoneOptionsResponse(
        zone=config.zone,
        isCatalogZone=False,
        isReadOnly=True,
        catalogZoneName="catalog.example.com",
        availableCatalogZoneNames=["catalog.example.com"],
    )

    mocker.patch.object(state.client, "get_zone_options", return_value=options)
    catalog_mock = mocker.patch(
        "external_dns_technitium_webhook.main.ensure_catalog_membership",
        new_callable=AsyncMock,
    )

    try:
        result = await ensure_zone_ready(state)
    finally:
        await state.close()

    assert result.is_writable is False
    assert result.server_role == "secondary"
    assert result.catalog_membership == "catalog.example.com"
    catalog_mock.assert_not_called()


@pytest.mark.asyncio
async def test_ensure_zone_ready_invokes_catalog_membership(mocker: MockerFixture) -> None:
    """Primary endpoints with catalog configured should enroll membership."""

    config = Config(
        technitium_url="http://localhost:5380",
        technitium_username="admin",
        technitium_password="password",
        zone="example.com",
        catalog_zone="catalog.example.com",
    )
    state = AppState(config=config)

    options = GetZoneOptionsResponse(
        zone=config.zone,
        isCatalogZone=False,
        isReadOnly=False,
        catalogZoneName=None,
        availableCatalogZoneNames=["catalog.example.com"],
    )

    mocker.patch.object(state.client, "get_zone_options", new_callable=AsyncMock, return_value=options)
    catalog_mock = mocker.patch(
        "external_dns_technitium_webhook.main.ensure_catalog_membership",
        new_callable=AsyncMock,
        return_value="catalog.example.com",
    )

    try:
        result = await ensure_zone_ready(state)
    finally:
        await state.close()

    assert result.catalog_membership == "catalog.example.com"
    catalog_mock.assert_awaited_once_with(state, options, "catalog.example.com")


@pytest.mark.asyncio
async def test_create_default_zone(mocker: MockerFixture) -> None:
    """Test creating default zone."""
    config = Config(
        technitium_url="http://localhost:5380",
        technitium_username="admin",
        technitium_password="password",
        zone="example.com",
        catalog_zone="catalog.example.com",
    )
    state = AppState(config=config)

    # Mock create_zone
    mock_response = CreateZoneResponse(domain="example.com")

    mock_create = mocker.patch.object(
        state.client,
        "create_zone",
        new_callable=AsyncMock,
        return_value=mock_response,
    )

    # Should not raise any exception
    await create_default_zone(state)
    mock_create.assert_awaited_once_with(
        zone=config.zone,
        zone_type="Forwarder",
        protocol="Udp",
        forwarder="this-server",
        dnssec_validation=True,
        catalog=config.catalog_zone_name,
    )


@pytest.mark.asyncio
async def test_ensure_catalog_membership_skips_when_unavailable(
    mocker: MockerFixture,
) -> None:
    """Do not enroll when desired catalog is not offered by endpoint."""

    config = Config(
        technitium_url="http://localhost:5380",
        technitium_username="admin",
        technitium_password="password",
        zone="example.com",
    )
    state = AppState(config=config)

    options = GetZoneOptionsResponse(
        zone=config.zone,
        isCatalogZone=False,
        isReadOnly=False,
        catalogZoneName=None,
        availableCatalogZoneNames=["other.example.com"],
    )

    set_mock = mocker.patch.object(state.client, "set_zone_options", new_callable=AsyncMock)

    try:
        result = await ensure_catalog_membership(state, options, "catalog.example.com")
    finally:
        await state.close()

    assert result is None
    set_mock.assert_not_called()


@pytest.mark.asyncio
async def test_ensure_catalog_membership_returns_existing_membership(
    mocker: MockerFixture,
) -> None:
    """When already enrolled, ensure_catalog_membership should return current membership."""

    config = Config(
        technitium_url="http://localhost:5380",
        technitium_username="admin",
        technitium_password="password",
        zone="example.com",
    )
    state = AppState(config=config)

    options = GetZoneOptionsResponse(
        zone=config.zone,
        isCatalogZone=False,
        isReadOnly=False,
        catalogZoneName="catalog.example.com",
        availableCatalogZoneNames=["catalog.example.com"],
    )

    try:
        membership = await ensure_catalog_membership(state, options, "catalog.example.com")
    finally:
        await state.close()

    assert membership == "catalog.example.com"


@pytest.mark.asyncio
async def test_ensure_catalog_membership_enrolls_when_available(
    mocker: MockerFixture,
) -> None:
    """Enroll zone when catalog is offered and server reports membership."""

    config = Config(
        technitium_url="http://localhost:5380",
        technitium_username="admin",
        technitium_password="password",
        zone="example.com",
    )
    state = AppState(config=config)

    options = GetZoneOptionsResponse(
        zone=config.zone,
        isCatalogZone=False,
        isReadOnly=False,
        catalogZoneName=None,
        availableCatalogZoneNames=["Catalog.Example.com"],
    )

    set_mock = mocker.patch.object(state.client, "set_zone_options", new_callable=AsyncMock)
    refreshed = GetZoneOptionsResponse(
        zone=config.zone,
        isCatalogZone=True,
        isReadOnly=False,
        catalogZoneName="catalog.example.com",
        availableCatalogZoneNames=["catalog.example.com"],
    )
    mocker.patch.object(
        state.client,
        "get_zone_options",
        new_callable=AsyncMock,
        return_value=refreshed,
    )

    try:
        membership = await ensure_catalog_membership(state, options, "catalog.example.com")
    finally:
        await state.close()

    assert membership == "catalog.example.com"
    set_mock.assert_awaited_once_with(
        state.config.zone,
        catalogZoneName="catalog.example.com",
    )


@pytest.mark.asyncio
async def test_setup_technitium_connection_success(mocker: MockerFixture) -> None:
    """Test successful Technitium connection setup."""
    config = Config(
        technitium_url="http://localhost:5380",
        technitium_username="admin",
        technitium_password="password",
        zone="example.com",
    )
    state = AppState(config=config)
    mocker.patch.object(state, "set_active_endpoint", new_callable=AsyncMock)

    login_response = LoginResponse(username="admin", displayName="Admin", token="test-token")
    mocker.patch.object(state.client, "login", new_callable=AsyncMock, return_value=login_response)

    zone_result = ZonePreparationResult(
        zone_created=False,
        is_writable=True,
        server_role="primary",
        catalog_membership=None,
    )
    mocker.patch(
        "external_dns_technitium_webhook.main.ensure_zone_ready",
        new_callable=AsyncMock,
        return_value=zone_result,
    )

    update_mock = mocker.patch.object(state, "update_status", new_callable=AsyncMock)
    start_mock = mocker.patch.object(state, "start_token_renewal")

    await setup_technitium_connection(state)

    update_mock.assert_awaited_once_with(
        ready=True,
        writable=True,
        server_role="primary",
        catalog_membership=None,
    )
    start_mock.assert_called_once()
    assert state.client.token == "test-token"


@pytest.mark.asyncio
async def test_setup_technitium_connection_uses_failover(mocker: MockerFixture) -> None:
    """Setup should try secondary endpoints when the first attempt fails."""

    config = Config(
        technitium_url="http://primary:5380",
        technitium_username="admin",
        technitium_password="password",
        zone="example.com",
        technitium_failover_urls="http://failover:5380",
    )
    state = AppState(config=config)

    set_endpoint_mock = mocker.patch.object(
        state,
        "set_active_endpoint",
        new_callable=AsyncMock,
    )

    login_response = LoginResponse(username="admin", displayName="Admin", token="ok")
    login_mock = mocker.patch.object(
        state.client,
        "login",
        new_callable=AsyncMock,
        side_effect=[RuntimeError("boom"), login_response],
    )

    zone_result = ZonePreparationResult(
        zone_created=False,
        is_writable=True,
        server_role="primary",
        catalog_membership=None,
    )
    mocker.patch(
        "external_dns_technitium_webhook.main.ensure_zone_ready",
        new_callable=AsyncMock,
        return_value=zone_result,
    )

    update_mock = mocker.patch.object(state, "update_status", new_callable=AsyncMock)
    start_mock = mocker.patch.object(state, "start_token_renewal")

    await setup_technitium_connection(state)

    assert login_mock.await_count == 2
    assert [call.args[0] for call in set_endpoint_mock.await_args_list] == config.technitium_endpoints
    update_mock.assert_awaited_once()
    start_mock.assert_called_once()


@pytest.mark.asyncio
async def test_setup_connection_logs_creation_and_catalog(
    mocker: MockerFixture, caplog: pytest.LogCaptureFixture
) -> None:
    """Zone creation and catalog enrollment messages should be logged."""

    config = Config(
        technitium_url="http://localhost:5380",
        technitium_username="admin",
        technitium_password="password",
        zone="example.com",
    )
    state = AppState(config=config)
    caplog.set_level("INFO")

    mocker.patch.object(state, "set_active_endpoint", new_callable=AsyncMock)
    login_response = LoginResponse(username="admin", displayName="Admin", token="test")
    mocker.patch.object(state.client, "login", new_callable=AsyncMock, return_value=login_response)

    zone_result = ZonePreparationResult(
        zone_created=True,
        is_writable=True,
        server_role="primary",
        catalog_membership="catalog.example.com",
    )
    mocker.patch(
        "external_dns_technitium_webhook.main.ensure_zone_ready",
        new_callable=AsyncMock,
        return_value=zone_result,
    )

    update_mock = mocker.patch.object(state, "update_status", new_callable=AsyncMock)
    mocker.patch.object(state, "start_token_renewal")

    try:
        await setup_technitium_connection(state)
    finally:
        await state.close()

    update_mock.assert_awaited_once()
    assert "Zone example.com created" in caplog.text
    assert "Zone example.com enrolled in catalog zone catalog.example.com" in caplog.text


@pytest.mark.asyncio
async def test_setup_connection_logs_read_only_warning(
    mocker: MockerFixture, caplog: pytest.LogCaptureFixture
) -> None:
    """Read-only endpoints should log a warning."""

    config = Config(
        technitium_url="http://localhost:5380",
        technitium_username="admin",
        technitium_password="password",
        zone="example.com",
    )
    state = AppState(config=config)
    caplog.set_level("WARNING")

    mocker.patch.object(state, "set_active_endpoint", new_callable=AsyncMock)
    login_response = LoginResponse(username="admin", displayName="Admin", token="test")
    mocker.patch.object(state.client, "login", new_callable=AsyncMock, return_value=login_response)

    zone_result = ZonePreparationResult(
        zone_created=False,
        is_writable=False,
        server_role="secondary",
        catalog_membership=None,
    )
    mocker.patch(
        "external_dns_technitium_webhook.main.ensure_zone_ready",
        new_callable=AsyncMock,
        return_value=zone_result,
    )

    mocker.patch.object(state, "update_status", new_callable=AsyncMock)
    mocker.patch.object(state, "start_token_renewal")

    try:
        await setup_technitium_connection(state)
    finally:
        await state.close()

    assert "read-only" in caplog.text


@pytest.mark.asyncio
async def test_fetch_zone_options_handles_not_found(mocker: MockerFixture) -> None:
    """_fetch_zone_options should return None when the server reports missing zone."""

    state = AppState(config=_build_config())
    mocker.patch.object(
        state.client,
        "get_zone_options",
        new_callable=AsyncMock,
        side_effect=TechnitiumError("Zone not found"),
    )

    try:
        result = await _fetch_zone_options(state, "example.com")
    finally:
        await state.close()

    assert result is None


@pytest.mark.asyncio
async def test_fetch_zone_options_reraises_other_errors(mocker: MockerFixture) -> None:
    """Unexpected errors should propagate from _fetch_zone_options."""

    state = AppState(config=_build_config())
    mocker.patch.object(
        state.client,
        "get_zone_options",
        new_callable=AsyncMock,
        side_effect=TechnitiumError("server unavailable"),
    )

    with pytest.raises(TechnitiumError):
        try:
            await _fetch_zone_options(state, "example.com")
        finally:
            await state.close()


@pytest.mark.asyncio
async def test_ensure_zone_ready_raises_when_zone_missing_after_create(
    mocker: MockerFixture,
) -> None:
    """An error should be raised when zone options cannot be loaded after creation."""

    config = Config(
        technitium_url="http://localhost:5380",
        technitium_username="admin",
        technitium_password="password",
        zone="example.com",
    )
    state = AppState(config=config)

    mocker.patch.object(
        state.client,
        "get_zone_options",
        new_callable=AsyncMock,
        side_effect=[TechnitiumError("zone not found"), None],
    )
    mocker.patch.object(state.client, "create_zone", new_callable=AsyncMock)

    with pytest.raises(RuntimeError):
        await ensure_zone_ready(state)


    await state.close()


@pytest.mark.asyncio
async def test_ensure_catalog_membership_logs_mismatch(
    mocker: MockerFixture, caplog: pytest.LogCaptureFixture
) -> None:
    """Ensure catalog membership warns when server reports a different membership."""

    config = Config(
        technitium_url="http://localhost:5380",
        technitium_username="admin",
        technitium_password="password",
        zone="example.com",
    )
    state = AppState(config=config)
    state.active_endpoint = "http://localhost:5380"
    caplog.set_level("INFO")

    options = GetZoneOptionsResponse(
        zone=config.zone,
        isCatalogZone=False,
        isReadOnly=False,
        catalogZoneName=None,
        availableCatalogZoneNames=["catalog.example.com"],
    )

    mocker.patch.object(state.client, "set_zone_options", new_callable=AsyncMock)
    refreshed = GetZoneOptionsResponse(
        zone=config.zone,
        isCatalogZone=False,
        isReadOnly=False,
        catalogZoneName="other.example.com",
        availableCatalogZoneNames=["catalog.example.com"],
    )
    mocker.patch.object(
        state.client,
        "get_zone_options",
        new_callable=AsyncMock,
        return_value=refreshed,
    )

    try:
        membership = await ensure_catalog_membership(state, options, "catalog.example.com")
    finally:
        await state.close()
    assert membership == "other.example.com"
    assert "server reports membership other.example.com" in caplog.text


@pytest.mark.asyncio
async def test_setup_connection_exits_when_no_endpoints(mocker: MockerFixture) -> None:
    """setup_technitium_connection should exit when no endpoints are configured."""

    config = Config(
        technitium_url=" ",  # trimmed to empty
        technitium_username="admin",
        technitium_password="password",
        zone="example.com",
    )
    state = AppState(config=config)
    exit_mock = mocker.patch(
        "external_dns_technitium_webhook.main.sys.exit",
        side_effect=SystemExit(1),
    )
    status_mock = mocker.patch.object(state, "update_status", new_callable=AsyncMock)

    with pytest.raises(SystemExit):
        await setup_technitium_connection(state)
    await state.close()

    status_mock.assert_awaited_once_with(
        ready=False,
        writable=False,
        server_role=None,
        catalog_membership=None,
    )
    exit_mock.assert_called_once_with(1)


@pytest.mark.asyncio
async def test_setup_connection_exits_after_failures(mocker: MockerFixture) -> None:
    """setup_technitium_connection should exit when all endpoints fail."""

    config = Config(
        technitium_url="http://primary:5380",
        technitium_username="admin",
        technitium_password="password",
        zone="example.com",
    )
    state = AppState(config=config)

    mocker.patch.object(state, "set_active_endpoint", new_callable=AsyncMock)
    mocker.patch.object(
        state.client,
        "login",
        new_callable=AsyncMock,
        side_effect=RuntimeError("boom"),
    )
    status_mock = mocker.patch.object(state, "update_status", new_callable=AsyncMock)
    exit_mock = mocker.patch(
        "external_dns_technitium_webhook.main.sys.exit",
        side_effect=SystemExit(1),
    )

    with pytest.raises(SystemExit):
        await setup_technitium_connection(state)
    await state.close()

    status_mock.assert_awaited_once_with(
        ready=False,
        writable=False,
        server_role=None,
        catalog_membership=None,
    )
    exit_mock.assert_called_once_with(1)


def _build_config() -> Config:
    """Helper to create a minimal configuration for tests."""

    return Config(
        technitium_url="http://localhost:5380",
        technitium_username="admin",
        technitium_password="password",
        zone="example.com",
        domain_filters="example.com",
    )


def test_get_app_state_returns_state(mocker: MockerFixture) -> None:
    """get_app_state should return the previously stored AppState."""

    mocker.patch("external_dns_technitium_webhook.app_state.TechnitiumClient")
    app = FastAPI()
    state = AppState(config=_build_config())
    app.state.app_state = state

    assert get_app_state(app) is state


def test_get_app_state_raises_when_missing() -> None:
    """get_app_state should raise when state has not been initialized."""

    app = FastAPI()

    with pytest.raises(RuntimeError, match="Application state not initialized"):
        get_app_state(app)


def test_create_state_dependency_invokes_get_app_state(mocker: MockerFixture) -> None:
    """create_state_dependency should forward to get_app_state when invoked."""

    app = FastAPI()
    dependency = create_state_dependency(app)
    sentinel_state = object()
    mocked_get = mocker.patch(
        "external_dns_technitium_webhook.main.get_app_state",
        return_value=sentinel_state,
    )

    assert dependency() is sentinel_state
    mocked_get.assert_called_once_with(app)


@pytest.mark.asyncio
async def test_lifespan_initializes_and_closes_state(mocker: MockerFixture) -> None:
    """lifespan should initialize app state and close it on shutdown."""

    app = FastAPI()
    config = _build_config()
    mocker.patch("external_dns_technitium_webhook.main.AppConfig", return_value=config)
    state = MagicMock(spec=AppState)
    state.close = AsyncMock()
    mocker.patch("external_dns_technitium_webhook.main.AppState", return_value=state)
    setup_mock = mocker.patch(
        "external_dns_technitium_webhook.main.setup_technitium_connection",
        new_callable=AsyncMock,
    )

    async with lifespan(app):
        assert app.state.app_state is state

    setup_mock.assert_awaited_once_with(state)
    state.close.assert_awaited_once()


@pytest.mark.asyncio
async def test_auto_renew_token_success_sets_token(mocker: MockerFixture) -> None:
    """auto_renew_technitium_token refreshes the token after sleeping."""

    config = _build_config()
    login_response = SimpleNamespace(token="renewed")
    client = SimpleNamespace(token=None)
    login_mock = AsyncMock(return_value=login_response)
    client.login = login_mock
    state = SimpleNamespace(
        config=config,
        client=client,
        active_endpoint="http://localhost:5380",
    )
    sleep_mock = mocker.patch(
        "external_dns_technitium_webhook.main.asyncio.sleep",
        new_callable=AsyncMock,
    )
    sleep_mock.side_effect = [None, asyncio.CancelledError()]

    await auto_renew_technitium_token(cast(AppState, state))

    login_mock.assert_awaited_once_with(
        username=config.technitium_username,
        password=config.technitium_password,
    )
    assert state.client.token == "renewed"


@pytest.mark.asyncio
async def test_auto_renew_token_failure_uses_failure_interval(mocker: MockerFixture) -> None:
    """auto_renew_technitium_token should retry quickly after a failure."""

    config = _build_config()
    client = SimpleNamespace(token="unchanged")
    login_mock = AsyncMock(side_effect=RuntimeError("boom"))
    client.login = login_mock
    state = SimpleNamespace(
        config=config,
        client=client,
        active_endpoint="http://localhost:5380",
    )
    sleep_mock = mocker.patch(
        "external_dns_technitium_webhook.main.asyncio.sleep",
        new_callable=AsyncMock,
    )
    sleep_mock.side_effect = [None, None, asyncio.CancelledError()]

    await auto_renew_technitium_token(cast(AppState, state))

    assert sleep_mock.await_args_list[0].args[0] == 20 * 60
    assert sleep_mock.await_args_list[1].args[0] == 60
    assert state.client.token == "unchanged"


def test_app_routes_delegate_to_handlers(mocker: MockerFixture) -> None:
    """Routes defined in create_app should delegate to underlying handlers."""

    mocker.patch("external_dns_technitium_webhook.app_state.TechnitiumClient")
    state = AppState(config=_build_config())
    state.is_ready = True

    @asynccontextmanager
    async def _dummy_lifespan(_app: FastAPI):
        yield

    mocker.patch("external_dns_technitium_webhook.main.lifespan", _dummy_lifespan)
    app = create_app()
    app.state.app_state = state

    health_mock = mocker.patch(
        "external_dns_technitium_webhook.main.health_check",
        new_callable=AsyncMock,
    )
    health_mock.return_value = None
    negotiate_response = Response(content="filters", media_type="application/json")
    negotiate_mock = mocker.patch(
        "external_dns_technitium_webhook.main.negotiate_domain_filter",
        new_callable=AsyncMock,
        return_value=negotiate_response,
    )
    records_response = Response(content="[]", media_type="application/json")
    records_mock = mocker.patch(
        "external_dns_technitium_webhook.main.get_records",
        new_callable=AsyncMock,
        return_value=records_response,
    )
    adjust_response = Response(content="[]", media_type="application/json")
    adjust_mock = mocker.patch(
        "external_dns_technitium_webhook.main.adjust_endpoints",
        new_callable=AsyncMock,
        return_value=adjust_response,
    )
    apply_mock = mocker.patch(
        "external_dns_technitium_webhook.main.apply_record",
        new_callable=AsyncMock,
    )

    endpoint_payload = [
        {
            "dnsName": "api.example.com",
            "recordType": "A",
            "targets": ["1.2.3.4"],
        }
    ]
    changes_payload = {
        "create": [],
        "updateOld": None,
        "updateNew": None,
        "delete": [],
    }

    with TestClient(app) as client:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

        response = client.get("/")
        assert response.status_code == 200
        assert response.content == negotiate_response.body

        response = client.get("/records")
        assert response.status_code == 200
        assert response.content == records_response.body

        response = client.post("/adjustendpoints", json=endpoint_payload)
        assert response.status_code == 200
        assert response.content == adjust_response.body

        response = client.post("/records", json=changes_payload)
        assert response.status_code == 204

    health_mock.assert_awaited_once_with(state)
    negotiate_mock.assert_awaited_once_with(state)
    records_mock.assert_awaited_once_with(state)
    adjust_mock.assert_awaited_once_with(state, ANY)
    apply_mock.assert_awaited_once_with(state, ANY)


def test_main_runs_server_and_handles_signals(mocker: MockerFixture) -> None:
    """main should start the server and shut it down on signals."""

    app = object()
    mocker.patch("external_dns_technitium_webhook.main.create_app", return_value=app)
    config = _build_config()
    mocker.patch("external_dns_technitium_webhook.main.AppConfig", return_value=config)
    uvicorn_config = mocker.Mock()
    mocker.patch(
        "external_dns_technitium_webhook.main.UvicornConfig",
        return_value=uvicorn_config,
    )
    server_mock = mocker.Mock()
    server_mock.should_exit = False
    mocker.patch("external_dns_technitium_webhook.main.Server", return_value=server_mock)

    handlers: dict[int, Any] = {}

    def _capture_handler(signum: int, handler: Any) -> None:
        handlers[signum] = handler

    mocker.patch("external_dns_technitium_webhook.main.signal.signal", side_effect=_capture_handler)

    main()

    server_mock.run.assert_called_once()
    assert signal.SIGINT in handlers
    assert signal.SIGTERM in handlers

    handlers[signal.SIGTERM](signal.SIGTERM, None)
    assert server_mock.should_exit is True
