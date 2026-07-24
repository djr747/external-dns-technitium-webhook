#!/usr/bin/env bash
# Secure private-CA TLS integration test: host pytest -> HTTPS port-forward -> TLS proxy -> Technitium.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$SCRIPT_DIR"
KIND_CONTEXT="${KIND_CONTEXT:-kind-technitium-tls-test}"
NAMESPACE="${NAMESPACE:-default}"
TLS_FORWARD_PORT="${TLS_FORWARD_PORT:-30443}"
PYTEST_BIN="${PYTEST_BIN:-$SCRIPT_DIR/.venv/bin/pytest}"
CA_BUNDLE="$(mktemp)"
FORWARD_PID=""
CREATED_TECHNITIUM_SECRET=false

cleanup() {
  if [ -n "$FORWARD_PID" ]; then kill "$FORWARD_PID" 2>/dev/null || true; fi
  kubectl --context "$KIND_CONTEXT" -n "$NAMESPACE" delete -f tests/integration/k8s/technitium-tls-proxy.yaml --ignore-not-found >/dev/null 2>&1 || true
  kubectl --context "$KIND_CONTEXT" -n "$NAMESPACE" delete secret technitium-tls-proxy technitium-test-ca --ignore-not-found >/dev/null 2>&1 || true
  if [ "$CREATED_TECHNITIUM_SECRET" = true ]; then
    kubectl --context "$KIND_CONTEXT" -n "$NAMESPACE" delete -f tests/integration/k8s/technitium-deployment.yaml --ignore-not-found >/dev/null 2>&1 || true
    kubectl --context "$KIND_CONTEXT" -n "$NAMESPACE" delete secret technitium-secret --ignore-not-found >/dev/null 2>&1 || true
  fi
  rm -f "$CA_BUNDLE"
}
trap cleanup EXIT

if ! kubectl --context "$KIND_CONTEXT" -n "$NAMESPACE" get secret technitium-secret >/dev/null 2>&1; then
  kubectl --context "$KIND_CONTEXT" -n "$NAMESPACE" create secret generic technitium-secret \
    --from-literal=username=admin \
    --from-literal=password="$(openssl rand -hex 32)" >/dev/null
  CREATED_TECHNITIUM_SECRET=true
fi

kubectl --context "$KIND_CONTEXT" apply -f tests/integration/k8s/technitium-deployment.yaml
kubectl --context "$KIND_CONTEXT" apply -f tests/integration/k8s/technitium-tls-proxy.yaml
kubectl --context "$KIND_CONTEXT" -n "$NAMESPACE" wait --for=condition=Ready certificate/technitium-test-ca --timeout=180s
kubectl --context "$KIND_CONTEXT" -n "$NAMESPACE" wait --for=condition=Ready certificate/technitium-tls-proxy --timeout=180s
kubectl --context "$KIND_CONTEXT" -n "$NAMESPACE" rollout status deployment/technitium --timeout=180s
kubectl --context "$KIND_CONTEXT" -n "$NAMESPACE" rollout status deployment/technitium-tls-proxy --timeout=180s
kubectl --context "$KIND_CONTEXT" -n "$NAMESPACE" get secret technitium-test-ca -o jsonpath='{.data.tls\.crt}' | base64 -d > "$CA_BUNDLE"
kubectl --context "$KIND_CONTEXT" -n "$NAMESPACE" port-forward svc/technitium-tls-proxy "$TLS_FORWARD_PORT":8443 > /tmp/technitium-tls-port-forward.log 2>&1 &
FORWARD_PID=$!
for _ in $(seq 1 30); do
  if kill -0 "$FORWARD_PID" 2>/dev/null && nc -z localhost "$TLS_FORWARD_PORT"; then break; fi
  sleep 1
done
kill -0 "$FORWARD_PID"

export TECHNITIUM_URL="https://localhost:${TLS_FORWARD_PORT}"
export TECHNITIUM_CA_BUNDLE_FILE="$CA_BUNDLE"
"$PYTEST_BIN" tests/integration/test_tls_transport.py -q -m integration
