# Technitium Credential Setup

This guide explains how to provision and manage credentials for the webhook. It covers creating Technitium users, storing credentials securely in Kubernetes, and configuring TLS for private certificate authorities.

For Kubernetes deployment details, see `docs/deployment/kubernetes.md`.

## Prerequisites

- Technitium DNS Server v5.0 or later
- Admin access to Technitium DNS web console
- `kubectl` access to Kubernetes cluster (for Helm/K8s deployments)

## Step 1: Create a Dedicated Technitium User

1. Sign in to Technitium DNS at `http://<technitium-host>:5380`
2. Navigate to **Administration** → **Users** → **Add User**
3. Create user account:
   - **Username:** `external-dns-webhook`
   - **Password:** Generate secure random: `openssl rand -base64 32`
   - **Permissions:** Grant DNS zone permissions for read/write access
4. Click **Create** and save credentials securely

## Step 2: Store Credentials in Kubernetes

```bash
# Create namespace
kubectl create namespace external-dns

# Create secret with credentials
kubectl create secret generic technitium-credentials \
  --from-literal=username='external-dns-webhook' \
  --from-literal=password='<your-secure-password>' \
  -n external-dns
```

## Step 3: TLS Configuration (Optional)

For HTTPS with private CA certificates:

```bash
# Create ConfigMap with CA certificate
kubectl create configmap technitium-ca-bundle \
  --from-file=ca.pem=/path/to/ca-certificate.pem \
  -n external-dns
```

Update Helm values:

```yaml
provider:
  webhook:
    env:
      - name: TECHNITIUM_URL
        value: "https://technitium-dns.technitium.svc.cluster.local:5380"
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

## Environment Variables

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

## Troubleshooting

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

## Additional Resources

- [Technitium DNS Documentation](https://technitium.com/dns/)
- [Kubernetes Secrets](https://kubernetes.io/docs/concepts/configuration/secret/)
- [Deployment Guide](deployment/kubernetes.md)
- [Security Best Practices](SECURITY.md)
