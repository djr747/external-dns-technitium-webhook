"""Tests for health check endpoint and health server logic."""

from external_dns_technitium_webhook.health import create_health_app, is_main_server_ready


def test_health_endpoint_ready(mocker):
    """Test health endpoint returns 200 when ready."""
    app = create_health_app()
    # Mock the entire health check function to return True
    mocker.patch("external_dns_technitium_webhook.health.is_main_server_ready", return_value=True)
    from fastapi.testclient import TestClient

    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200


def test_health_endpoint_not_ready(mocker):
    """Test health endpoint returns 503 when not ready."""
    app = create_health_app()
    # Mock the entire health check function to return False
    mocker.patch("external_dns_technitium_webhook.health.is_main_server_ready", return_value=False)
    from fastapi.testclient import TestClient

    client = TestClient(app)
    response = client.get("/health")
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
