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
