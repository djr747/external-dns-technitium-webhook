"""Unit tests for Prometheus metrics module and integration."""

import contextlib
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY

from external_dns_technitium_webhook.technitium_client import (
    InvalidTokenError,
    TechnitiumClient,
    TechnitiumError,
)


@pytest.fixture(autouse=True)
def reset_prometheus_metrics():
    """Reset Prometheus metrics between tests without reloading the module.

    Re-registers each collector so its internal state is cleared without
    breaking the object references already held by handlers.py and
    technitium_client.py.
    """
    from external_dns_technitium_webhook import metrics as m

    collectors = [
        m.dns_records_processed_total,
        m.technitium_latency_seconds,
        m.webhook_ready,
        m.api_errors_total,
        m.dns_records_total,
    ]

    for collector in collectors:
        with contextlib.suppress(ValueError):
            REGISTRY.unregister(collector)
        REGISTRY.register(collector)

    yield


class TestMetricsEndpoint:
    """Test the /metrics endpoint on the health server."""

    def test_metrics_endpoint_returns_200(self, mocker):
        """Test that /metrics endpoint returns 200."""
        mocker.patch(
            "external_dns_technitium_webhook.health.is_main_server_ready",
            return_value=True,
        )
        from external_dns_technitium_webhook.health import create_health_app

        app = create_health_app()
        client = TestClient(app)
        response = client.get("/metrics")
        assert response.status_code == 200

    def test_metrics_endpoint_content_type(self, mocker):
        """Test that /metrics endpoint returns Prometheus content type."""
        mocker.patch(
            "external_dns_technitium_webhook.health.is_main_server_ready",
            return_value=True,
        )
        from external_dns_technitium_webhook.health import create_health_app

        app = create_health_app()
        client = TestClient(app)
        response = client.get("/metrics")
        assert "text/plain" in response.headers["content-type"]

    def test_metrics_endpoint_contains_prometheus_format(self, mocker):
        """Test that /metrics output contains valid Prometheus format."""
        mocker.patch(
            "external_dns_technitium_webhook.health.is_main_server_ready",
            return_value=True,
        )
        from external_dns_technitium_webhook.health import create_health_app

        app = create_health_app()
        client = TestClient(app)
        response = client.get("/metrics")
        # Prometheus format includes HELP and TYPE lines
        assert b"# HELP" in response.content
        assert b"# TYPE" in response.content

    def test_metrics_endpoint_contains_webhook_metrics(self, mocker):
        """Test that /metrics output contains webhook-specific metrics."""
        mocker.patch(
            "external_dns_technitium_webhook.health.is_main_server_ready",
            return_value=True,
        )
        from external_dns_technitium_webhook.health import create_health_app

        app = create_health_app()
        client = TestClient(app)
        response = client.get("/metrics")
        content = response.content
        # Check all 5 required metric names are present
        assert b"webhook_dns_records_processed_total" in content
        assert b"webhook_technitium_latency_seconds" in content
        assert b"webhook_ready" in content
        assert b"webhook_api_errors_total" in content
        assert b"webhook_dns_records_total" in content


