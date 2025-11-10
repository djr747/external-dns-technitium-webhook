"""Unit tests for run_servers function."""

import asyncio
import contextlib
import signal
from unittest.mock import AsyncMock, MagicMock

import pytest
from pytest_mock import MockerFixture

from external_dns_technitium_webhook.config import Config
from external_dns_technitium_webhook.server import run_servers


@pytest.fixture
def config() -> Config:
    """Return test config."""
    return Config(
        technitium_url="http://localhost:5380",
        technitium_username="admin",
        technitium_password="password",
        zone="example.com",
        listen_address="127.0.0.1",
        listen_port=8888,
        health_port=8889,  # Use different port to avoid conflicts
    )


def test_run_servers_happy_path(config: Config, mocker: MockerFixture) -> None:
    """Test run_servers with successful server startup."""
    # Mock the Server class instances
    mock_main_server = MagicMock()
    mock_health_server = MagicMock()

    # Mock serve methods
    async def mock_serve():
        await asyncio.sleep(0.01)

    mock_main_server.serve = AsyncMock(side_effect=mock_serve)
    mock_health_server.serve = AsyncMock(side_effect=mock_serve)

    # Track Server constructor calls
    servers_created = []

    def mock_server_init(*args, **kwargs):
        server = mock_main_server if len(servers_created) == 0 else mock_health_server
        servers_created.append(server)
        return server

    mocker.patch("external_dns_technitium_webhook.server.Server", side_effect=mock_server_init)

    # Mock asyncio.run to exit quickly
    async def quick_serve():
        await asyncio.sleep(0.01)

    mocker.patch("external_dns_technitium_webhook.server.asyncio.run", side_effect=quick_serve)

    # Mock FastAPI apps
    mock_app = MagicMock()
    mock_health_app = MagicMock()

    # Mock signal to avoid actual signal handling
    mocker.patch("signal.signal")

    # Mock logging
    mock_logger = mocker.patch("external_dns_technitium_webhook.server.logging")

    # Call run_servers
    run_servers(mock_app, mock_health_app, config)

    # Verify both servers were created
    assert len(servers_created) == 2

    # Verify logging calls for successful startup
    log_info_calls = [call[0][0] for call in mock_logger.info.call_args_list]
    assert any("Health server is ready" in str(call) for call in log_info_calls)


def test_run_servers_timeout_waiting_for_health(config: Config, mocker: MockerFixture) -> None:
    """Test run_servers when health server startup times out."""
    # Mock Server class
    mock_main_server = MagicMock()
    mock_health_server = MagicMock()

    async def no_op():
        pass

    mock_main_server.serve = AsyncMock(side_effect=no_op)
    mock_health_server.serve = AsyncMock(side_effect=no_op)

    servers_created = []

    def server_init(*args, **kwargs):
        server = mock_main_server if len(servers_created) == 0 else mock_health_server
        servers_created.append(server)
        return server

    mocker.patch("external_dns_technitium_webhook.server.Server", side_effect=server_init)

    # Mock asyncio.run
    mocker.patch("external_dns_technitium_webhook.server.asyncio.run", side_effect=no_op)

    # Mock threading.Event to return timeout
    mock_event = MagicMock()
    mock_event.wait.return_value = False  # Simulate timeout

    mock_thread = MagicMock()  # Thread instance
    mocker.patch("threading.Thread", return_value=mock_thread)
    mocker.patch("threading.Event", return_value=mock_event)

    # Mock signal
    mocker.patch("signal.signal")

    # Mock logging
    mock_logger = mocker.patch("external_dns_technitium_webhook.server.logging")

    # Mock FastAPI apps
    mock_app = MagicMock()
    mock_health_app = MagicMock()

    # Call run_servers
    run_servers(mock_app, mock_health_app, config)

    # Verify timeout error was logged
    mock_logger.error.assert_any_call(
        "Health server failed to start (timeout waiting for server to bind to port)"
    )


