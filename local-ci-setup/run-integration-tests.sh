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

CLUSTER_NAME="local-integration-test"
KIND_CONTEXT="kind-${CLUSTER_NAME}"
FORWARD_PORT=30380

# Check if cluster exists
if ! kind get clusters | grep -q "^${CLUSTER_NAME}$"; then
    echo "ERROR: Cluster '$CLUSTER_NAME' not found."
    echo "Please run './local-ci-setup/setup.sh' first to create the cluster."
    exit 1
fi

# Switch to the kind context
kubectl config use-context "${KIND_CONTEXT}"

echo "--- Setting up port forwarding ---"
echo "Forwarding localhost:${FORWARD_PORT} to technitium-external:5380..."

# Kill any existing port-forward processes on these ports
pkill -f "kubectl port-forward.*${FORWARD_PORT}" || true
sleep 1

# Start port forwarding in the background

kubectl --context "${KIND_CONTEXT}" port-forward svc/technitium-external ${FORWARD_PORT}:5380 -n default &
TECHNITIUM_FORWARD_PID=$!

# Give port-forward time to establish
sleep 2

# Verify port is accessible

if ! curl -s http://localhost:${FORWARD_PORT}/api/user/login > /dev/null 2>&1; then
    echo "ERROR: Could not reach Technitium at localhost:${FORWARD_PORT}"
    kill $FORWARD_PID 2>/dev/null || true
    exit 1
fi

echo "✓ Port forwarding established"

# Extract credentials from secret
echo "--- Extracting credentials ---"
TECHNITIUM_USERNAME=$(kubectl --context "${KIND_CONTEXT}" get secret technitium-secret -o jsonpath='{.data.username}' | base64 -d)
TECHNITIUM_PASSWORD=$(kubectl --context "${KIND_CONTEXT}" get secret technitium-secret -o jsonpath='{.data.password}' | base64 -d)
ZONE="test.local"

echo "✓ Credentials extracted"
echo "  Username: $TECHNITIUM_USERNAME"
echo "  Zone: $ZONE"

# Export environment variables for pytest
export TECHNITIUM_URL="http://localhost:${FORWARD_PORT}"
export TECHNITIUM_USERNAME
export TECHNITIUM_PASSWORD
export ZONE

# Clean up trap
cleanup() {
    echo ""
    echo "--- Cleaning up ---"
    kill $TECHNITIUM_FORWARD_PID 2>/dev/null || true
    kill $WEBHOOK_FORWARD_PID 2>/dev/null || true
    echo "Port forwarding stopped"
}
trap cleanup EXIT

# Run integration tests
echo ""
echo "--- Running integration tests ---"
echo "TECHNITIUM_URL=$TECHNITIUM_URL"
echo "TECHNITIUM_USERNAME=$TECHNITIUM_USERNAME"
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
