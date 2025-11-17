"""Tests for server logic (run_servers, threading, entrypoint)."""

import signal
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI

import external_dns_technitium_webhook.server as server_mod
from external_dns_technitium_webhook.config import Config as AppConfig


@pytest.fixture
def config():
    """Provide a test configuration."""
    return AppConfig(
        technitium_url="http://localhost:5380",
        technitium_username="admin",
        technitium_password="password",
        zone="example.com",
        domain_filters="example.com",
    )


def test_run_servers_starts_both_servers(mocker, config):
    """Test that run_servers starts both main and health servers."""
    app = FastAPI()
    health_app = FastAPI()
    mock_server = mocker.patch("external_dns_technitium_webhook.server.Server")
    mock_server.return_value.serve = mocker.AsyncMock()
    mocker.patch("external_dns_technitium_webhook.server.UvicornConfig")
    mock_thread = mocker.patch("external_dns_technitium_webhook.server.threading.Thread")
    mock_asyncio_run = mocker.patch("external_dns_technitium_webhook.server.asyncio.run")
    mocker.patch("external_dns_technitium_webhook.server.signal.signal")
    mock_event = mocker.patch("external_dns_technitium_webhook.server.threading.Event")
    mock_event.return_value.wait.return_value = True

    server_mod.run_servers(app, health_app, config)

    # Verify health thread was started
    mock_thread.return_value.start.assert_called_once()
    # Verify main server was started
    mock_asyncio_run.assert_called_once()


def test_run_servers_signal_handler(mocker, config):
    """Test that signal handler sets shutdown event and server flags."""
    app = FastAPI()
    health_app = FastAPI()
    mock_server = mocker.patch("external_dns_technitium_webhook.server.Server")
    # Use Mock instead of AsyncMock to avoid un-awaited coroutine when signal handler is called
    mock_server.return_value.serve = mocker.Mock()
    mocker.patch("external_dns_technitium_webhook.server.UvicornConfig")
    mocker.patch("external_dns_technitium_webhook.server.threading.Thread")
    mocker.patch("external_dns_technitium_webhook.server.asyncio.run")
    mock_signal = mocker.patch("external_dns_technitium_webhook.server.signal.signal")
    mock_event = mocker.patch("external_dns_technitium_webhook.server.threading.Event")
    mock_event.return_value.wait.return_value = True
    mock_logging = mocker.patch("external_dns_technitium_webhook.server.logging.info")

    server_mod.run_servers(app, health_app, config)

    # Get the signal handler from the mock calls
    signal_handler = mock_signal.call_args_list[0][0][1]

    # Call the signal handler
    signal_handler(15, None)

    # Verify logging was called
    assert any("Received signal" in str(call) for call in mock_logging.call_args_list)


def test_run_servers_health_thread_exception(mocker, config):
    """Test that health server exceptions are logged in health thread."""
    app = FastAPI()
    health_app = FastAPI()
    mock_server = mocker.patch("external_dns_technitium_webhook.server.Server")

    # Create a mock that will be used in the health thread
    mock_health_serve = mocker.AsyncMock(side_effect=Exception("Health server error"))

    # Track which server instance is created (main vs health)
    server_instances = []

    def create_server(config):
        instance = mocker.Mock()
        if len(server_instances) == 0:
            # First call is main server
            instance.serve = mocker.AsyncMock()
        else:
            # Second call is health server
            instance.serve = mock_health_serve
        server_instances.append(instance)
        return instance

    mock_server.side_effect = create_server
    mocker.patch("external_dns_technitium_webhook.server.UvicornConfig")

    # Capture the thread target function
    thread_target = None

    def capture_thread(*args, **kwargs):
        nonlocal thread_target
        thread_target = kwargs.get("target")
        mock_thread = mocker.Mock()
        mock_thread.start = mocker.Mock()
        mock_thread.join = mocker.Mock()
        return mock_thread

    mocker.patch(
        "external_dns_technitium_webhook.server.threading.Thread", side_effect=capture_thread
    )
    mocker.patch("external_dns_technitium_webhook.server.asyncio.run")
    mocker.patch("external_dns_technitium_webhook.server.signal.signal")
    mock_event = mocker.patch("external_dns_technitium_webhook.server.threading.Event")
    mock_event.return_value.wait.return_value = False
    mock_logging_error = mocker.patch("external_dns_technitium_webhook.server.logging.error")
    mock_loop = mocker.Mock()
    mock_loop.run_until_complete = mocker.Mock(side_effect=Exception("Health server error"))
    mock_loop.close = mocker.Mock()
    mocker.patch(
        "external_dns_technitium_webhook.server.asyncio.new_event_loop", return_value=mock_loop
    )
    mocker.patch("external_dns_technitium_webhook.server.asyncio.set_event_loop")

    server_mod.run_servers(app, health_app, config)

    # Verify health server failed to start was logged
    assert any(
        "Health server failed to start" in str(call) for call in mock_logging_error.call_args_list
    )