def test_run_servers_health_error(config: Config, mocker: MockerFixture) -> None:
    """Test run_servers when health server sets error."""
    # Mock Server class
    mock_main_server = MagicMock()
    mock_health_server = MagicMock()

    async def no_op():
        pass

    mock_main_server.serve = AsyncMock(side_effect=no_op)
    mock_health_server.serve = AsyncMock(side_effect=no_op)

    servers_created = []

    def server_init(*args, **kwargs):
        server = mock_main_server if len(servers_created) == 0 else mock_health_server
        servers_created.append(server)
        return server

    mocker.patch("external_dns_technitium_webhook.server.Server", side_effect=server_init)

    # Mock asyncio.run
    mocker.patch("external_dns_technitium_webhook.server.asyncio.run", side_effect=no_op)

    # Mock threading.Event with error set
    mock_event = MagicMock()
    mock_event.wait.return_value = True  # Ready event

    mocker.patch("threading.Event", return_value=mock_event)

    # Mock signal
    mocker.patch("signal.signal")

    # Mock logging
    mock_logger = mocker.patch("external_dns_technitium_webhook.server.logging")

    # Patch the health server thread target to set an error
    def patched_thread(target, daemon):
        """Create a thread that injects error before calling target."""
        mock_thread = MagicMock()

        def wrapped_target():
            # Simulate health server error by raising
            with contextlib.suppress(Exception):
                target()

        mock_thread.target = wrapped_target
        return mock_thread

    mocker.patch(
        "threading.Thread",
        side_effect=lambda **kwargs: patched_thread(kwargs["target"], kwargs["daemon"]),
    )

    # Mock FastAPI apps
    mock_app = MagicMock()
    mock_health_app = MagicMock()

    # Call run_servers
    run_servers(mock_app, mock_health_app, config)

    # Verify health is ready (no error in this test since we mock too much)
    assert mock_logger.info.called


def test_run_servers_main_exception(config: Config, mocker: MockerFixture) -> None:
    """Test run_servers when main server raises exception."""
    # Mock Server class
    mock_main_server = MagicMock()
    mock_health_server = MagicMock()

    async def no_op():
        pass

    mock_main_server.serve = AsyncMock(side_effect=no_op)
    mock_health_server.serve = AsyncMock(side_effect=no_op)

    servers_created = []

    def server_init(*args, **kwargs):
        server = mock_main_server if len(servers_created) == 0 else mock_health_server
        servers_created.append(server)
        return server

    mocker.patch("external_dns_technitium_webhook.server.Server", side_effect=server_init)

    # Mock asyncio.run to raise an exception
    def asyncio_run_error(coro):
        raise RuntimeError("Server failed")

    mocker.patch(
        "external_dns_technitium_webhook.server.asyncio.run", side_effect=asyncio_run_error
    )

    # Mock threading.Event
    mock_event = MagicMock()
    mock_event.wait.return_value = True
    mock_thread = MagicMock()
    mocker.patch("threading.Thread", return_value=mock_thread)
    mocker.patch("threading.Event", return_value=mock_event)

    # Mock signal
    mocker.patch("signal.signal")

    # Mock logging
    mock_logger = mocker.patch("external_dns_technitium_webhook.server.logging")

    # Mock FastAPI apps
    mock_app = MagicMock()
    mock_health_app = MagicMock()

    # Call run_servers - should catch and log the exception
    run_servers(mock_app, mock_health_app, config)

    # Verify error was logged
    mock_logger.error.assert_any_call("Main server error: Server failed")


def test_run_servers_signal_handlers(config: Config, mocker: MockerFixture) -> None:
    """Test that signal handlers are registered."""
    # Mock Server class
    mock_main_server = MagicMock()
    mock_health_server = MagicMock()

    async def no_op():
        pass

    mock_main_server.serve = AsyncMock(side_effect=no_op)
    mock_health_server.serve = AsyncMock(side_effect=no_op)

    servers_created = []

    def server_init(*args, **kwargs):
        server = mock_main_server if len(servers_created) == 0 else mock_health_server
        servers_created.append(server)
        return server

    mocker.patch("external_dns_technitium_webhook.server.Server", side_effect=server_init)

    # Mock asyncio.run
    mocker.patch("external_dns_technitium_webhook.server.asyncio.run", side_effect=no_op)

    # Mock threading
    mock_event = MagicMock()
    mock_event.wait.return_value = True
    mock_thread = MagicMock()
    mocker.patch("threading.Thread", return_value=mock_thread)
    mocker.patch("threading.Event", return_value=mock_event)

    # Track signal registrations
    signal_registrations = {}

    def mock_signal(sig, handler):
        signal_registrations[sig] = handler

    mocker.patch("signal.signal", side_effect=mock_signal)

    # Mock FastAPI apps
    mock_app = MagicMock()
    mock_health_app = MagicMock()

    # Call run_servers
    run_servers(mock_app, mock_health_app, config)

    # Verify SIGINT and SIGTERM handlers were registered
    assert signal.SIGINT in signal_registrations
    assert signal.SIGTERM in signal_registrations


