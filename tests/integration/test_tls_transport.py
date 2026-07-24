"""Private-CA TLS transport integration checks via Kubernetes port-forward."""

import http.client
import os
import socket
import ssl
from pathlib import Path
from urllib.parse import urlparse

import pytest

pytestmark = pytest.mark.integration


def _endpoint() -> tuple[str, int, Path]:
    parsed = urlparse(os.environ["TECHNITIUM_URL"])
    assert parsed.scheme == "https"
    assert parsed.hostname == "localhost"
    assert parsed.port is not None
    ca_bundle = Path(os.environ["TECHNITIUM_CA_BUNDLE_FILE"])
    assert ca_bundle.is_file()
    return parsed.hostname, parsed.port, ca_bundle


def _handshake(host: str, port: int, context: ssl.SSLContext, server_name: str) -> None:
    with context.wrap_socket(
        socket.create_connection((host, port), timeout=10), server_hostname=server_name
    ) as tls_socket:
        assert tls_socket.version() is not None


def test_private_ca_tls_succeeds_with_trusted_ca() -> None:
    host, port, ca_bundle = _endpoint()
    ctx = ssl.create_default_context(cafile=ca_bundle)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    connection = http.client.HTTPSConnection(host, port, context=ctx, timeout=10)
    try:
        connection.request("GET", "/")
        response = connection.getresponse()
        assert response.status < 500
    finally:
        connection.close()


def test_private_ca_tls_fails_without_trusted_ca() -> None:
    host, port, _ = _endpoint()
    ctx = ssl.create_default_context()
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    with pytest.raises(ssl.SSLCertVerificationError):
        _handshake(host, port, ctx, "localhost")


def test_private_ca_tls_rejects_wrong_hostname() -> None:
    host, port, ca_bundle = _endpoint()
    ctx = ssl.create_default_context(cafile=ca_bundle)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    with pytest.raises(ssl.SSLCertVerificationError):
        _handshake(host, port, ctx, "wrong.invalid")
