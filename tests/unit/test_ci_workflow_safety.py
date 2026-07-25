from pathlib import Path

WORKFLOW = Path(__file__).parents[2] / ".github" / "workflows" / "ci.yml"
SECURITY_WORKFLOW = Path(__file__).parents[2] / ".github" / "workflows" / "security.yml"
SCHEDULED_REBUILD_WORKFLOW = (
    Path(__file__).parents[2] / ".github" / "workflows" / "scheduled-rebuild.yml"
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
    codeql_action_sha = "7211b7c8077ea37d8641b6271f6a365a22a5fbfa"
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
    assert "tail -n 200 /tmp/external-dns.log || true" in workflow
    assert "tail -n 200 /tmp/webhook.log || true" in workflow
    assert "tail -n 200 /tmp/technitium-tls-port-forward.log || true" in workflow
    assert "emit_integration_failure_diagnostics" in workflow.split("trap ", 1)[1]
