"""Tests for health check endpoint and health server logic."""

from datetime import UTC, datetime

from external_dns_technitium_webhook.health import (
    create_health_app,
    is_main_server_ready,
    is_startup_delay_complete,
    set_health_server_start_time,
)


def test_set_and_check_startup_delay(mocker):
    """Test setting and checking startup delay."""
    # Record current time
    set_health_server_start_time()

    # Immediately check - should be complete since almost no time passed (but check within 1 second)
    mocker.patch(
        "external_dns_technitium_webhook.health.AppConfig",
        return_value=mocker.Mock(startup_delay_seconds=1.0),
    )
    assert not is_startup_delay_complete()

    # Wait for delay to pass
    import time

    time.sleep(1.1)
    assert is_startup_delay_complete()


def test_startup_delay_disabled(mocker):
    """Test that startup delay disabled (0 seconds) returns True immediately."""
    set_health_server_start_time()

    mocker.patch(
        "external_dns_technitium_webhook.health.AppConfig",
        return_value=mocker.Mock(startup_delay_seconds=0.0),
    )

    # Should be complete immediately when disabled
    assert is_startup_delay_complete()


def test_startup_delay_negative(mocker):
    """Test that negative startup delay returns True immediately."""
    set_health_server_start_time()

    mocker.patch(
        "external_dns_technitium_webhook.health.AppConfig",
        return_value=mocker.Mock(startup_delay_seconds=-1.0),
    )

    # Should be complete immediately when negative
    assert is_startup_delay_complete()


def test_startup_delay_not_set(mocker):
    """Test that startup delay returns True when start time not set."""
    # Reset the start time by directly manipulating the module state
    import external_dns_technitium_webhook.health as health_module

    health_module._health_server_start_time = None

    mocker.patch(
        "external_dns_technitium_webhook.health.AppConfig",
        return_value=mocker.Mock(startup_delay_seconds=10.0),
    )

    # Should be complete when start time not set (assume startup is complete)
    assert is_startup_delay_complete()


def test_health_endpoint_during_startup_delay(mocker):
    """Test health endpoint returns 503 during startup delay."""
    import external_dns_technitium_webhook.health as health_module

    # Set the start time to just now
    health_module._health_server_start_time = datetime.now(UTC)

    app = create_health_app()
    mocker.patch(
        "external_dns_technitium_webhook.health.AppConfig",
        return_value=mocker.Mock(startup_delay_seconds=10.0),
    )
    # Even though main server would be ready, health should return 503 during startup delay
    mocker.patch("external_dns_technitium_webhook.health.is_main_server_ready", return_value=True)

    from fastapi.testclient import TestClient

    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 503
    assert "starting up" in response.json()["detail"].lower()


def test_health_endpoint_ready(mocker):
    """Test health endpoint returns 200 when ready."""
    app = create_health_app()
    # Mock the entire health check function to return True
    mocker.patch("external_dns_technitium_webhook.health.is_main_server_ready", return_value=True)
    # Mock startup delay to be complete
    mocker.patch(
        "external_dns_technitium_webhook.health.is_startup_delay_complete", return_value=True
    )
    from fastapi.testclient import TestClient

    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200


def test_health_endpoint_not_ready(mocker):
    """Test health endpoint returns 503 when not ready."""
    app = create_health_app()
    # Mock the entire health check function to return False
    mocker.patch("external_dns_technitium_webhook.health.is_main_server_ready", return_value=False)
    # Mock startup delay to be complete
    mocker.patch(
        "external_dns_technitium_webhook.health.is_startup_delay_complete", return_value=True
    )
    from fastapi.testclient import TestClient

    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 503


def test_healthz_endpoint_during_startup_delay(mocker):
    """Test /healthz endpoint returns 503 during startup delay."""
    import external_dns_technitium_webhook.health as health_module

    # Set the start time to just now
    health_module._health_server_start_time = datetime.now(UTC)

    app = create_health_app()
    mocker.patch(
        "external_dns_technitium_webhook.health.AppConfig",
        return_value=mocker.Mock(startup_delay_seconds=10.0),
    )
    # Even though main server would be ready, healthz should return 503 during startup delay
    mocker.patch("external_dns_technitium_webhook.health.is_main_server_ready", return_value=True)

    from fastapi.testclient import TestClient

    client = TestClient(app)
    response = client.get("/healthz")
    assert response.status_code == 503
    assert "starting up" in response.json()["detail"].lower()


def test_healthz_endpoint_ready(mocker):
    """Test /healthz endpoint returns 200 when ready."""
    app = create_health_app()
    # Mock the entire health check function to return True
    mocker.patch("external_dns_technitium_webhook.health.is_main_server_ready", return_value=True)
    # Mock startup delay to be complete
    mocker.patch(
        "external_dns_technitium_webhook.health.is_startup_delay_complete", return_value=True
    )
    from fastapi.testclient import TestClient

    client = TestClient(app)
    response = client.get("/healthz")
    assert response.status_code == 200


def test_healthz_endpoint_not_ready(mocker):
    """Test /healthz endpoint returns 503 when not ready."""
    app = create_health_app()
    # Mock the entire health check function to return False
    mocker.patch("external_dns_technitium_webhook.health.is_main_server_ready", return_value=False)
    # Mock startup delay to be complete
    mocker.patch(
        "external_dns_technitium_webhook.health.is_startup_delay_complete", return_value=True
    )
    from fastapi.testclient import TestClient

    client = TestClient(app)
    response = client.get("/healthz")
    assert response.status_code == 503


def test_is_main_server_ready_success(mocker):
    """Test is_main_server_ready returns True when connection succeeds."""
    mocker.patch(
        "external_dns_technitium_webhook.health.AppConfig",
        return_value=mocker.Mock(listen_address="127.0.0.1", listen_port=8888),
    )
    mock_sock = mocker.Mock()
    mock_sock.connect_ex.return_value = 0
    mock_sock.close.return_value = None
    mocker.patch("socket.socket", return_value=mock_sock)

    result = is_main_server_ready()

    assert result is True
    mock_sock.connect_ex.assert_called_once()
    mock_sock.close.assert_called_once()


def test_is_main_server_ready_failure(mocker):
    """Test is_main_server_ready returns False when connection fails."""
    mocker.patch(
        "external_dns_technitium_webhook.health.AppConfig",
        return_value=mocker.Mock(listen_address="127.0.0.1", listen_port=8888),
    )
    mock_sock = mocker.Mock()
    mock_sock.connect_ex.return_value = 1
    mock_sock.close.return_value = None
    mocker.patch("socket.socket", return_value=mock_sock)

    result = is_main_server_ready()

    assert result is False
    mock_sock.connect_ex.assert_called_once()
    mock_sock.close.assert_called_once()


def test_is_main_server_ready_exception(mocker):
    """Test is_main_server_ready returns False when exception occurs."""
    mocker.patch(
        "external_dns_technitium_webhook.health.AppConfig",
        return_value=mocker.Mock(listen_address="127.0.0.1", listen_port=8888),
    )
    mocker.patch("socket.socket", side_effect=Exception("Connection error"))
    mock_logger = mocker.patch("external_dns_technitium_webhook.health.logging.warning")

    result = is_main_server_ready()

    assert result is False
    mock_logger.assert_called_once()
