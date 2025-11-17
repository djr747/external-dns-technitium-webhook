# Local Integration Testing Guide

This guide explains how to run integration tests locally against a Kubernetes cluster created with `kind`.

## Prerequisites

- `kind` - Kubernetes in Docker
- `kubectl` - Kubernetes CLI
- `helm` - Kubernetes package manager
- Docker - For running containers
- Python 3.13+ - With venv
- `curl` - For health checks

Install on macOS:
```bash
brew install kind kubectl helm
```

## Quick Start

### 1. Create the Local Cluster and Infrastructure

```bash
bash local-ci-setup/setup.sh
```

This script:
- Creates a local kind cluster named `local-integration-test`
- Builds the webhook Docker image from the current code
- Loads images into kind
- Deploys Technitium DNS Server
- Deploys ExternalDNS with the webhook provider sidecar
- Waits for all services to be ready

Expected output shows deployment status and next steps.

### 2. Run Integration Tests

```bash
bash local-ci-setup/run-integration-tests.sh
```

This script:
- Sets up `kubectl port-forward` from `localhost:30380` to the Technitium service
- Extracts credentials from the Kubernetes secret
- Runs pytest with proper environment variables
- Streams logs for debugging if tests fail
- Cleans up port-forwarding on exit

## Test Results

The integration test suite validates:

1. **test_technitium_api_ready** - Technitium API is reachable and responds to authentication requests
2. **test_dns_record_creation_and_validation** - ExternalDNS can sync Kubernetes services to DNS records; includes HTTP compression detection for large responses
3. **test_technitium_zone_exists** - The configured zone exists in Technitium

### Expected Test Run Time

- Initial test suite: ~40 seconds
- With 50 services (large scale test): ~5 minutes

## Manual Cluster Interaction

### View Cluster Status

```bash
# Get all pods
kubectl get pods -n default

# Get services
kubectl get svc -n default

# Get logs from specific component
kubectl logs -l app.kubernetes.io/name=external-dns -c webhook -f     # Webhook
kubectl logs -l app.kubernetes.io/name=external-dns -c external-dns -f # ExternalDNS
kubectl logs -l app=technitium -f                                        # Technitium
```

### Access Technitium Web UI

In a separate terminal:
```bash
kubectl port-forward svc/technitium 5380:30380 -n default
```

Then open `http://localhost:30380` in your browser.

Default credentials:
- Username: `admin`
- Password: (generated randomly and stored in the Kubernetes secret)

### Inspect Configuration

```bash
# View Technitium admin credentials
kubectl get secret technitium-secret -o jsonpath='{.data.password}' | base64 -d

# View ExternalDNS configuration
kubectl describe deployment external-dns

# View webhook image version
kubectl describe pod -l app.kubernetes.io/name=external-dns -c webhook
```

## Cleanup

To delete the cluster and restore your original Kubernetes context:

```bash
kind delete cluster --name local-integration-test && kubectl config use-context <your-original-context>
```

To just switch back to your original context without deleting:

```bash
kubectl config use-context <your-original-context>
```

## Troubleshooting

### Port Forwarding Not Working

If you see "Could not reach Technitium at localhost:30380":

1. Verify the Technitium pod is running:
   ```bash
   kubectl get pods -l app=technitium
   ```

2. Check if something else is using port 30380:
   ```bash
   lsof -i :30380
   ```

3. Kill any existing port-forward processes:
   ```bash
   pkill -f "kubectl port-forward.*30380"
   ```

### Tests Skip or Can't Find kubernetes Module

The integration test suite requires the `kubernetes` Python package. If it's not installed:

```bash
source .venv/bin/activate
pip install kubernetes
```

The conftest.py in the integration tests directory handles venv path configuration.

### ExternalDNS Not Syncing

If DNS records aren't appearing in Technitium:

1. Check ExternalDNS logs:
   ```bash
   kubectl logs -l app.kubernetes.io/name=external-dns -c external-dns -f
   ```

2. Check webhook logs:
   ```bash
   kubectl logs -l app.kubernetes.io/name=external-dns -c webhook -f
   ```

3. Verify the webhook is receiving requests:
   ```bash
   # Look for endpoints logged in webhook
   kubectl logs -l app.kubernetes.io/name=external-dns -c webhook -f | grep -i "endpoint\|record"
   ```

### Kubernetes Context Issues

To see your current context:
```bash
kubectl config current-context
```

To list all contexts:
```bash
kubectl config get-contexts
```

To switch contexts:
```bash
kubectl config use-context <context-name>
```

## Architecture

The local testing environment mirrors the CI setup:

```
Your Machine
    ↓
kubectl port-forward (localhost:30380)
    ↓
kind cluster
├── Technitium DNS (ClusterIP:5380, NodePort:30380)
├── ExternalDNS with webhook sidecar
└── Test resources (Services for DNS records)
```

**Key difference from CI**: On CI (Linux), kind's `extraPortMappings` work directly. On macOS with Docker Desktop, we use `kubectl port-forward` to expose the service to the host.

## Environment Variables

When running tests manually, set these environment variables:

```bash
export TECHNITIUM_URL="http://localhost:30380"
export TECHNITIUM_USERNAME="admin"
export TECHNITIUM_PASSWORD="$(kubectl get secret technitium-secret -o jsonpath='{.data.password}' | base64 -d)"
export ZONE="test.local"

pytest tests/integration/ -m integration -v
```

The `run-integration-tests.sh` script does this automatically.

## Development Workflow

### Make Code Changes

Edit source code in `external_dns_technitium_webhook/`

### Rebuild and Test

```bash
# Rebuild the image
docker build -t external-dns-technitium-webhook:dev .

# Load into kind
kind load docker-image external-dns-technitium-webhook:dev --name local-integration-test

# Restart ExternalDNS pod to pick up new image
kubectl rollout restart deployment/external-dns

# Run tests
bash local-ci-setup/run-integration-tests.sh
```

## CI vs Local Testing

| Aspect | CI (Linux) | Local (macOS) |
|--------|-----------|---------------|
| Port Mapping | kind's extraPortMappings | kubectl port-forward |
| Node Setup | Ubuntu 24.04 runner | Docker Desktop |
| Python | Installed in CI job | Uses system Python + venv |
| Duration | ~5 min total | ~5-10 min (includes port-forward wait) |
| Debugging | GitHub Actions logs | Local terminal output |

## Further Reading

- [kind Documentation](https://kind.sigs.k8s.io/)
- [ExternalDNS Documentation](https://external-dns.sigs.k8s.io/)
- [Technitium DNS Documentation](https://technitium.com/dns/)
