# Technitium Credential Setup

This guide explains how to provision and manage credentials for the webhook. It covers creating Technitium users, storing credentials securely in Kubernetes, and configuring TLS for private certificate authorities.

For Kubernetes deployment details, see `docs/deployment/kubernetes.md`.

## Prerequisites

- Technitium DNS Server v5.0 or later
- Admin access to Technitium DNS web console
- `kubectl` access to Kubernetes cluster (for Helm/K8s deployments)

## Step 1: Create a Dedicated Technitium User

1. Sign in to Technitium DNS at `https://<technitium-host>:53443`; this is also the HTTPS endpoint required by the webhook
2. Navigate to **Administration** → **Users** → **Add User**
3. Create user account:
   - **Username:** `external-dns-webhook`
   - **Password:** Generate secure random: `openssl rand -base64 32`
4. Click **Create** and save credentials securely

## Step 2: Grant Required Permissions

The webhook requires membership in the **DNS admin group** to access the API. After creating the user:

1. Navigate to **Administration** → **Groups**
2. Edit the **DNS admin** group
3. Add `external-dns-webhook` user to the group
4. Save changes

This grants the user the necessary API permissions to:

- Authenticate via `/api/user/login`
- List zones via `/api/zones/list`
- Create zones via `/api/zones/create`
- Add/get DNS records via `/api/zones/records/*`

**Note:** Technitium DNS uses different ports for HTTP (5380) and HTTPS (53443).

## Step 3: Store Credentials in Kubernetes

```bash
# Create namespace
kubectl create namespace external-dns

# Create secret with credentials
kubectl create secret generic technitium-credentials \
  --from-literal=username='external-dns-webhook' \
  --from-literal=password='<your-secure-password>' \
  -n external-dns
```

## TLS Configuration

The webhook connects to Technitium only through an HTTPS endpoint. Certificate-chain and hostname verification are always enabled. HTTP Technitium endpoints and disabled verification are rejected during startup.

### Private or self-signed certificate authorities

For a private or self-signed Technitium certificate, mount the issuing CA PEM file into the webhook Pod and configure:

```yaml
env:
  - name: TECHNITIUM_URL
    value: "https://dns.example.com:53443"
  - name: TECHNITIUM_CA_BUNDLE_FILE
    value: "/etc/technitium-ca/ca.crt"
```

Create a ConfigMap from the public CA certificate and mount it read-only at `/etc/technitium-ca`. The CA bundle extends normal certificate trust; it does not disable certificate or hostname verification.

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
        value: "https://technitium-dns.technitium.svc.cluster.local:53443"
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

> **Port configuration:** ExternalDNS calls the webhook on port **8888** and
> probes `/health` on **8080**. These ports are hard‑coded in the sidecar and
> cannot be changed in production; the `LISTEN_PORT`/`HEALTH_PORT` settings are
> only used for local testing.

| Variable | Required | Default | Purpose |
| ---------- | ---------- | --------- | --------- |
| `TECHNITIUM_URL` | Yes | None | HTTPS Technitium DNS API endpoint (normally port 53443) |
| `TECHNITIUM_USERNAME` | Yes | None | Username for authentication |
| `TECHNITIUM_PASSWORD` | Yes | None | Password for authentication |
| `ZONE` | Yes | None | Primary DNS zone for management |
| `DOMAIN_FILTERS` | No | None | Semicolon-separated list of domains |
| `TECHNITIUM_CA_BUNDLE_FILE` | No | None | Path to PEM file with CA certificate |
| `TECHNITIUM_TIMEOUT` | No | `10.0` | HTTP client timeout in seconds |
| `TECHNITIUM_FAILOVER_URLS` | No | None | Semicolon-separated list of failover Technitium URLs for HA |
| `TECHNITIUM_ENABLE_REQUEST_COMPRESSION` | No | `false` | Enable gzip compression for large request bodies |
| `TECHNITIUM_COMPRESSION_THRESHOLD_BYTES` | No | `32768` | Minimum request size for compression (32KB) |
| `CATALOG_ZONE` | No | None | Catalog zone name for advanced DNS setups |
| `LOG_LEVEL` | No | `INFO` | Logging level: DEBUG, INFO, WARNING, ERROR |
| `LISTEN_ADDRESS` | No | `0.0.0.0` | Address to bind the webhook server |
| `REQUESTS_PER_MINUTE` | No | `1000` | Rate limiting: requests per minute |
| `RATE_LIMIT_BURST` | No | `10` | Rate limiting: burst allowance |
| `HEALTH_POLLING_INTERVAL_SECONDS` | No | `15.0` | Poll interval for endpoint health checks and automatic primary failback |

## Troubleshooting

### Authentication Failures

1. Verify credentials in Kubernetes Secret:

   ```bash
   kubectl get secret technitium-credentials -n external-dns \
     -o jsonpath='{.data.username}' | base64 -d
   ```

2. Test credentials manually:

   ```bash
   curl -X POST "https://technitium:53443/api/user/login" \
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
- [Technitium DNS HTTP API Documentation](https://github.com/TechnitiumSoftware/DnsServer/blob/master/APIDOCS.md)
- [Catalog Zones (RFC 9432)](https://datatracker.ietf.org/doc/rfc9432/)
- [Kubernetes Secrets](https://kubernetes.io/docs/concepts/configuration/secret/)
- [Deployment Guide](deployment/kubernetes.md)
- [Security Best Practices](SECURITY.md)
