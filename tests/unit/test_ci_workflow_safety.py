from pathlib import Path

WORKFLOW = Path(__file__).parents[2] / ".github" / "workflows" / "ci.yml"
SECURITY_WORKFLOW = Path(__file__).parents[2] / ".github" / "workflows" / "security.yml"
SCHEDULED_REBUILD_WORKFLOW = (
    Path(__file__).parents[2] / ".github" / "workflows" / "scheduled-rebuild.yml"
)
RELEASE_WORKFLOW = Path(__file__).parents[2] / ".github" / "workflows" / "release.yml"
HELM_EXAMPLE = Path(__file__).parents[2] / "helm" / "values-webhook-example.yaml"
INTEGRATION_HELM_VALUES = (
    Path(__file__).parents[2] / "tests" / "integration" / "helm" / "external-dns-values.yaml"
)


def test_ci_skips_push_jobs_only_when_the_branch_has_an_open_pr() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    assert "  push:\n    branches:\n      - '**'" in workflow
    assert "  pull_request:\n    branches:\n      - '**'" in workflow
    assert "head=${GITHUB_REPOSITORY_OWNER}:${GITHUB_REF_NAME}" in workflow
    assert "needs.check-open-pr.outputs.should-run == 'true'" in workflow


def test_security_skips_push_jobs_only_when_the_branch_has_an_open_pr() -> None:
    workflow = SECURITY_WORKFLOW.read_text(encoding="utf-8")
    assert "  push:\n    branches-ignore: [ main ]" in workflow
    assert "  pull_request:\n    branches:\n      - '**'" in workflow
    assert "head=${GITHUB_REPOSITORY_OWNER}:${GITHUB_REF_NAME}" in workflow
    assert "needs.check-open-pr.outputs.should-run == 'true'" in workflow


def test_security_workflow_uses_one_codeql_action_revision() -> None:
    workflow = SECURITY_WORKFLOW.read_text(encoding="utf-8")
    codeql_action_sha = "1c5b675653bb5c22dbe9b12b556ec555138e09fd"
    codeql_lines = [line for line in workflow.splitlines() if "uses: github/codeql-action/" in line]
    assert codeql_lines
    assert all(f"@{codeql_action_sha}" in line for line in codeql_lines)


def test_snyk_monitor_reads_outputs_from_declared_dependencies() -> None:
    workflow = SCHEDULED_REBUILD_WORKFLOW.read_text(encoding="utf-8")
    assert "needs: [check-for-updates, rebuild-image]" in workflow
    assert (
        "needs.check-for-updates.outputs.rebuild-needed == 'true'"
        " && needs.rebuild-image.result == 'success'"
    ) in workflow


def test_external_dns_v023_helm_values_are_explicit_and_supported() -> None:
    expected = [
        "A",
        "AAAA",
        "NS",
        "CNAME",
        "PTR",
        "MX",
        "TXT",
        "SRV",
        "NAPTR",
        "DNAME",
        "TLSA",
        "ANAME",
        "CAA",
        "URI",
        "SSHFP",
        "SVCB",
        "HTTPS",
    ]
    for values_path in (HELM_EXAMPLE, INTEGRATION_HELM_VALUES):
        values = values_path.read_text(encoding="utf-8")
        assert "annotationPrefix: external-dns.kubernetes.io/" in values
        assert "policy: sync" in values
        assert "managedRecordTypes:" in values
        start = values.index("managedRecordTypes:")
        end = values.find("\nprovider:", start)
        managed_types = values[start : end if end != -1 else None]
        assert all(f"  - {record_type}" in managed_types for record_type in expected)
        assert "imagePullPolicy:" not in managed_types


def test_v023_controller_chart_and_ga_annotations_are_used() -> None:
    ci = WORKFLOW.read_text(encoding="utf-8")
    integration_path = (
        Path(__file__).parents[2] / "tests" / "integration" / "test_webhook_integration.py"
    )
    integration = integration_path.read_text(encoding="utf-8")
    assert "external-dns/external-dns --version 1.22.0" in ci
    values = INTEGRATION_HELM_VALUES.read_text(encoding="utf-8")
    assert "tag: v0.23.0" in values
    assert "external-dns.alpha.kubernetes.io/" not in integration