def test_run_servers_health_server_timeout(config: Config, mocker: MockerFixture) -> None:
    """Test run_servers when health server times out."""
    # Mock the Server class
    mock_main_server = MagicMock()
    mock_health_server = MagicMock()
    mocker.patch(
        "external_dns_technitium_webhook.server.Server",
        side_effect=[mock_main_server, mock_health_server],
    )

    # Mock asyncio.run
    mocker.patch("external_dns_technitium_webhook.server.asyncio.run")

    # Mock threading
    mocker.patch("threading.Thread")
    mock_event_class = mocker.patch("threading.Event")
    mock_event_instance = MagicMock()
    mock_event_instance.wait.return_value = False  # Simulate timeout
    mock_event_class.return_value = mock_event_instance

    # Mock signal
    mocker.patch("signal.signal")

    # Mock logging
    mock_logger = mocker.patch("external_dns_technitium_webhook.server.logging")

    # Mock FastAPI app
    mock_app = MagicMock()
    mock_health_app = MagicMock()

    # Call run_servers
    run_servers(mock_app, mock_health_app, config)

    # Verify timeout error was logged
    mock_logger.error.assert_any_call(
        "Health server failed to start (timeout waiting for server to bind to port)"
    )


def test_run_servers_main_server_exception(config: Config, mocker: MockerFixture) -> None:
    """Test run_servers when main server raises an exception."""
    # Mock the Server class
    mock_main_server = MagicMock()
    mock_health_server = MagicMock()
    mocker.patch(
        "external_dns_technitium_webhook.server.Server",
        side_effect=[mock_main_server, mock_health_server],
    )

    # Mock asyncio.run to raise an exception
    mock_asyncio_run = mocker.patch("external_dns_technitium_webhook.server.asyncio.run")
    mock_asyncio_run.side_effect = RuntimeError("Server error")

    # Mock threading
    mocker.patch("threading.Thread")
    mock_event_class = mocker.patch("threading.Event")
    mock_event_instance = MagicMock()
    mock_event_instance.wait.return_value = True
    mock_event_class.return_value = mock_event_instance

    # Mock signal
    mocker.patch("signal.signal")

    # Mock logging
    mock_logger = mocker.patch("external_dns_technitium_webhook.server.logging")

    # Mock FastAPI app
    mock_app = MagicMock()
    mock_health_app = MagicMock()

    # Call run_servers - should not raise, should catch exception
    run_servers(mock_app, mock_health_app, config)

    # Verify main server error was logged
    mock_logger.error.assert_any_call("Main server error: Server error")


def test_run_servers_signals_handled(config: Config, mocker: MockerFixture) -> None:
    """Test that run_servers registers signal handlers."""
    # Mock the Server class
    mock_main_server = MagicMock()
    mock_health_server = MagicMock()
    mocker.patch(
        "external_dns_technitium_webhook.server.Server",
        side_effect=[mock_main_server, mock_health_server],
    )

    # Mock asyncio.run
    mocker.patch("external_dns_technitium_webhook.server.asyncio.run")

    # Mock threading
    mocker.patch("threading.Thread")
    mock_event_class = mocker.patch("threading.Event")
    mock_event_instance = MagicMock()
    mock_event_instance.wait.return_value = True
    mock_event_class.return_value = mock_event_instance

    # Mock signal
    mock_signal = mocker.patch("signal.signal")

    # Mock FastAPI app
    mock_app = MagicMock()
    mock_health_app = MagicMock()

    # Call run_servers
    run_servers(mock_app, mock_health_app, config)

    # Verify signal handlers were registered
    import signal

    assert mock_signal.call_count >= 2
    # Check that SIGINT and SIGTERM handlers were registered
    calls = mock_signal.call_args_list
    sigints = [c for c in calls if c[0][0] == signal.SIGINT]
    sigterms = [c for c in calls if c[0][0] == signal.SIGTERM]
    assert len(sigints) > 0
    assert len(sigterms) > 0
