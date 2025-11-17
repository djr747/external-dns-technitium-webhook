#!/bin/bash
set -e

# This script replicates the CI integration test environment locally.
# It checks for dependencies, builds the webhook image, creates a kind cluster,
# and deploys Technitium and ExternalDNS with the webhook.

# --- Configuration ---
: "${HOST_PORT_WEB:=5380}"
: "${HOST_PORT_DNS:=5335}"
CLUSTER_NAME="local-integration-test"
KIND_CONTEXT="kind-${CLUSTER_NAME}"

# --- Dependency Check ---
if ! command -v kubectl &> /dev/null; then
    echo "Error: kubectl is not installed. Please install it to continue."
    exit 1
fi
if ! command -v kind &> /dev/null; then
    echo "Error: kind is not installed. Please install it to continue."
    exit 1
fi
if ! command -v helm &> /dev/null; then
    echo "Error: helm is not installed. Please install it to continue."
    exit 1
fi

# --- Context Handling ---
echo "--- Saving current Kubernetes context (if it exists) ---"
CURRENT_CONTEXT=$(kubectl config current-context 2>/dev/null || echo "")
RESTORE_COMMAND=""
if [ -n "${CURRENT_CONTEXT}" ]; then
  echo "Your current context is '${CURRENT_CONTEXT}'. It will be restored after cleanup."
  RESTORE_COMMAND="&& kubectl config use-context ${CURRENT_CONTEXT}"
else
  echo "No active kubectl context found. A new one will be created by kind."
fi

# --- Check for existing cluster ---
echo "--- Checking for existing cluster ---"
if kind get clusters | grep -q "^${CLUSTER_NAME}$"; then
    echo "Found existing cluster '${CLUSTER_NAME}'. Deleting it..."
    kind delete cluster --name "${CLUSTER_NAME}"
else
    echo "No existing cluster found. Proceeding with setup."
fi

echo "--- Building local webhook Docker image ---"
COMMIT_SHA=$(git rev-parse --short HEAD)
export IMAGE_TAG="external-dns-technitium-webhook:${COMMIT_SHA}"
docker build -t "${IMAGE_TAG}" .

echo "--- Creating kind cluster (this will switch your kubectl context) ---"
# Note: On macOS with Docker Desktop, extraPortMappings don't work reliably in kind.
# We'll use kubectl port-forward instead after the cluster is created.
cat > /tmp/kind-config.yaml <<EOF
kind: Cluster
apiVersion: kind.x-k8s.io/v1alpha4
nodes:
  - role: control-plane
EOF
kind create cluster --name "${CLUSTER_NAME}" --config /tmp/kind-config.yaml

echo "--- Loading images into kind cluster ---"
kind load docker-image "${IMAGE_TAG}" --name "${CLUSTER_NAME}"
docker pull technitium/dns-server:latest
kind load docker-image technitium/dns-server:latest --name "${CLUSTER_NAME}"

echo "--- Deploying Technitium DNS ---"
export ADMIN_PASSWORD=$(openssl rand -base64 12)
kubectl --context "${KIND_CONTEXT}" create secret generic technitium-secret \
  --from-literal=username=admin \
  --from-literal=password="${ADMIN_PASSWORD}" \
  -n default

kubectl --context "${KIND_CONTEXT}" apply -f tests/integration/k8s/technitium-deployment.yaml
kubectl --context "${KIND_CONTEXT}" wait --for=condition=ready pod \
  -l app=technitium \
  --timeout=300s \
  -n default

echo "--- Initializing Technitium ---"
kubectl --context "${KIND_CONTEXT}" run technitium-init \
  --image=curlimages/curl:latest \
  --restart=Never \
  --attach=true \
  --quiet \
  --env="TECHNITIUM_URL=http://technitium:5380" \
  --env="ADMIN_PASSWORD=${ADMIN_PASSWORD}" \
  --env="CATALOG_ZONE=catalog.invalid" \
  --env="ZONE=test.local" \
  -- sh -c "$(cat tests/integration/fixtures/init-technitium.sh)" > /tmp/technitium-init.log 2>&1

kubectl --context "${KIND_CONTEXT}" delete pod technitium-init -n default --force --grace-period=0 2>/dev/null || true

echo "--- Deploying ExternalDNS with webhook ---"
helm repo add external-dns https://kubernetes-sigs.github.io/external-dns/
helm repo update

REPO="${IMAGE_TAG%:*}"
TAG="${IMAGE_TAG##*:}"

helm install external-dns external-dns/external-dns \
  --kube-context "${KIND_CONTEXT}" \
  -f tests/integration/helm/external-dns-values.yaml \
  --set provider.webhook.image.repository="${REPO}" \
  --set provider.webhook.image.tag="${TAG}" \
  -n default \
  --timeout=5m

echo "--- Waiting for ExternalDNS deployment ---"
kubectl --context "${KIND_CONTEXT}" wait --for=condition=Available=True deployment/external-dns --timeout=120s

echo "---"
echo "--- Local environment is ready! ---"
echo "Your kubectl context has been switched to '${KIND_CONTEXT}'."
echo ""
echo "=== Next Steps ==="
echo ""
echo "1. Run integration tests:"
echo "   bash local-ci-setup/run-integration-tests.sh"
echo ""
echo "   This script will:"
echo "   - Set up kubectl port-forwarding to Technitium (localhost:30380)"
echo "   - Extract credentials from the Kubernetes secret"
echo "   - Run pytest with proper environment variables"
echo "   - Stream logs for debugging"
echo ""
echo "2. To manually interact with the cluster:"
echo "   kubectl --context ${KIND_CONTEXT} get pods -n default"
echo ""
echo "3. To access Technitium UI (requires port-forward in separate terminal):"
echo "   kubectl --context ${KIND_CONTEXT} port-forward svc/technitium 5380:5380 -n default"
echo "   Then open: http://localhost:5380"
echo ""
echo "4. To stream logs:"
echo "   Webhook:      kubectl --context ${KIND_CONTEXT} logs -l app.kubernetes.io/name=external-dns -c webhook -f"
echo "   ExternalDNS:  kubectl --context ${KIND_CONTEXT} logs -l app.kubernetes.io/name=external-dns -c external-dns -f"
echo "   Technitium:   kubectl --context ${KIND_CONTEXT} logs -l app=technitium -f"
echo ""
echo "5. To clean up and restore your original context:"
echo "   kind delete cluster --name ${CLUSTER_NAME} ${RESTORE_COMMAND}"
echo ""
echo "---"
