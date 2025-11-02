# Kubernetes Deployment Guide

Deploy the Technitium webhook as a sidecar container next to ExternalDNS in Kubernetes. This guide covers Helm-based deployment, standalone deployments, and configuration options including private CA support.

## Prerequisites

- Kubernetes cluster 1.19+ with sufficient RBAC permissions
- Helm 3.x installed
- Technitium DNS Server v5.0+ accessible from the cluster
- Credentials created per `docs/CREDENTIALS_SETUP.md`

## Quick Start: Helm Deployment (Recommended)

### Step 1: Add ExternalDNS Helm Repository

```bash
helm repo add external-dns https://kubernetes-sigs.github.io/external-dns/
helm repo update
```

### Step 2: Create Kubernetes Namespace and Secrets

```bash
# Create namespace
kubectl create namespace external-dns

# Create secret with Technitium credentials
kubectl create secret generic technitium-credentials \
  --from-literal=username='external-dns-webhook' \
  --from-literal=password='<your-secure-password>' \
  -n external-dns
```

### Step 3: Create Helm Values File

Create `values-technitium.yaml` with the webhook sidecar configuration:

```yaml
provider:
  name: webhook
  webhook:
    image:
      repository: ghcr.io/dj747/external-dns-technitium-webhook
      tag: v1.0.0  # Use your released version
    env:
      - name: TECHNITIUM_URL
        value: "http://technitium-dns.technitium.svc.cluster.local:5380"
      - name: TECHNITIUM_USERNAME
        valueFrom:
          secretKeyRef:
            name: technitium-credentials
            key: username
      - name: TECHNITIUM_PASSWORD
        valueFrom:
          secretKeyRef:
            name: technitium-credentials
            key: password
      - name: ZONE
        value: "example.com"
      - name: DOMAIN_FILTERS
        value: "example.com"
      - name: LOG_LEVEL
        value: "INFO"
```

### Step 4: Install ExternalDNS with Webhook

```bash
helm install external-dns external-dns/external-dns \
  --namespace external-dns \
  --values values-technitium.yaml \
  --set provider.webhook.url="http://127.0.0.1:8888" \
  --set provider.webhook.httpClient.timeout="30s"
```

## TLS Configuration (Optional)

For HTTPS with private CA certificates:

```bash
# Create ConfigMap with CA certificate
kubectl create configmap technitium-ca-bundle \
  --from-file=ca.pem=/path/to/ca-certificate.pem \
  -n external-dns
```

Update your Helm values to include TLS configuration:

```yaml
provider:
  webhook:
    env:
      - name: TECHNITIUM_VERIFY_SSL
        value: "true"
      - name: TECHNITIUM_CA_BUNDLE_FILE
        value: "/etc/technitium-ssl/ca.pem"
    volumeMounts:
      - name: technitium-ca-bundle
        mountPath: /etc/technitium-ssl
        readOnly: true

volumes:
  - name: technitium-ca-bundle
    configMap:
      name: technitium-ca-bundle
      items:
        - key: ca.pem
          path: ca.pem
```

## Standalone Deployment

If you prefer not to use Helm, you can deploy the webhook as a standalone service:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: external-dns-technitium-webhook
  namespace: external-dns
spec:
  replicas: 1
  selector:
    matchLabels:
      app: external-dns-technitium-webhook
  template:
    metadata:
      labels:
        app: external-dns-technitium-webhook
    spec:
      containers:
      - name: webhook
        image: ghcr.io/djr747/external-dns-technitium-webhook:v1.0.0
        ports:
        - containerPort: 8888
          name: webhook
        - containerPort: 8080
          name: health
        env:
        - name: TECHNITIUM_URL
          value: "http://technitium-dns.technitium.svc.cluster.local:5380"
        - name: TECHNITIUM_USERNAME
          valueFrom:
            secretKeyRef:
              name: technitium-credentials
              key: username
        - name: TECHNITIUM_PASSWORD
          valueFrom:
            secretKeyRef:
              name: technitium-credentials
              key: password
        - name: ZONE
          value: "example.com"
        - name: DOMAIN_FILTERS
          value: "example.com"
        livenessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 30
          periodSeconds: 10
        readinessProbe:
          httpGet:
            path: /health
            port: 8080
          initialDelaySeconds: 5
          periodSeconds: 5