def test_snyk_container_reports_reach_json_gate_after_scan_errors() -> None:
    for workflow_path in (SECURITY_WORKFLOW, SCHEDULED_REBUILD_WORKFLOW, RELEASE_WORKFLOW):
        workflow = workflow_path.read_text(encoding="utf-8")
        assert "Normalize Snyk" in workflow
        assert "continue-on-error: true" in workflow
        assert "security-severity" in workflow
        assert "high/critical" in workflow
        assert "exit 1" in workflow


def test_release_snyk_gate_has_no_zlib_exception() -> None:
    release = RELEASE_WORKFLOW.read_text(encoding="utf-8")
    assert "SNYK-WOLFILATEST-ZLIB-19698962" not in release
    assert "CVE-2026-85091" not in release
    assert "1.3.2-r7" not in release


def _integration_step() -> str:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    marker = "pytest tests/integration/test_webhook_integration.py"
    start = workflow.index(marker)
    return workflow[max(0, workflow.rfind("      - name:", 0, start)) :]


def test_integration_workflow_fails_on_pipeline_http_and_pytest_warning_errors() -> None:
    integration = _integration_step()
    assert "set -o pipefail" in integration
    assert "--fail-with-body" in integration
    assert "-W error" in integration


def test_integration_workflow_rejects_skipped_tests() -> None:
    integration = _integration_step()
    assert "--junitxml=/tmp/integration-junit.xml" in integration
    assert "unexpected skipped integration test" in integration


def test_integration_workflow_jq_filter_uses_unescaped_empty_string() -> None:
    bad_escape = chr(92) + chr(34) + chr(92) + chr(34)
    assert bad_escape not in WORKFLOW.read_text()


def test_integration_workflow_pytest_command_has_no_literal_newline_argument() -> None:
    integration = _integration_step()
    literal_newline_escape = chr(92) + "n"
    assert literal_newline_escape not in integration


def test_dockerfile_does_not_use_root_user() -> None:
    dockerfile = Path(__file__).parents[2] / "Dockerfile"
    assert "USER root" not in dockerfile.read_text()


def test_integration_workflow_pytest_invocation_has_no_shell_continuation() -> None:
    integration = _integration_step()
    pytest_lines = [
        line for line in integration.splitlines() if "test_webhook_integration.py" in line
    ]
    assert len(pytest_lines) == 1
    assert chr(92) not in pytest_lines[0]


def test_pending_pod_diagnostics_handles_missing_container_statuses() -> None:
    workflow = (Path(__file__).parents[2] / ".github" / "workflows" / "ci.yml").read_text()
    assert "(.status.containerStatuses // [])[]" in workflow


def test_external_dns_readiness_requires_pod_ready_condition() -> None:
    workflow = (Path(__file__).parents[2] / ".github" / "workflows" / "ci.yml").read_text()
    assert "POD_READY=" in workflow
    assert '[ "$POD_READY" = "True" ]' in workflow


def test_external_dns_timeout_captures_per_container_logs() -> None:
    workflow = (Path(__file__).parents[2] / ".github" / "workflows" / "ci.yml").read_text()
    timeout = workflow.index("ERROR: ExternalDNS pod did not become ready after 160s.")
    assert "capture_external_dns_diagnostics()" in workflow
    assert "capture_external_dns_diagnostics" in workflow[timeout:]


def test_integration_pytest_reports_skip_reasons() -> None:
    workflow = (Path(__file__).parents[2] / ".github" / "workflows" / "ci.yml").read_text()
    integration_command = next(
        line
        for line in workflow.splitlines()
        if "pytest tests/integration/test_webhook_integration.py" in line
    )
    assert "-rs" in integration_command.split()


def test_integration_failure_emits_buffered_container_diagnostics() -> None:
    workflow = (Path(__file__).parents[2] / ".github" / "workflows" / "ci.yml").read_text()
    assert "emit_integration_failure_diagnostics()" in workflow
    assert "tail -n 2000 /tmp/external-dns.log || true" in workflow
    assert "tail -n 2000 /tmp/webhook.log || true" in workflow
    assert "tail -n 200 /tmp/technitium-tls-port-forward.log || true" in workflow
    assert "emit_integration_failure_diagnostics" in workflow.split("trap ", 1)[1]
