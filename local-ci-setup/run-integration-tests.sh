#!/bin/bash
#
# Run integration tests locally against the kind cluster created by setup.sh
# This script:
# 1. Sets up port-forwarding from localhost to the Technitium service
# 2. Extracts credentials from the Technitium secret
# 3. Runs pytest with the correct environment variables
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$SCRIPT_DIR"

# Use absolute path to pytest from venv
VENV_DIR="$SCRIPT_DIR/.venv"
if [ -x "$VENV_DIR/bin/pytest" ]; then
    PYTEST_BIN="$VENV_DIR/bin/pytest"
else
    PYTEST_BIN="pytest"
fi

CLUSTER_NAME="${CLUSTER_NAME:-local-integration-test}"
KIND_CONTEXT="${KIND_CONTEXT:-kind-${CLUSTER_NAME}}"
HEALTH_FORWARD_PORT=30380
TLS_FORWARD_PORT="${TLS_FORWARD_PORT:-30443}"
CA_BUNDLE="$(mktemp)"

# Verify the requested context without changing global kubectl state.
if ! kubectl --context "${KIND_CONTEXT}" get --raw=/readyz >/dev/null; then
    echo "ERROR: Kubernetes context '${KIND_CONTEXT}' is not reachable."
    exit 1
fi

echo "--- Setting up port forwarding ---"
kubectl --context "${KIND_CONTEXT}" get secret technitium-test-ca -n default -o jsonpath='{.data.tls\.crt}' | base64 -d > "${CA_BUNDLE}"
echo "Forwarding localhost:${HEALTH_FORWARD_PORT} to technitium:5380 and localhost:${TLS_FORWARD_PORT} to technitium:53443..."

# Start port forwarding in the background
kubectl --context "${KIND_CONTEXT}" port-forward svc/technitium ${HEALTH_FORWARD_PORT}:5380 -n default &
HEALTH_FORWARD_PID=$!
kubectl --context "${KIND_CONTEXT}" port-forward svc/technitium ${TLS_FORWARD_PORT}:53443 -n default &
TECHNITIUM_FORWARD_PID=$!
EXTERNAL_DNS_LOG_PID=""

# Give port-forward time to establish
sleep 2

# Verify port is accessible

if ! curl -s http://localhost:${HEALTH_FORWARD_PORT}/api/user/login > /dev/null 2>&1 || ! curl -s --cacert "${CA_BUNDLE}" https://localhost:${TLS_FORWARD_PORT}/api/user/login > /dev/null 2>&1; then
    echo "ERROR: Could not reach Technitium HTTP health endpoint or native TLS endpoint"
    kill "${HEALTH_FORWARD_PID}" 2>/dev/null || true
    kill "${TECHNITIUM_FORWARD_PID}" 2>/dev/null || true
    rm -f "${CA_BUNDLE}"
    exit 1
fi

echo "✓ Port forwarding established"

# Extract credentials from secret
echo "--- Extracting credentials ---"
TECHNITIUM_USERNAME=$(kubectl --context "${KIND_CONTEXT}" get secret technitium-secret -o jsonpath='{.data.username}' | base64 -d)
TECHNITIUM_PASSWORD=$(kubectl --context "${KIND_CONTEXT}" get secret technitium-secret -o jsonpath='{.data.password}' | base64 -d)
ZONE="test.local"

echo "✓ Credentials extracted"
echo "  Zone: $ZONE"

# Export environment variables for pytest
export TECHNITIUM_URL="https://localhost:${TLS_FORWARD_PORT}"
export TECHNITIUM_CA_BUNDLE_FILE="${CA_BUNDLE}"
export TECHNITIUM_USERNAME
export TECHNITIUM_PASSWORD
export ZONE

# Clean up trap
cleanup() {
    rm -f "${CA_BUNDLE}"
    echo ""
    echo "--- Cleaning up ---"
    kill "${HEALTH_FORWARD_PID}" 2>/dev/null || true
    kill "${TECHNITIUM_FORWARD_PID}" 2>/dev/null || true
    kill "${EXTERNAL_DNS_LOG_PID}" 2>/dev/null || true
    echo "Port forwarding stopped"
}
trap cleanup EXIT

# Run integration tests
echo ""
echo "--- Running integration tests ---"
echo "TECHNITIUM_URL=$TECHNITIUM_URL"
echo "ZONE=$ZONE"
echo ""

# Start log streams in background for debugging
echo "Starting log streams for debugging..."
mkdir -p /tmp/k8s-logs
kubectl --context "${KIND_CONTEXT}" logs -l app.kubernetes.io/name=external-dns -n default -c external-dns -f > /tmp/k8s-logs/external-dns.log 2>&1 &
EXTERNAL_DNS_LOG_PID=$!



# Give logs a moment to start
sleep 1

# Run tests using absolute path to pytest (ensures venv site-packages are used)
"$PYTEST_BIN" tests/integration/test_webhook_integration.py \
    -v \
    --tb=short \
    -m "integration"
TEST_RESULT=$?

# Stop log streams
kill $EXTERNAL_DNS_LOG_PID 2>/dev/null || true

# Display logs
if [ $TEST_RESULT -ne 0 ]; then
    echo ""
    echo "=== External DNS Logs ==="
    cat /tmp/k8s-logs/external-dns.log || true
    
    echo ""
    echo "=== Webhook Logs ==="
    echo "(webhook logs not collected by runner to avoid direct webhook access)"
fi

exit $TEST_RESULT
