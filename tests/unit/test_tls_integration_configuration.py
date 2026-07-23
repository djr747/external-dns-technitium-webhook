from pathlib import Path
from typing import Any

import yaml

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def _documents(relative_path: str) -> list[dict[str, Any]]:
    return [
        document
        for document in yaml.safe_load_all((REPOSITORY_ROOT / relative_path).read_text())
        if document
    ]


def test_webhook_uses_direct_technitium_https_and_ca_bundle() -> None:
    values = yaml.safe_load(
        (REPOSITORY_ROOT / "tests/integration/helm/external-dns-values.yaml").read_text()
    )
    webhook = values["provider"]["webhook"]
    env = {item["name"]: item.get("value") for item in webhook["env"]}

    assert env["TECHNITIUM_URL"] == "https://technitium.default.svc.cluster.local:53443"
    assert env["TECHNITIUM_CA_BUNDLE_FILE"] == "/etc/technitium/ca/ca.crt"
    assert any(
        volume["name"] == "technitium-ca" and volume["secret"]["secretName"] == "technitium-test-ca"
        for volume in values["extraVolumes"]
    )
    assert any(
        mount["name"] == "technitium-ca"
        and mount["mountPath"] == "/etc/technitium/ca"
        and mount["readOnly"]
        for mount in webhook["extraVolumeMounts"]
    )


def test_technitium_manifest_uses_native_https_and_retains_http_health() -> None:
    documents = _documents("tests/integration/k8s/technitium-deployment.yaml")
    deployment = next(document for document in documents if document["kind"] == "Deployment")
    service = next(document for document in documents if document["kind"] == "Service")
    container = deployment["spec"]["template"]["spec"]["containers"][0]
    env = {item["name"]: item for item in container["env"]}
    ports = {port["port"] for port in service["spec"]["ports"]}

    assert ports == {5380, 53443}
    assert env["DNS_SERVER_WEB_SERVICE_HTTP_PORT"]["value"] == "5380"
    assert env["DNS_SERVER_WEB_SERVICE_HTTPS_PORT"]["value"] == "53443"
    assert env["DNS_SERVER_WEB_SERVICE_ENABLE_HTTPS"]["value"] == "true"
    assert env["DNS_SERVER_WEB_SERVICE_HTTP_TO_TLS_REDIRECT"]["value"] == "false"
    assert (
        env["DNS_SERVER_WEB_SERVICE_TLS_CERTIFICATE_PATH"]["value"]
        == "/etc/technitium/tls/keystore.p12"
    )
    assert (
        env["DNS_SERVER_WEB_SERVICE_TLS_CERTIFICATE_PASSWORD"]["valueFrom"]["secretKeyRef"]["name"]
        == "technitium-pkcs12-password"
    )
    assert any(
        mount["mountPath"] == "/etc/technitium/tls" and mount["readOnly"]
        for mount in container["volumeMounts"]
    )
    assert any(
        volume.get("secret", {}).get("secretName") == "technitium-https-tls"
        for volume in deployment["spec"]["template"]["spec"]["volumes"]
    )


def test_local_runner_uses_direct_technitium_tls_and_http_health() -> None:
    runner = (REPOSITORY_ROOT / "local-ci-setup/run-integration-tests.sh").read_text()

    assert "svc/technitium ${TLS_FORWARD_PORT}:53443" in runner
    assert "https://localhost:${TLS_FORWARD_PORT}" in runner
    assert "svc/technitium ${HEALTH_FORWARD_PORT}:5380" in runner
    assert "http://localhost:${HEALTH_FORWARD_PORT}" in runner
    assert 'KIND_CONTEXT="${KIND_CONTEXT:-kind-${CLUSTER_NAME}}"' in runner
    assert 'TLS_FORWARD_PORT="${TLS_FORWARD_PORT:-30443}"' in runner
    assert "kubectl config use-context" not in runner
    assert "technitium-tls-proxy" not in runner
    assert "pkill -f" not in runner
    assert "HEALTH_FORWARD_PID=$!" in runner
    assert "TECHNITIUM_FORWARD_PID=$!" in runner
    assert 'kill "${HEALTH_FORWARD_PID}"' in runner
    assert 'kill "${TECHNITIUM_FORWARD_PID}"' in runner
    assert 'kill "${EXTERNAL_DNS_LOG_PID}"' in runner
    assert "TECHNITIUM_USERNAME=$TECHNITIUM_USERNAME" not in runner


def test_local_setup_provisions_native_technitium_tls_without_proxy() -> None:
    setup = (REPOSITORY_ROOT / "local-ci-setup/setup.sh").read_text()

    assert "cert-manager/releases/download/v1.16.3/cert-manager.yaml" in setup
    assert "technitium-pkcs12-password" in setup
    assert "certificate/technitium-https" in setup
    assert "technitium-tls-proxy" not in setup


def test_ci_uses_native_technitium_tls_and_http_health() -> None:
    workflow = (REPOSITORY_ROOT / ".github/workflows/ci.yml").read_text()

    assert "technitium-pkcs12-password" in workflow
    assert "certificate/technitium-https" in workflow
    assert (
        "kubectl wait --for=condition=Available deployment/cert-manager-webhook "
        "--timeout=180s -n cert-manager" in workflow
    )
    assert "svc/technitium 30443:53443" in workflow
    assert "TECHNITIUM_URL=http://technitium.default.svc.cluster.local:5380" in workflow
    assert "technitium-tls-proxy" not in workflow


def test_native_technitium_certificate_supplies_pkcs12() -> None:
    certificate_path = Path("tests/integration/k8s/technitium-tls.yaml")
    assert certificate_path.is_file()
    assert not Path("tests/integration/k8s/technitium-tls-proxy.yaml").exists()
    documents = _documents(str(certificate_path))
    certificate = next(
        document
        for document in documents
        if document["kind"] == "Certificate" and document["metadata"]["name"] == "technitium-https"
    )

    assert certificate["metadata"]["name"] == "technitium-https"
    assert certificate["spec"]["secretName"] == "technitium-https-tls"
    assert certificate["spec"]["keystores"]["pkcs12"]["create"] is True
    assert (
        certificate["spec"]["keystores"]["pkcs12"]["passwordSecretRef"]["name"]
        == "technitium-pkcs12-password"
    )
    assert "localhost" in certificate["spec"]["dnsNames"]
    assert "technitium.default.svc.cluster.local" in certificate["spec"]["dnsNames"]