class TestMetricsModule:
    """Test the metrics module objects directly."""

    def test_metrics_module_has_all_required_metrics(self):
        """Test that metrics module exports all required metric objects."""
        from external_dns_technitium_webhook.metrics import (
            api_errors_total,
            dns_records_processed_total,
            dns_records_total,
            technitium_latency_seconds,
            webhook_ready,
        )

        assert dns_records_processed_total is not None
        assert technitium_latency_seconds is not None
        assert webhook_ready is not None
        assert api_errors_total is not None
        assert dns_records_total is not None

    def test_dns_records_processed_counter_labels(self):
        """Test that dns_records_processed_total counter accepts correct labels."""
        from external_dns_technitium_webhook.metrics import dns_records_processed_total

        dns_records_processed_total.labels(operation="create").inc()
        dns_records_processed_total.labels(operation="delete").inc()

    def test_api_errors_counter_labels(self):
        """Test that api_errors_total counter accepts correct labels."""
        from external_dns_technitium_webhook.metrics import api_errors_total

        api_errors_total.labels(error_type="invalid_token").inc()
        api_errors_total.labels(error_type="timeout").inc()
        api_errors_total.labels(error_type="connection_error").inc()

    def test_technitium_latency_histogram_labels(self):
        """Test that technitium_latency_seconds histogram accepts correct labels."""
        from external_dns_technitium_webhook.metrics import technitium_latency_seconds

        technitium_latency_seconds.labels(operation="login").observe(0.1)
        technitium_latency_seconds.labels(operation="get_records").observe(0.2)
        technitium_latency_seconds.labels(operation="add_record").observe(0.05)
        technitium_latency_seconds.labels(operation="delete_record").observe(0.03)

    def test_webhook_ready_gauge_set(self):
        """Test that webhook_ready gauge can be set to 0 and 1."""
        from external_dns_technitium_webhook.metrics import webhook_ready

        webhook_ready.set(0)
        webhook_ready.set(1)

    def test_dns_records_total_gauge_set(self):
        """Test that dns_records_total gauge can be set."""
        from external_dns_technitium_webhook.metrics import dns_records_total

        dns_records_total.set(42)


