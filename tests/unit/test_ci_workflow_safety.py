from pathlib import Path

WORKFLOW = Path(__file__).parents[2] / ".github" / "workflows" / "ci.yml"


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


def test_dockerfile_local_project_install_runs_as_root_in_builder() -> None:
    dockerfile = Path(__file__).parents[2] / "Dockerfile"
    source = dockerfile.read_text()
    local_install = source.rfind("pip")
    assert local_install >= 0
    assert "USER root" in source[:local_install]