def test_run_servers_main_server_exception(mocker, config):
    """Test that main server exceptions are logged."""
    app = FastAPI()
    health_app = FastAPI()
    mock_server = mocker.patch("external_dns_technitium_webhook.server.Server")
    # Don't use AsyncMock - asyncio.run is mocked so the coroutine won't be awaited properly
    mock_server.return_value.serve = mocker.Mock()
    mocker.patch("external_dns_technitium_webhook.server.UvicornConfig")
    mock_thread = mocker.patch("external_dns_technitium_webhook.server.threading.Thread")
    mock_asyncio_run = mocker.patch("external_dns_technitium_webhook.server.asyncio.run")
    mock_asyncio_run.side_effect = Exception("Main server error")
    mocker.patch("external_dns_technitium_webhook.server.signal.signal")
    mock_event = mocker.patch("external_dns_technitium_webhook.server.threading.Event")
    mock_event.return_value.wait.return_value = True
    mock_logging_error = mocker.patch("external_dns_technitium_webhook.server.logging.error")

    server_mod.run_servers(app, health_app, config)

    # Verify error was logged
    mock_logging_error.assert_called_once()
    assert "Main server error" in str(mock_logging_error.call_args)
    # Verify thread join was called in finally block
    mock_thread.return_value.join.assert_called_once_with(timeout=5)


def test_run_health_server_success(mocker, config):
    """Test that run_health_server starts successfully."""
    health_app = FastAPI()
    mock_server = mocker.patch("external_dns_technitium_webhook.server.Server")
    # Don't use AsyncMock when mocking run_until_complete - use Mock to avoid creating un-awaited coroutines
    mock_server.return_value.serve = mocker.Mock()
    mocker.patch("external_dns_technitium_webhook.server.UvicornConfig")
    mock_loop = mocker.Mock()
    mock_loop.run_until_complete = mocker.Mock()
    mock_loop.close = mocker.Mock()
    mocker.patch(
        "external_dns_technitium_webhook.server.asyncio.new_event_loop", return_value=mock_loop
    )
    mocker.patch("external_dns_technitium_webhook.server.asyncio.set_event_loop")
    mock_logging = mocker.patch("external_dns_technitium_webhook.server.logging.info")

    server_mod.run_health_server(health_app, config)

    # Verify loop was created and used
    mock_loop.run_until_complete.assert_called_once()
    mock_loop.close.assert_called_once()
    # Verify logging was called
    assert any("[HEALTH]" in str(call) for call in mock_logging.call_args_list)


def test_run_health_server_exception_in_serve(mocker, config):
    """Test that run_health_server handles exceptions from serve()."""
    health_app = FastAPI()
    mock_server = mocker.patch("external_dns_technitium_webhook.server.Server")
    # Don't use AsyncMock when mocking run_until_complete - use Mock to avoid creating un-awaited coroutines
    mock_server.return_value.serve = mocker.Mock()
    mocker.patch("external_dns_technitium_webhook.server.UvicornConfig")
    mock_loop = mocker.Mock()
    mock_loop.run_until_complete = mocker.Mock(side_effect=Exception("Serve failed"))
    mock_loop.close = mocker.Mock()
    mocker.patch(
        "external_dns_technitium_webhook.server.asyncio.new_event_loop", return_value=mock_loop
    )
    mocker.patch("external_dns_technitium_webhook.server.asyncio.set_event_loop")
    mock_logging_error = mocker.patch("external_dns_technitium_webhook.server.logging.error")

    server_mod.run_health_server(health_app, config)

    # Verify error was logged
    assert any(
        "Health server serve error" in str(call) for call in mock_logging_error.call_args_list
    )
    mock_loop.close.assert_called_once()