class TestHandlerMetricsIntegration:
    """Test that handlers correctly update metrics."""

    @pytest.mark.asyncio
    async def test_health_check_ready_sets_gauge(self, mocker):
        """Test that health_check sets webhook_ready=1 when ready."""
        from external_dns_technitium_webhook.handlers import health_check
        from external_dns_technitium_webhook.metrics import webhook_ready

        state = MagicMock()
        state.is_ready = True

        mock_set = mocker.patch.object(webhook_ready, "set")
        await health_check(state)
        mock_set.assert_called_with(1)

    @pytest.mark.asyncio
    async def test_health_check_not_ready_sets_gauge(self, mocker):
        """Test that health_check sets webhook_ready=0 when not ready."""
        from external_dns_technitium_webhook.handlers import health_check
        from external_dns_technitium_webhook.metrics import webhook_ready

        state = MagicMock()
        state.is_ready = False

        mock_set = mocker.patch.object(webhook_ready, "set")
        await health_check(state)
        mock_set.assert_called_with(0)

    @pytest.mark.asyncio
    async def test_get_records_updates_dns_records_total(self, mocker):
        """Test that get_records updates dns_records_total gauge."""
        from external_dns_technitium_webhook.handlers import get_records
        from external_dns_technitium_webhook.metrics import dns_records_total
        from external_dns_technitium_webhook.models import GetRecordsResponse, RecordInfo, ZoneInfo

        state = MagicMock()
        state.is_ready = True
        state.ensure_ready = AsyncMock()
        state.record_fetch_count = 0
        state.config.zone = "example.com"

        mock_response = GetRecordsResponse(
            zone=ZoneInfo(name="example.com", type="Primary", disabled=False),
            records=[
                RecordInfo(
                    name="a.example.com",
                    type="A",
                    ttl=300,
                    disabled=False,
                    rData={"ipAddress": "192.0.2.1"},
                ),
                RecordInfo(
                    name="b.example.com",
                    type="A",
                    ttl=300,
                    disabled=False,
                    rData={"ipAddress": "192.0.2.2"},
                ),
            ],
        )
        state.client.get_records = AsyncMock(return_value=mock_response)

        mock_set = mocker.patch.object(dns_records_total, "set")

        response = await get_records(state)
        # consume the streaming response
        if hasattr(response, "body_iterator"):
            async for _ in response.body_iterator:
                pass

        mock_set.assert_called_once_with(2)

    @pytest.mark.asyncio
    async def test_apply_record_increments_create_counter(self, mocker):
        """Test that apply_record increments dns_records_processed_total for create."""
        from external_dns_technitium_webhook.models import Changes, Endpoint

        state = MagicMock()
        state.is_ready = True
        state.is_writable = True
        state.ensure_ready = AsyncMock()
        state.ensure_writable = AsyncMock()
        state.client.add_record = AsyncMock()
        state.client.delete_record = AsyncMock()

        changes = Changes(
            create=[
                Endpoint(
                    dnsName="test.example.com",
                    recordType="A",
                    recordTTL=300,
                    setIdentifier="",
                    targets=["192.0.2.1"],
                )
            ],
            delete=[],
            updateOld=[],
            updateNew=[],
        )

        # Patch the counter at the handlers module level so the handler uses our mock
        mock_counter = MagicMock()
        mocker.patch(
            "external_dns_technitium_webhook.handlers.dns_records_processed_total",
            mock_counter,
        )

        from external_dns_technitium_webhook.handlers import apply_record

        await apply_record(state, changes)
        mock_counter.labels.assert_called_with(operation="create")
        mock_counter.labels.return_value.inc.assert_called_once()

    @pytest.mark.asyncio
    async def test_apply_record_increments_delete_counter(self, mocker):
        """Test that apply_record increments dns_records_processed_total for delete."""
        from external_dns_technitium_webhook.models import Changes, Endpoint

        state = MagicMock()
        state.is_ready = True
        state.is_writable = True
        state.ensure_ready = AsyncMock()
        state.ensure_writable = AsyncMock()
        state.client.add_record = AsyncMock()
        state.client.delete_record = AsyncMock()

        changes = Changes(
            create=[],
            delete=[
                Endpoint(
                    dnsName="test.example.com",
                    recordType="A",
                    recordTTL=300,
                    setIdentifier="",
                    targets=["192.0.2.1"],
                )
            ],
            updateOld=[],
            updateNew=[],
        )

        # Patch the counter at the handlers module level so the handler uses our mock
        mock_counter = MagicMock()
        mocker.patch(
            "external_dns_technitium_webhook.handlers.dns_records_processed_total",
            mock_counter,
        )

        from external_dns_technitium_webhook.handlers import apply_record

        await apply_record(state, changes)
        mock_counter.labels.assert_called_with(operation="delete")
        mock_counter.labels.return_value.inc.assert_called_once()

    @pytest.mark.asyncio
    async def test_apply_record_increments_error_counter_on_create_failure(self, mocker):
        """Test that apply_record increments api_errors_total on create failure."""
        from fastapi import HTTPException

        from external_dns_technitium_webhook.models import Changes, Endpoint

        state = MagicMock()
        state.is_ready = True
        state.is_writable = True
        state.ensure_ready = AsyncMock()
        state.ensure_writable = AsyncMock()
        state.client.add_record = AsyncMock(side_effect=Exception("API error"))
        state.client.delete_record = AsyncMock()

        changes = Changes(
            create=[
                Endpoint(
                    dnsName="test.example.com",
                    recordType="A",
                    recordTTL=300,
                    setIdentifier="",
                    targets=["192.0.2.1"],
                )
            ],
            delete=[],
            updateOld=[],
            updateNew=[],
        )

        # Patch the error counter at the handlers module level
        mock_error_counter = MagicMock()
        mocker.patch(
            "external_dns_technitium_webhook.handlers.api_errors_total",
            mock_error_counter,
        )

        from external_dns_technitium_webhook.handlers import apply_record

        with pytest.raises(HTTPException):
            await apply_record(state, changes)

        mock_error_counter.labels.assert_called_with(error_type="connection_error")
        mock_error_counter.labels.return_value.inc.assert_called_once()

    @pytest.mark.asyncio
    async def test_apply_record_increments_error_counter_on_delete_failure(self, mocker):
        """Test that apply_record increments api_errors_total on delete failure."""
        from fastapi import HTTPException

        from external_dns_technitium_webhook.models import Changes, Endpoint

        state = MagicMock()
        state.is_ready = True
        state.is_writable = True
        state.ensure_ready = AsyncMock()
        state.ensure_writable = AsyncMock()
        state.client.add_record = AsyncMock()
        state.client.delete_record = AsyncMock(side_effect=Exception("Delete failed"))

        changes = Changes(
            create=[],
            delete=[
                Endpoint(
                    dnsName="test.example.com",
                    recordType="A",
                    recordTTL=300,
                    setIdentifier="",
                    targets=["192.0.2.1"],
                )
            ],
            updateOld=[],
            updateNew=[],
        )

        # Patch the error counter at the handlers module level
        mock_error_counter = MagicMock()
        mocker.patch(
            "external_dns_technitium_webhook.handlers.api_errors_total",
            mock_error_counter,
        )

        from external_dns_technitium_webhook.handlers import apply_record

        with pytest.raises(HTTPException):
            await apply_record(state, changes)

        mock_error_counter.labels.assert_called_with(error_type="connection_error")
        mock_error_counter.labels.return_value.inc.assert_called_once()