---
apiVersion: v1
kind: Service
metadata:
  name: external-dns-technitium-webhook
  namespace: external-dns
spec:
  selector:
    app: external-dns-technitium-webhook
  ports:
  - name: webhook
    port: 8888
    targetPort: 8888
  - name: health
    port: 8080
    targetPort: 8080
```

## Configuration Options

### Environment Variables

| Variable | Required | Default | Purpose |
|----------|----------|---------|---------|
| `TECHNITIUM_URL` | Yes | None | Technitium DNS Server API endpoint |
| `TECHNITIUM_USERNAME` | Yes | None | Username for authentication |
| `TECHNITIUM_PASSWORD` | Yes | None | Password for authentication |
| `ZONE` | Yes | None | Primary DNS zone for management |
| `DOMAIN_FILTERS` | No | None | Semicolon-separated list of domains |
| `TECHNITIUM_VERIFY_SSL` | No | `true` | Enable/disable SSL certificate verification |
| `TECHNITIUM_CA_BUNDLE_FILE` | No | None | Path to PEM file with CA certificate |
| `LOG_LEVEL` | No | `INFO` | Logging level: DEBUG, INFO, WARNING, ERROR |
| `LISTEN_ADDRESS` | No | `0.0.0.0` | Address to bind the webhook server |
| `LISTEN_PORT` | No | `8888` | Port for ExternalDNS webhook communication |
| `HEALTH_PORT` | No | `8080` | Port for health check endpoints |

### Resource Requirements

```yaml
provider:
  webhook:
    resources:
      requests:
        cpu: 100m
        memory: 128Mi
      limits:
        cpu: 500m
        memory: 256Mi
```

## Troubleshooting

### Webhook Connection Issues

1. Verify the webhook is running:
   ```bash
   kubectl get pods -n external-dns
   kubectl logs -n external-dns deployment/external-dns
   ```

2. Check webhook health:
   ```bash
   kubectl port-forward -n external-dns svc/external-dns-technitium-webhook 8080:8080
   curl http://localhost:8080/health
   ```

### Authentication Failures

1. Verify credentials in Kubernetes Secret:
   ```bash
   kubectl get secret technitium-credentials -n external-dns \
     -o jsonpath='{.data.username}' | base64 -d
   ```

2. Test credentials manually:
   ```bash
   curl -X POST "http://technitium:5380/api/user/login" \
     -d "username=external-dns-webhook&password=YOUR_PASSWORD"
   ```

### TLS Certificate Verification Failed

1. Verify CA ConfigMap is properly mounted:
   ```bash
   kubectl exec -n external-dns deploy/external-dns -c webhook -- \
     ls -la /etc/technitium-ssl/
   ```

2. Verify certificate content:
   ```bash
   kubectl get configmap technitium-ca-bundle -n external-dns \
     -o jsonpath='{.data.ca\.pem}' | openssl x509 -text -noout
   ```

## High Availability Considerations

If running ExternalDNS with multiple replicas:

- Ensure all replicas use the same Technitium credentials
- Store credentials in a single Kubernetes Secret
- Configure ExternalDNS with `--provider=webhook` and appropriate webhook URL

## Security Best Practices

- Use RBAC to limit ExternalDNS permissions
- Store credentials in Kubernetes Secrets (never in ConfigMaps)
- Enable TLS verification when possible
- Use private CA certificates for internal Technitium deployments
- Regularly rotate Technitium credentials

## Additional Resources

- [ExternalDNS Documentation](https://github.com/kubernetes-sigs/external-dns)
- [Helm Charts](https://artifacthub.io/packages/helm/external-dns/external-dns)
- [Technitium DNS Documentation](https://technitium.com/dns/)
- [Credentials Setup](../CREDENTIALS_SETUP.md)
- [Security Guide](../SECURITY.md)