def test_run_health_server_outer_exception(mocker, config):
    """Test that run_health_server handles outer exceptions."""
    health_app = FastAPI()
    mocker.patch("external_dns_technitium_webhook.server.Server")
    mocker.patch("external_dns_technitium_webhook.server.UvicornConfig")
    mock_new_event_loop = mocker.patch(
        "external_dns_technitium_webhook.server.asyncio.new_event_loop"
    )
    mock_new_event_loop.side_effect = Exception("Loop creation failed")
    mock_logging_error = mocker.patch("external_dns_technitium_webhook.server.logging.error")

    server_mod.run_health_server(health_app, config)

    # Verify outer error was logged
    assert any("Health server error" in str(call) for call in mock_logging_error.call_args_list)


def test_run_health_server_system_exit_in_serve(mocker, config):
    """Test that run_health_server handles SystemExit from serve()."""
    health_app = FastAPI()
    mock_server = mocker.patch("external_dns_technitium_webhook.server.Server")
    # Don't use AsyncMock when mocking run_until_complete - use Mock to avoid creating un-awaited coroutines
    mock_server.return_value.serve = mocker.Mock()
    mocker.patch("external_dns_technitium_webhook.server.UvicornConfig")
    mock_loop = mocker.Mock()
    # SystemExit is a BaseException, not Exception, so it's caught by our BaseException handler
    mock_loop.run_until_complete = mocker.Mock(side_effect=SystemExit(1))
    mock_loop.close = mocker.Mock()
    mocker.patch(
        "external_dns_technitium_webhook.server.asyncio.new_event_loop", return_value=mock_loop
    )
    mocker.patch("external_dns_technitium_webhook.server.asyncio.set_event_loop")
    mock_logging_error = mocker.patch("external_dns_technitium_webhook.server.logging.error")

    server_mod.run_health_server(health_app, config)

    # Verify SystemExit was handled and logged
    assert any(
        "Health server serve error" in str(call) for call in mock_logging_error.call_args_list
    )
    mock_loop.close.assert_called_once()


# Additional comprehensive tests for run_servers function


def test_run_servers_happy_path(mocker, config):
    """Test the happy path where both servers start and run successfully."""
    app = FastAPI()
    health_app = FastAPI()

    mock_health_server = MagicMock()
    mock_main_server = MagicMock()

    def server_factory(config_obj):
        if config_obj.port == config.health_port:
            return mock_health_server
        return mock_main_server

    mocker.patch("external_dns_technitium_webhook.server.Server", side_effect=server_factory)
    mocker.patch("external_dns_technitium_webhook.server.UvicornConfig")

    mock_thread = MagicMock()
    mocker.patch(
        "external_dns_technitium_webhook.server.threading.Thread", return_value=mock_thread
    )

    mock_event = MagicMock()
    mock_event.wait.return_value = False
    mocker.patch("external_dns_technitium_webhook.server.threading.Event", return_value=mock_event)

    mock_asyncio_run = mocker.patch("external_dns_technitium_webhook.server.asyncio.run")
    mocker.patch("external_dns_technitium_webhook.server.signal.signal")

    server_mod.run_servers(app, health_app, config)

    mock_thread.start.assert_called_once()
    mock_asyncio_run.assert_called_once()
    mock_thread.join.assert_called_once()


def test_run_servers_signal_handlers(mocker, config):
    """Test that signal handlers are registered correctly."""
    app = FastAPI()
    health_app = FastAPI()

    mock_health_server = MagicMock()
    mock_main_server = MagicMock()

    def server_factory(config_obj):
        if config_obj.port == config.health_port:
            return mock_health_server
        return mock_main_server

    mocker.patch("external_dns_technitium_webhook.server.Server", side_effect=server_factory)
    mocker.patch("external_dns_technitium_webhook.server.UvicornConfig")

    mock_thread = MagicMock()
    mocker.patch(
        "external_dns_technitium_webhook.server.threading.Thread", return_value=mock_thread
    )

    mock_event = MagicMock()
    mock_event.wait.return_value = False
    mocker.patch("external_dns_technitium_webhook.server.threading.Event", return_value=mock_event)

    mocker.patch("external_dns_technitium_webhook.server.asyncio.run")
    mock_signal = mocker.patch("external_dns_technitium_webhook.server.signal.signal")

    server_mod.run_servers(app, health_app, config)

    assert mock_signal.call_count >= 2
    signal_calls = [call[0][0] for call in mock_signal.call_args_list]
    assert signal.SIGTERM in signal_calls
    assert signal.SIGINT in signal_calls


