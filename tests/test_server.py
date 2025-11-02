"""Tests for server logic (run_servers, threading, entrypoint)."""

from fastapi import FastAPI

import external_dns_technitium_webhook.server as server_mod
from external_dns_technitium_webhook.config import Config as AppConfig


def test_run_servers_starts_both_servers(mocker):
    """Test that run_servers starts both main and health servers."""
    app = FastAPI()
    health_app = FastAPI()
    config = AppConfig(
        technitium_url="http://localhost:5380",
        technitium_username="admin",
        technitium_password="password",
        zone="example.com",
        domain_filters="example.com",
    )
    mock_server = mocker.patch("external_dns_technitium_webhook.server.Server")
    mock_server.return_value.serve = mocker.AsyncMock()
    mocker.patch("external_dns_technitium_webhook.server.UvicornConfig")
    mock_thread = mocker.patch("external_dns_technitium_webhook.server.threading.Thread")
    mock_asyncio_run = mocker.patch("external_dns_technitium_webhook.server.asyncio.run")
    mock_signal = mocker.patch("external_dns_technitium_webhook.server.signal.signal")
    mock_time_sleep = mocker.patch("external_dns_technitium_webhook.server.time.sleep")

    server_mod.run_servers(app, health_app, config)

    # Verify signal handlers were registered
    assert mock_signal.call_count == 2
    # Verify health thread was started
    mock_thread.return_value.start.assert_called_once()
    # Verify time.sleep was called
    mock_time_sleep.assert_called_once_with(0.1)
    # Verify main server was started
    mock_asyncio_run.assert_called_once()


def test_run_servers_signal_handler(mocker):
    """Test that signal handler sets shutdown event and server flags."""
    app = FastAPI()
    health_app = FastAPI()
    config = AppConfig(
        technitium_url="http://localhost:5380",
        technitium_username="admin",
        technitium_password="password",
        zone="example.com",
        domain_filters="example.com",
    )
    mock_server = mocker.patch("external_dns_technitium_webhook.server.Server")
    mock_server.return_value.serve = mocker.AsyncMock()
    mocker.patch("external_dns_technitium_webhook.server.UvicornConfig")
    mocker.patch("external_dns_technitium_webhook.server.threading.Thread")
    mocker.patch("external_dns_technitium_webhook.server.asyncio.run")
    mock_signal = mocker.patch("external_dns_technitium_webhook.server.signal.signal")
    mocker.patch("external_dns_technitium_webhook.server.time.sleep")
    mock_logging = mocker.patch("external_dns_technitium_webhook.server.logging.info")

    server_mod.run_servers(app, health_app, config)

    # Get the signal handler from the mock calls
    signal_handler = mock_signal.call_args_list[0][0][1]

    # Call the signal handler
    signal_handler(15, None)

    # Verify logging was called
    assert any("Received signal" in str(call) for call in mock_logging.call_args_list)


def test_run_servers_health_thread_exception(mocker):
    """Test that health server exceptions are logged in health thread."""
    app = FastAPI()
    health_app = FastAPI()
    config = AppConfig(
        technitium_url="http://localhost:5380",
        technitium_username="admin",
        technitium_password="password",
        zone="example.com",
        domain_filters="example.com",
    )
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
    mocker.patch("external_dns_technitium_webhook.server.time.sleep")
    mock_logging_error = mocker.patch("external_dns_technitium_webhook.server.logging.error")
    mock_loop = mocker.Mock()
    mock_loop.run_until_complete = mocker.Mock(side_effect=Exception("Health server error"))
    mock_loop.close = mocker.Mock()
    mocker.patch(
        "external_dns_technitium_webhook.server.asyncio.new_event_loop", return_value=mock_loop
    )
    mocker.patch("external_dns_technitium_webhook.server.asyncio.set_event_loop")

    server_mod.run_servers(app, health_app, config)

    # Now call the captured thread target to exercise the health server exception path
    if thread_target:
        thread_target()
        mock_logging_error.assert_called()
        assert "Health server error" in str(mock_logging_error.call_args)
        mock_loop.close.assert_called_once()


def test_run_servers_main_server_exception(mocker):
    """Test that main server exceptions are logged."""
    app = FastAPI()
    health_app = FastAPI()
    config = AppConfig(
        technitium_url="http://localhost:5380",
        technitium_username="admin",
        technitium_password="password",
        zone="example.com",
        domain_filters="example.com",
    )
    mock_server = mocker.patch("external_dns_technitium_webhook.server.Server")
    mock_server.return_value.serve = mocker.AsyncMock()
    mocker.patch("external_dns_technitium_webhook.server.UvicornConfig")
    mock_thread = mocker.patch("external_dns_technitium_webhook.server.threading.Thread")
    mock_asyncio_run = mocker.patch("external_dns_technitium_webhook.server.asyncio.run")
    mock_asyncio_run.side_effect = Exception("Main server error")
    mocker.patch("external_dns_technitium_webhook.server.signal.signal")
    mocker.patch("external_dns_technitium_webhook.server.time.sleep")
    mock_logging_error = mocker.patch("external_dns_technitium_webhook.server.logging.error")

    server_mod.run_servers(app, health_app, config)

    # Verify error was logged
    mock_logging_error.assert_called_once()
    assert "Main server error" in str(mock_logging_error.call_args)
    # Verify thread join was called in finally block
    mock_thread.return_value.join.assert_called_once_with(timeout=5)
