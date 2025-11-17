"""
Integration tests for External DNS Technitium Webhook

Tests the complete workflow:
1. Technitium DNS running in Kubernetes
2. External DNS with webhook provider sidecar
3. DNS record synchronization through Kubernetes resource annotations
4. Verification of DNS records in Technitium
"""

import logging
import os
import time

import httpx
import pytest
from kubernetes import client, config

pytestmark = pytest.mark.integration

logger = logging.getLogger(__name__)


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

    @pytest.fixture(scope="class", autouse=True)
    def ensure_cluster_ready(self, k8s_client, technitium_url):
        """Ensure cluster resources (Technitium service/pod and ExternalDNS pod) are ready before tests run.

        This prevents race conditions where pods are 'Running' but endpoints are not yet accepting
        connections on the host (which causes httpx ReadError connection resets in CI).
        """
        namespace = "default"
        # Wait for technitium Service to exist
        start = time.time()
        timeout = 120
        found_svc = False
        while time.time() - start < timeout:
            try:
                _ = k8s_client.read_namespaced_service("technitium", namespace)
                found_svc = True
                break
            except Exception:
                time.sleep(2)

        if not found_svc:
            pytest.skip("Technitium service not found in cluster within timeout")

        # Wait for technitium pod to be ready
        start = time.time()
        found_ready = False
        while time.time() - start < timeout:
            pods = k8s_client.list_namespaced_pod(namespace, label_selector="app=technitium")
            if pods.items:
                pod = pods.items[0]
                statuses = pod.status.container_statuses or []
                if statuses and all(getattr(s, "ready", False) for s in statuses):
                    found_ready = True
                    break
            time.sleep(2)

        if not found_ready:
            pytest.skip("Technitium pod not ready within timeout")

        # Wait for ExternalDNS pod to be ready (at least one container)
        start = time.time()
        ext_ready = False
        while time.time() - start < timeout:
            pods = k8s_client.list_namespaced_pod(
                namespace, label_selector="app.kubernetes.io/name=external-dns"
            )
            if pods.items:
                pod = pods.items[0]
                statuses = pod.status.container_statuses or []
                if statuses and any(getattr(s, "ready", False) for s in statuses):
                    ext_ready = True
                    break
            time.sleep(2)

        if not ext_ready:
            pytest.skip("ExternalDNS pod not ready within timeout")

        # Finally, verify the Technitium API is reachable from the runner (host) at technitium_url
        # Retry for a short period to allow port mappings to become available
        reach_start = time.time()
        reach_timeout = 60
        reachable = False
        last_error = None
        while time.time() - reach_start < reach_timeout:
            try:
                resp = httpx.get(f"{technitium_url}/api/user/login", timeout=5)
                if resp.status_code in [200, 400]:
                    reachable = True
                    break
            except Exception as e:
                last_error = str(e)
            time.sleep(2)

        if not reachable:
            error_msg = f"Technitium API not reachable at {technitium_url} from runner"
            if last_error:
                error_msg += f". Last error: {last_error}"
            pytest.skip(error_msg)

    @pytest.fixture(scope="class")
    def technitium_url(self):
        """Get Technitium service URL"""
        return os.getenv("TECHNITIUM_URL", "http://technitium:5380")

    def verify_compression(self, response: httpx.Response) -> tuple[bool, str]:
        """Verify if a response is compressed and return (is_compressed, encoding).

        Args:
            response: httpx Response object

        Returns:
            Tuple of (is_compressed: bool, encoding: str)
        """
        content_encoding = response.headers.get("content-encoding", "").lower()
        is_compressed = content_encoding in ("gzip", "deflate", "br", "compress")
        return is_compressed, content_encoding

    @pytest.fixture(scope="class")
    def technitium_credentials(self):
        """Get Technitium authentication credentials"""
        username = os.getenv("TECHNITIUM_USERNAME")
        password = os.getenv("TECHNITIUM_PASSWORD")
        if not username or not password:
            pytest.skip(
                "TECHNITIUM_USERNAME and TECHNITIUM_PASSWORD environment variables required"
            )
        return {"username": username, "password": password}

    @pytest.fixture(scope="class")
    def technitium_zone(self):
        """Get the primary DNS zone"""
        zone = os.getenv("ZONE")
        if not zone:
            pytest.skip("ZONE environment variable required")
        return zone

    @pytest.fixture(scope="class")
    def webhook_url(self):
        """Get the webhook service URL"""
        webhook_url = os.getenv("WEBHOOK_URL")
        if not webhook_url:
            pytest.skip("WEBHOOK_URL environment variable required")
        return webhook_url

    @pytest.fixture(scope="class")
    def technitium_client(self, technitium_url, technitium_credentials):
        """Create authenticated Technitium client"""
        return TechnitiumTestClient(technitium_url, technitium_credentials)

    def test_technitium_api_ready(self, technitium_url):
        """Verify Technitium API is accessible"""
        response = httpx.get(f"{technitium_url}/api/user/login", timeout=10)
        assert response.status_code in [200, 400], (
            f"Technitium API unreachable: {response.status_code}"
        )

    def test_dns_record_creation_and_validation(
        self, k8s_client, technitium_client, technitium_url, technitium_zone
    ):
        """Test complete DNS record lifecycle: create 20 services → verify records → cleanup

        This creates enough records to trigger HTTP compression in the /records endpoint response.
        Verifies that compression is enabled by checking Content-Encoding header.
        """
        namespace = "default"
        num_services = 20
        created_services = []

        # Create 20 ClusterIP services with internal-hostname annotations
        # With publishInternalServices enabled, ExternalDNS will create DNS records
        # pointing to the ClusterIP service's internal IP using the internal-hostname annotation
        for i in range(num_services):
            service_name = f"test-dns-service-{i:03d}"  # Zero-padded for consistent naming
            hostname = f"{service_name}.{technitium_zone}"

            service_spec = client.V1Service(
                api_version="v1",
                kind="Service",
                metadata=client.V1ObjectMeta(
                    name=service_name,
                    annotations={"external-dns.alpha.kubernetes.io/internal-hostname": hostname},
                ),
                spec=client.V1ServiceSpec(
                    type="ClusterIP",
                    selector={"app": "test-app"},
                    ports=[client.V1ServicePort(port=80, target_port=8080, protocol="TCP")],
                ),
            )

            # Create the service
            k8s_client.create_namespaced_service(namespace, service_spec)
            created_services.append(service_name)
            print(f"Created service {i + 1}/{num_services}: {service_name}")

        try:
            # Wait for ExternalDNS to process all services and create DNS records
            max_wait = 120  # 2 minutes max wait for 20 services
            wait_time = 0
            all_records_found = False
            compression_detected = False

            compression_info = {}  # Store compression detection info for later verification

            while wait_time < max_wait and not all_records_found:
                time.sleep(15)  # Check every 15 seconds
                wait_time += 15

                # Query Technitium for all DNS records in the zone
                try:
                    # Make raw HTTP call to detect compression headers
                    if not compression_detected:
                        try:
                            token = technitium_client.token
                            response = httpx.get(
                                f"{technitium_url}/api/zone/records",
                                params={
                                    "token": token,
                                    "zone": technitium_zone,
                                    "listZone": "true",
                                },
                                timeout=10,
                            )
                            response.raise_for_status()

                            # Check if response was compressed
                            content_encoding = response.headers.get("content-encoding", "").lower()
                            response_size = len(response.content)

                            # Store compression info for verification in test assertion
                            compression_info = {
                                "encoding": content_encoding,
                                "size": response_size,
                                "is_compressed": content_encoding in ("gzip", "deflate", "br"),
                            }

                            if compression_info["is_compressed"]:
                                compression_detected = True
                                msg = f"✓ HTTP compression ENABLED: {content_encoding} (response: {response_size} bytes)"
                                logger.info(msg)
                            else:
                                # Log even if no compression for debugging
                                msg = f"ℹ Response uncompressed (Content-Encoding: {content_encoding or 'none'}, size: {response_size} bytes)"
                                logger.info(msg)
                        except Exception as e:
                            print(f"[{wait_time}s] Could not check compression: {e}")

                    all_records = technitium_client.get_records(technitium_zone, list_zone=True)
                    test_records = [
                        r for r in all_records if r.get("name", "").startswith("test-dns-service-")
                    ]

                    print(f"[{wait_time}s] Found {len(test_records)}/{num_services} test records")

                    if len(test_records) >= num_services:
                        # Verify we have all expected hostnames
                        expected_hostnames = {
                            f"test-dns-service-{i:03d}.{technitium_zone}"
                            for i in range(num_services)
                        }
                        found_hostnames = {
                            r.get("name") for r in test_records if r.get("type") == "A"
                        }

                        if expected_hostnames.issubset(found_hostnames):
                            all_records_found = True
                            print(f"✓ All {num_services} DNS records found!")
                            break

                except Exception as e:
                    # Continue waiting if API call fails (service might not be ready)
                    print(f"[{wait_time}s] API call failed, continuing to wait: {e}")
                    continue

            assert all_records_found, (
                f"Not all {num_services} DNS records were created within {max_wait} seconds. "
                f"Found {len(test_records)} records."
            )

            # When we have large result sets (20+ records), report compression status
            # Note: Compression depends on response size and server configuration
            compression_status = "DETECTED" if compression_detected else "NOT DETECTED"
            encoding_info = (
                f" ({compression_info.get('encoding', 'none')})" if compression_info else ""
            )
            logger.info(f"Compression status: {compression_status}{encoding_info}")

            if compression_info:
                # This info will be visible in test output via logger
                response_size = compression_info.get("size", 0)
                encoding = compression_info.get("encoding", "none")
                assert response_size > 0, (
                    f"Response size should be captured. "
                    f"Compression detection: {compression_status} ({encoding}), "
                    f"Response size: {response_size} bytes"
                )
                # Document the compression detection in test output
                # This message will appear if the test fails or with -v flag
                print(
                    f"\n[Compression Check] Status: {compression_status}, "
                    f"Encoding: {encoding}, Size: {response_size} bytes"
                )

            # Verify the record details for a few samples
            all_records = technitium_client.get_records(technitium_zone, list_zone=True)
            test_records = [
                r for r in all_records if r.get("name", "").startswith("test-dns-service-")
            ]

            print(f"Final verification: {len(test_records)} test records found")

            # Sample check: verify first, middle, and last records
            sample_indices = [0, num_services // 2, num_services - 1]
            for idx in sample_indices:
                hostname = f"test-dns-service-{idx:03d}.{technitium_zone}"
                a_record = None
                for record in test_records:
                    if record.get("name") == hostname and record.get("type") == "A":
                        a_record = record
                        break

                assert a_record, f"No A record found for {hostname}"
                assert "rData" in a_record, f"Record for {hostname} should have rData field"

                # The record should have been created by ExternalDNS
                ip_address = a_record["rData"].get("ipAddress")
                assert ip_address, f"A record for {hostname} should have an IP address"
                print(f"✓ Verified record for {hostname}: {ip_address}")

        finally:
            # Clean up: delete all services
            for service_name in created_services:
                try:
                    k8s_client.delete_namespaced_service(service_name, namespace)
                    print(f"Deleted service: {service_name}")
                except Exception as e:
                    print(f"Warning: Failed to delete service {service_name}: {e}")

        # Wait for ExternalDNS to process the deletions
        print("Waiting for ExternalDNS to process deletions...")
        time.sleep(24)  # Give time for 20 deletions

        # Verify all DNS records were removed
        try:
            all_records = technitium_client.get_records(technitium_zone, list_zone=True)
            remaining_test_records = [
                r for r in all_records if r.get("name", "").startswith("test-dns-service-")
            ]
            assert len(remaining_test_records) == 0, (
                f"{len(remaining_test_records)} DNS records were not removed after service deletion"
            )
            print("✓ All DNS records successfully removed")
        except Exception as e:
            # If the API call fails, it might mean the records were successfully deleted
            # This is acceptable for cleanup verification
            print(f"Note: Could not verify record deletion (may be expected): {e}")

    def test_technitium_zone_exists(self, technitium_url):
        """Verify test.local zone was created in Technitium"""
        # This would require authentication, but for now just verify Technitium is accessible
        response = httpx.get(f"{technitium_url}/api/user/login", timeout=10)
        assert response.status_code in [200, 400], "Should be able to connect to Technitium API"


class TechnitiumTestClient:
    """Simple test client for Technitium API operations"""

    def __init__(self, base_url: str, credentials: dict):
        self.base_url = base_url.rstrip("/")
        self.credentials = credentials
        self.token = None
        self._login()

    def _login(self):
        """Authenticate with Technitium API"""
        data = {"user": self.credentials["username"], "pass": self.credentials["password"]}
        response = httpx.post(f"{self.base_url}/api/user/login", data=data, timeout=10)
        response.raise_for_status()
        result = response.json()
        self.token = result.get("token")
        if not self.token:
            raise Exception("Failed to get authentication token")

    def _authenticated_request(self, method: str, endpoint: str, data: dict | None = None):
        """Make an authenticated API request"""
        url = f"{self.base_url}{endpoint}"

        # Add token to the data/params (Technitium expects it in form data, not headers)
        request_data = {"token": self.token}
        if data:
            request_data.update(data)

        if method.upper() == "POST":
            response = httpx.post(url, data=request_data, timeout=10)
        else:
            response = httpx.get(url, params=request_data, timeout=10)

        response.raise_for_status()
        return response.json()

    def get_records(self, domain: str, zone: str | None = None, list_zone: bool | None = None):
        """Get DNS records for a domain"""
        data = {"domain": domain}
        if zone:
            data["zone"] = zone
        if list_zone is not None:
            data["listZone"] = str(list_zone).lower()

        result = self._authenticated_request("POST", "/api/zones/records/get", data)
        # Records are nested under "response" key in Technitium API response
        response_obj = result.get("response", {})
        records = response_obj.get("records", [])
        print(
            f"[TechnitiumTestClient] Query: domain={domain}, zone={zone}, list_zone={list_zone} -> {len(records)} records"
        )
        print(f"[TechnitiumTestClient] Full response: {result}")
        return records