def test_run_servers_health_server_timeout(mocker, config):
    """Test health server timeout during startup (wait returns False = timeout)."""
    app = FastAPI()
    health_app = FastAPI()

    mock_health_server = MagicMock()
    mock_main_server = MagicMock()

    def server_factory(config_obj):
        if config_obj.port == config.health_port:
            return mock_health_server
        return mock_main_server

    mocker.patch("external_dns_technitium_webhook.server.Server", side_effect=server_factory)
    mocker.patch("external_dns_technitium_webhook.server.UvicornConfig")

    mock_thread = MagicMock()
    mocker.patch(
        "external_dns_technitium_webhook.server.threading.Thread", return_value=mock_thread
    )

    mock_event = MagicMock()
    # wait() returns False on timeout
    mock_event.wait.return_value = False
    mocker.patch("external_dns_technitium_webhook.server.threading.Event", return_value=mock_event)

    mocker.patch("external_dns_technitium_webhook.server.asyncio.run")
    mocker.patch("external_dns_technitium_webhook.server.signal.signal")
    mock_logging_error = mocker.patch("external_dns_technitium_webhook.server.logging.error")

    server_mod.run_servers(app, health_app, config)

    # When wait() returns False, an error is logged about timeout
    assert any(
        "Health server failed to start (timeout" in str(call)
        for call in mock_logging_error.call_args_list
    )


def test_run_servers_main_server_exception_with_health_timeout(mocker, config):
    """Test exception handling during main server execution when health times out."""
    app = FastAPI()
    health_app = FastAPI()

    mock_health_server = MagicMock()
    mock_main_server = MagicMock()

    def server_factory(config_obj):
        if config_obj.port == config.health_port:
            return mock_health_server
        return mock_main_server

    mocker.patch("external_dns_technitium_webhook.server.Server", side_effect=server_factory)
    mocker.patch("external_dns_technitium_webhook.server.UvicornConfig")

    mock_thread = MagicMock()
    mocker.patch(
        "external_dns_technitium_webhook.server.threading.Thread", return_value=mock_thread
    )

    mock_event = MagicMock()
    # wait() returns False on timeout
    mock_event.wait.return_value = False
    mocker.patch("external_dns_technitium_webhook.server.threading.Event", return_value=mock_event)

    mock_asyncio_run = mocker.patch("external_dns_technitium_webhook.server.asyncio.run")
    mock_asyncio_run.side_effect = Exception("Simulated main server error")
    mocker.patch("external_dns_technitium_webhook.server.signal.signal")
    mock_logging_error = mocker.patch("external_dns_technitium_webhook.server.logging.error")

    server_mod.run_servers(app, health_app, config)

    # Two errors: health timeout + main server error
    assert len(mock_logging_error.call_args_list) == 2
    assert "Health server failed to start (timeout" in str(mock_logging_error.call_args_list[0])
    assert "Simulated main server error" in str(mock_logging_error.call_args_list[1])
    mock_thread.join.assert_called_once()


def test_run_servers_signals_handled(mocker, config):
    """Test that signals trigger graceful shutdown."""
    app = FastAPI()
    health_app = FastAPI()

    mock_health_server = MagicMock()
    mock_main_server = MagicMock()

    def server_factory(config_obj):
        if config_obj.port == config.health_port:
            return mock_health_server
        return mock_main_server

    mocker.patch("external_dns_technitium_webhook.server.Server", side_effect=server_factory)
    mocker.patch("external_dns_technitium_webhook.server.UvicornConfig")

    mock_thread = MagicMock()
    mocker.patch(
        "external_dns_technitium_webhook.server.threading.Thread", return_value=mock_thread
    )

    mock_event = MagicMock()
    mock_event.wait.return_value = False
    mocker.patch("external_dns_technitium_webhook.server.threading.Event", return_value=mock_event)

    mocker.patch("external_dns_technitium_webhook.server.asyncio.run")

    captured_handlers = {}

    def capture_signal(sig, handler):
        captured_handlers[sig] = handler

    mocker.patch("external_dns_technitium_webhook.server.signal.signal", side_effect=capture_signal)

    server_mod.run_servers(app, health_app, config)

    assert signal.SIGTERM in captured_handlers
    assert signal.SIGINT in captured_handlers

    handler = captured_handlers[signal.SIGTERM]
    handler(signal.SIGTERM, None)

    mock_event.set.assert_called()
    assert mock_health_server.should_exit is True
    assert mock_main_server.should_exit is True
