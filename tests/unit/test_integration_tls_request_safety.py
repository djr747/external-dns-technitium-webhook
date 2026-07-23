"""Regression guard for TLS verification in Kubernetes integration requests."""

import ast
from pathlib import Path

INTEGRATION_TEST = Path(__file__).parents[1] / "integration" / "test_webhook_integration.py"


def _is_httpx2_request(call: ast.Call) -> bool:
    return (
        isinstance(call.func, ast.Attribute)
        and isinstance(call.func.value, ast.Name)
        and call.func.value.id == "httpx2"
        and call.func.attr in {"get", "post"}
    )


def test_technitium_integration_requests_explicitly_verify_tls() -> None:
    tree = ast.parse(INTEGRATION_TEST.read_text())
    requests = [
        node for node in ast.walk(tree) if isinstance(node, ast.Call) and _is_httpx2_request(node)
    ]
    assert requests
    for request in requests:
        assert any(keyword.arg == "verify" for keyword in request.keywords), (
            f"httpx2 request at line {request.lineno} must explicitly verify TLS"
        )