class TestTechnitiumClientMetrics:
    """Test that TechnitiumClient correctly tracks metrics."""

    @pytest.mark.asyncio
    async def test_login_tracks_latency(self, mocker):
        """Test that login tracks latency via the histogram context manager."""
        client = TechnitiumClient(base_url="http://localhost:5380")

        mock_post_raw = mocker.patch.object(
            client,
            "_post_raw",
            return_value={
                "status": "ok",
                "token": "test-token",
                "username": "admin",
                "displayName": "Admin",
            },
        )
        # Patch _track_latency at the module level to verify it is called with "login"
        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=mock_ctx)
        mock_ctx.__exit__ = MagicMock(return_value=False)
        mock_track = mocker.patch(
            "external_dns_technitium_webhook.technitium_client._track_latency",
            return_value=mock_ctx,
        )

        await client.login("admin", "password")

        mock_post_raw.assert_called_once()
        mock_track.assert_called_once_with("login")

    @pytest.mark.asyncio
    async def test_invalid_token_increments_error_counter(self, mocker):
        """Test that invalid-token response increments api_errors_total."""
        client = TechnitiumClient(base_url="http://localhost:5380")
        client.token = "test-token"

        mocker.patch.object(
            client._client,
            "post",
            return_value=mocker.Mock(
                status_code=200,
                json=mocker.Mock(return_value={"status": "invalid-token"}),
                raise_for_status=mocker.Mock(),
            ),
        )

        # Patch api_errors_total at the technitium_client module level
        mock_error_counter = MagicMock()
        mocker.patch(
            "external_dns_technitium_webhook.technitium_client.api_errors_total",
            mock_error_counter,
        )

        with pytest.raises(InvalidTokenError):
            await client._post_raw("/api/test", {"key": "value"})

        mock_error_counter.labels.assert_called_with(error_type="invalid_token")
        mock_error_counter.labels.return_value.inc.assert_called_once()

    @pytest.mark.asyncio
    async def test_timeout_increments_error_counter(self, mocker):
        """Test that timeout exception increments api_errors_total with timeout label."""
        import httpx

        client = TechnitiumClient(base_url="http://localhost:5380")
        client.token = "test-token"

        mocker.patch.object(
            client._client,
            "post",
            side_effect=httpx.TimeoutException("Connection timed out"),
        )

        # Patch api_errors_total at the technitium_client module level
        mock_error_counter = MagicMock()
        mocker.patch(
            "external_dns_technitium_webhook.technitium_client.api_errors_total",
            mock_error_counter,
        )

        with pytest.raises(TechnitiumError):
            await client._post_raw("/api/test", {"key": "value"})

        mock_error_counter.labels.assert_called_with(error_type="timeout")
        mock_error_counter.labels.return_value.inc.assert_called_once()

    @pytest.mark.asyncio
    async def test_connection_error_increments_error_counter(self, mocker):
        """Test that connection error increments api_errors_total with connection_error label."""
        import httpx

        client = TechnitiumClient(base_url="http://localhost:5380")
        client.token = "test-token"

        mocker.patch.object(
            client._client,
            "post",
            side_effect=httpx.ConnectError("Connection refused"),
        )

        # Patch api_errors_total at the technitium_client module level
        mock_error_counter = MagicMock()
        mocker.patch(
            "external_dns_technitium_webhook.technitium_client.api_errors_total",
            mock_error_counter,
        )

        with pytest.raises(TechnitiumError):
            await client._post_raw("/api/test", {"key": "value"})

        mock_error_counter.labels.assert_called_with(error_type="connection_error")
        mock_error_counter.labels.return_value.inc.assert_called_once()
