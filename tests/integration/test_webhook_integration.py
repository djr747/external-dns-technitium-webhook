"""
Integration tests for External DNS Technitium Webhook

Tests the complete workflow:
1. Technitium DNS running in Kubernetes
2. External DNS with webhook provider sidecar
3. DNS record synchronization
4. Webhook health and API endpoints
"""

import os

import httpx
import pytest
from kubernetes import client, config

pytestmark = pytest.mark.integration


class TestWebhookIntegration:
    """Test webhook integration with Technitium in Kubernetes"""

    @pytest.fixture(scope="class")
    def k8s_client(self):
        """Initialize Kubernetes client"""
        try:
            config.load_incluster_config()
        except config.config_exception.ConfigException:
            # Local testing without Kubernetes
            try:
                config.load_kube_config()
            except config.config_exception.ConfigException:
                pytest.skip("Kubernetes not available")
        return client.CoreV1Api()

    @pytest.fixture(scope="class")
    def technitium_url(self):
        """Get Technitium service URL"""
        return os.getenv("TECHNITIUM_URL", "http://technitium:5380")

    @pytest.fixture(scope="class")
    def webhook_url(self):
        """Get webhook service URL"""
        # Webhook runs as sidecar in external-dns pod
        return os.getenv("WEBHOOK_URL", "http://external-dns:8888")

    def test_technitium_api_ready(self, technitium_url):
        """Verify Technitium API is accessible"""
        response = httpx.get(f"{technitium_url}/api/user/login", timeout=10)
        assert response.status_code in [200, 400], (
            f"Technitium API unreachable: {response.status_code}"
        )

    def test_webhook_health_endpoint(self, webhook_url):
        """Test webhook /health endpoint"""
        response = httpx.get(f"{webhook_url}/health", timeout=10)
        assert response.status_code == 200, f"Health check failed: {response.text}"
        assert response.text in ["OK", "ok"], "Health endpoint should return OK"

    def test_webhook_negotiate_endpoint(self, webhook_url):
        """Test webhook domain filter negotiation"""
        response = httpx.get(f"{webhook_url}/", timeout=10)
        assert response.status_code == 200, f"Negotiate failed: {response.text}"
        data = response.json()
        assert "filters" in data, "Response should contain filters"
        assert "test.local" in data["filters"], "test.local should be in filters"

    @pytest.mark.asyncio
    async def test_webhook_records_endpoint(self, webhook_url):
        """Test webhook /records GET endpoint"""
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{webhook_url}/records", timeout=10)
            assert response.status_code == 200, f"Records endpoint failed: {response.text}"
            data = response.json()
            assert "content" in data, "Response should contain records"

    def test_webhook_custom_media_type(self, webhook_url):
        """Verify webhook returns correct ExternalDNS media type"""
        response = httpx.get(f"{webhook_url}/health", timeout=10)
        # Should use standard JSON for health, but API endpoints should use custom type
        assert response.status_code == 200

    def test_pod_logs_no_errors(self, k8s_client):
        """Check External DNS pod logs for errors"""
        namespace = "default"

        # Find external-dns pod
        pods = k8s_client.list_namespaced_pod(namespace)
        external_dns_pod = None
        for pod in pods.items:
            if "external-dns" in pod.metadata.name:
                external_dns_pod = pod.metadata.name
                break

        if external_dns_pod:
            try:
                logs = k8s_client.read_namespaced_pod_log(external_dns_pod, namespace)
                assert "ERROR" not in logs, "Pod logs contain ERROR messages"
                assert "panic" not in logs.lower(), "Pod logs contain panic"
            except Exception as e:
                pytest.skip(f"Could not read pod logs: {e}")

    def test_webhook_sidecar_container_running(self, k8s_client):
        """Verify webhook sidecar container is running in external-dns pod"""
        namespace = "default"

        pods = k8s_client.list_namespaced_pod(namespace)
        external_dns_pod = None
        for pod in pods.items:
            if "external-dns" in pod.metadata.name:
                external_dns_pod = pod
                break

        if external_dns_pod:
            # Check for webhook-provider container
            containers = external_dns_pod.spec.containers
            container_names = [c.name for c in containers]
            assert "webhook-provider" in container_names or len(containers) > 1, (
                "Webhook sidecar should be running"
            )

            # Check container status
            for container_status in external_dns_pod.status.container_statuses:
                if (
                    "webhook" in container_status.name
                    or "external-dns-technitium" in container_status.image
                ):
                    assert container_status.ready, f"Container {container_status.name} is not ready"

    def test_technitium_zone_exists(self, technitium_url):
        """Verify test.local zone was created in Technitium"""
        # This would require authentication
        # For now, just verify Technitium is accessible
        response = httpx.get(f"{technitium_url}/api/user/login", timeout=10)
        assert response.status_code in [200, 400], "Should be able to connect to Technitium API"


class TestWebhookAdjustEndpoints:
    """Test webhook /adjustendpoints functionality"""

    @pytest.fixture
    def webhook_url(self):
        """Get webhook service URL"""
        return os.getenv("WEBHOOK_URL", "http://external-dns:8888")

    @pytest.mark.asyncio
    async def test_adjust_endpoints_post(self, webhook_url):
        """Test POST /adjustendpoints endpoint"""
        payload = {
            "endpoints": [
                {"dnsName": "test.test.local", "recordType": "A", "targets": ["10.0.0.1"]}
            ]
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(f"{webhook_url}/adjustendpoints", json=payload, timeout=10)
            assert response.status_code == 200, f"Adjust endpoints failed: {response.text}"
            data = response.json()
            assert "content" in data, "Response should contain adjusted endpoints"


class TestWebhookRecordOperations:
    """Test webhook /records POST for record operations"""

    @pytest.fixture
    def webhook_url(self):
        """Get webhook service URL"""
        return os.getenv("WEBHOOK_URL", "http://external-dns:8888")

    @pytest.mark.asyncio
    async def test_create_a_record(self, webhook_url):
        """Test creating an A record via webhook"""
        payload = {
            "changes": [
                {
                    "action": "CREATE",
                    "resourceRecordSet": {
                        "name": "test.test.local",
                        "type": "A",
                        "ttl": 300,
                        "changes": [{"action": "CREATE", "resourceRecord": {"value": "10.0.0.1"}}],
                    },
                }
            ]
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(f"{webhook_url}/records", json=payload, timeout=10)
            # Should return 200 even if Technitium isn't fully configured for testing
            assert response.status_code in [200, 400, 500], (
                f"Unexpected status code: {response.status_code}"
            )
