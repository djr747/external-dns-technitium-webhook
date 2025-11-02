# DNS Cleanup Policy Configuration

## Overview

ExternalDNS supports three policies for managing DNS records. The **`sync` policy (default)** is required for proper DNS record cleanup when services are deleted from your Kubernetes cluster.

## Policy Options

| Policy | Create | Update | Delete | Use Case |
|--------|--------|--------|--------|----------|
| **`sync`** (default) | ✅ Yes | ✅ Yes | ✅ Yes | Full lifecycle management (RECOMMENDED) |
| `upsert-only` | ✅ Yes | ✅ Yes | ❌ No | Prevent accidental deletions (legacy) |
| `create-only` | ✅ Yes | ❌ No | ❌ No | Manual record management |

## Default Configuration

The webhook works correctly with the **ExternalDNS default policy (`--policy=sync`)**. This ensures:

- ✅ DNS records are **created** when services are added
- ✅ DNS records are **updated** when services are modified  
- ✅ DNS records are **deleted** when services are removed
- ✅ Tracking TXT records are properly managed throughout the lifecycle

## Deployment Configuration

### Helm Installation

When deploying ExternalDNS with this webhook via Helm, ensure you use the default policy:

```bash
# Option 1: Use default (no need to specify)
helm install external-dns external-dns/external-dns \
  --namespace external-dns \
  --values values-technitium.yaml

# Option 2: Explicitly set sync policy (if needed)
helm install external-dns external-dns/external-dns \
  --namespace external-dns \
  --set policy=sync \
  --values values-technitium.yaml
```

### Kubectl Deployment

If deploying with kubectl, ensure the deployment includes:

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: external-dns
spec:
  template:
    spec:
      containers:
      - name: external-dns
        args:
        - --provider=webhook
        - --policy=sync  # ← REQUIRED for cleanup
        - --webhook-provider-url=http://localhost:8888
        # ... other args
```

### Changing Existing Deployment

If you need to change an existing deployment to use the `sync` policy:

```bash
# Using kubectl patch
kubectl patch deployment external-dns -n external-dns \
  -p '{"spec":{"template":{"spec":{"containers":[{"name":"external-dns","args":["--log-level=info","--policy=sync",...]}]}}}}'

# Or re-install with Helm
helm upgrade external-dns external-dns/external-dns \
  --namespace external-dns \
  --set policy=sync \
  --values values-technitium.yaml
```

## Lifecycle Example

### With `sync` Policy (Recommended)

```
1. Service created in Kubernetes
   ↓
2. ExternalDNS detects service
   ↓
3. Webhook adds DNS records to Technitium
   ✓ service-name.example.com → IP
   ✓ kuber-external-dns-a-service-name.example.com → TXT (ownership tracking)
   ↓
4. Service deleted from Kubernetes
   ↓
5. ExternalDNS detects deletion
   ↓
6. Webhook removes DNS records from Technitium
   ✓ service-name.example.com → DELETED
   ✓ kuber-external-dns-a-service-name.example.com → DELETED
   ↓
7. DNS queries return NXDOMAIN
```

### With `upsert-only` Policy (Not Recommended)

```
1-3. Same as above
4. Service deleted from Kubernetes
   ↓
5. ExternalDNS detects deletion
   ↓
6. ExternalDNS takes NO ACTION (policy blocks deletions)
   ✗ service-name.example.com → REMAINS IN DNS
   ✗ kuber-external-dns-a-service-name.example.com → REMAINS IN DNS
   ↓
7. DNS queries still resolve (orphaned records)
```

## Testing the Policy

### Test Creation and Deletion

```bash
# Create test service
cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: Service
metadata:
  name: test-cleanup
  namespace: default
  annotations:
    external-dns.alpha.kubernetes.io/hostname: test-cleanup.example.com
spec:
  type: LoadBalancer
  selector:
    app: test
  ports:
    - port: 80
      targetPort: 8080
  externalIPs:
    - 192.0.2.100
EOF

# Wait for DNS update (~60 seconds)
sleep 60

# Verify record created
nslookup test-cleanup.example.com <technitium-server-ip>
# Expected: test-cleanup.example.com → 192.0.2.100

# Delete service
kubectl delete svc test-cleanup

# Wait for DNS update (~60 seconds)
sleep 60

# Verify record deleted
nslookup test-cleanup.example.com <technitium-server-ip>
# Expected: NXDOMAIN (with sync policy) or still resolves (with upsert-only policy)
```

## Webhook Support

The webhook correctly implements both operations:

- ✅ `/records` POST with `type: "DELETE"` - Removes DNS records
- ✅ `/records` POST with `type: "CREATE"` - Adds DNS records

Example webhook log output:

```
INFO - Deleting record test-cleanup.example.com with data {'ipAddress': '192.0.2.100'}
POST https://technitium-server:53443/api/zones/records/delete → 200 OK
```

## Monitoring

### Check ExternalDNS Policy

```bash
# Get deployment args
kubectl get deployment external-dns -n external-dns -o yaml | grep policy

# Expected output:
# - --policy=sync
```

### Verify Deletions in Logs

```bash
# Check webhook logs for delete operations
kubectl logs -n external-dns deployment/external-dns -c webhook | grep -i delete

# Check ExternalDNS logs for reconciliation
kubectl logs -n external-dns deployment/external-dns -c external-dns | grep -i "updating\|deleting"
```

### Monitor DNS Records

```bash
# Query Technitium API to see current records
curl -s -k -X POST https://technitium-server:53443/api/zones/records/get \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer <token>" \
  -d '{"zone":"example.com"}' | jq '.records | length'
```

## Troubleshooting

### Records Not Being Deleted

1. **Check ExternalDNS policy**:
   ```bash
   kubectl get deployment external-dns -n external-dns -o yaml | grep policy
   ```
   Should show: `--policy=sync`

2. **Check webhook logs for errors**:
   ```bash
   kubectl logs -n external-dns deployment/external-dns -c webhook | grep -i error
   ```

3. **Verify Technitium API connectivity**:
   ```bash
   kubectl exec -it -n external-dns deployment/external-dns -c webhook -- \
     curl -k -X POST https://<technitium-server>:53443/api/user/login \
     -H "Content-Type: application/json" \
     -d '{"username":"admin","password":"..."}'
   ```

4. **Check sync interval**:
   - Default: `--interval=1m0s` (ExternalDNS checks every 60 seconds)
   - If no changes detected, check if service was actually deleted

### Orphaned Records

If you see DNS records for deleted services:

1. **Verify policy**: Most likely cause is `--policy=upsert-only`
2. **Update policy** to `--policy=sync`
3. **Manual cleanup**: Query and delete stale records via Technitium API

## References

- [ExternalDNS Flags Documentation](https://kubernetes-sigs.github.io/external-dns/latest/docs/flags/)
- [ExternalDNS Policy Flag](https://kubernetes-sigs.github.io/external-dns/latest/docs/flags/) - `--policy` option
- [ExternalDNS Webhook Provider](https://kubernetes-sigs.github.io/external-dns/latest/docs/tutorials/webhook-provider/)
