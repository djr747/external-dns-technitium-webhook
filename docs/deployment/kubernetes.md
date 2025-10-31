# Kubernetes Deployment Guide# Kubernetes Deployment with Helm# Deployment Checklist



Deploy the Technitium webhook as a sidecar container next to ExternalDNS. This guide focuses on the minimum Helm configuration; adapt it to your platform and tooling.



## PrerequisitesThis guide shows how to deploy the Technitium webhook alongside ExternalDNS using Helm.This checklist will guide you through deploying the external-dns-technitium-webhook to production.

- Kubernetes 1.19+ with cluster-admin rights (or equivalent)

- Helm 3.x

- Technitium DNS reachable from the cluster

- Credentials created per `docs/CREDENTIALS_SETUP.md`## Prerequisites## Prerequisites ✅



## Step 1 – Prepare Secrets and Namespace

```bash

kubectl create namespace external-dns --dry-run=client -o yaml | kubectl apply -f -- Kubernetes cluster (1.19+)### Required

# Credentials secret (username/password fields)

# See docs/CREDENTIALS_SETUP.md for details- Helm 3.x installed- [ ] Technitium DNS Server (v5.0+)

```

- Technitium DNS Server running and accessible  - Installation: https://technitium.com/dns/

## Step 2 – Author Helm Values

Create `values-technitium.yaml` with the webhook sidecar configuration:- API token from Technitium  - API access enabled



```yaml  - API token created

provider:

  name: webhook## Deploy as ExternalDNS Sidecar (Recommended)- [ ] Kubernetes cluster (for ExternalDNS integration)

  webhook:

    image:  - ExternalDNS deployed: https://github.com/kubernetes-sigs/external-dns

      repository: ghcr.io/<YOUR_ORG>/external-dns-technitium-webhook

      tag: latestThis approach deploys the webhook as a sidecar container in the ExternalDNS pod for maximum efficiency.  - Webhook provider enabled

    env:

      - name: TECHNITIUM_URL- [ ] Docker or Podman (for container builds)

        value: "http://technitium-dns.technitium.svc.cluster.local:5380"

      - name: TECHNITIUM_USERNAME### Step 1: Add ExternalDNS Helm Repository

        valueFrom:

          secretKeyRef:### Optional but Recommended

            name: technitium-credentials

            key: username```bash- [ ] GitHub Actions (for CI/CD automation)

      - name: TECHNITIUM_PASSWORD

        valueFrom:helm repo add external-dns https://kubernetes-sigs.github.io/external-dns/- [ ] Container registry (GHCR, Docker Hub, or private registry)

          secretKeyRef:

            name: technitium-credentialshelm repo update- [ ] Prometheus/Grafana (for monitoring)

            key: password

      - name: ZONE```

        value: "example.com"

      - name: DOMAIN_FILTERS## Pre-Deployment Verification

        value: "example.com"  # optional

    resources:### Step 2: Create Technitium Secret

      requests:

        cpu: 50m### 1. Code Quality ✅

        memory: 64Mi

      limits:```bash```bash

        cpu: 200m

        memory: 128Mikubectl create namespace external-dns# Run tests

    securityContext:

      runAsNonRoot: truemake test

      allowPrivilegeEscalation: false

      readOnlyRootFilesystem: truekubectl create secret generic technitium-webhook \



sources:  --from-literal=api-token='your-technitium-api-token-here' \# Check linting

  - service

  - ingress  -n external-dnsmake lint

registry: txt

policy: upsert-only```

interval: 1m

```# Run security scans



If you operate multiple Technitium endpoints, add `TECHNITIUM_FAILOVER_URLS` with a semicolon-separated list.### Step 3: Create Helm Values Filemake security-check



## Step 3 – Install or Upgrade ExternalDNS

```bash

helm repo add external-dns https://kubernetes-sigs.github.io/external-dns/Create `external-dns-values.yaml`:# Expected: All tests passing (30/30), no critical issues

helm repo update

```

helm upgrade --install external-dns external-dns/external-dns \

  --namespace external-dns \```yaml

  --create-namespace \

  --values values-technitium.yaml# External DNS configuration### 2. Docker Build ✅

```

provider:```bash

Helm handles both fresh installs and upgrades; re-run the command whenever you update configuration or image versions.

  name: webhook# Build multi-platform image

## Step 4 – Validate the Deployment

```bashmake docker-build

kubectl get pods -n external-dns

kubectl logs -n external-dns deploy/external-dns -c webhook --tail=20# Webhook provider configuration

kubectl logs -n external-dns deploy/external-dns -c external-dns --tail=20

extraArgs:# Or build for specific platform

# Forward the health endpoint if required

kubectl port-forward -n external-dns deploy/external-dns 3000:3000 &  - --webhook-provider-url=http://localhost:8888docker build -t technitium-dns-webhook:latest .

curl -s http://127.0.0.1:3000/health

```



You should see a `200 OK` response once the webhook authenticates with Technitium. ExternalDNS logs should confirm the webhook provider is connected.# Add Technitium webhook as sidecar# Expected: Build succeeds, image ~200MB



## Step 5 – Test Record Synchronisationsidecars:```

```bash

kubectl apply -f - <<'EOF'  - name: technitium-webhook

apiVersion: v1

kind: Service    image: ghcr.io/yourusername/external-dns-technitium-webhook:latest### 3. Configuration Validation ✅

metadata:

  name: webhook-smoke-test    imagePullPolicy: IfNotPresent```bash

  annotations:

    external-dns.alpha.kubernetes.io/hostname: smoke.example.com    ports:# Test with actual Technitium credentials

spec:

  selector: { app: kubernetes }      - containerPort: 8888export TECHNITIUM_API_URL="http://your-technitium-server:5380"

  ports:

    - port: 80        name: httpexport TECHNITIUM_API_TOKEN="your-api-token-here"

EOF

        protocol: TCPexport DOMAIN_FILTER="example.com,test.example.com"

sleep 60

kubectl logs -n external-dns deploy/external-dns -c external-dns --tail=20    env:

kubectl delete service webhook-smoke-test

```      - name: TECHNITIUM_API_URL# Run locally



Verify the record in Technitium (Service → Zones → `example.com`). Remove the test service once confirmed.        value: "http://technitium-dns.default.svc.cluster.local:5380"python -m uvicorn external_dns_technitium_webhook.main:app --host 0.0.0.0 --port 8888



## Maintenance Tips      - name: TECHNITIUM_API_TOKEN

- **Updates:** Bump the container tag in `values-technitium.yaml` and rerun the Helm upgrade.

- **Scaling:** Increase the ExternalDNS deployment replicas; the webhook sidecar scales with it.        valueFrom:# Test health endpoint

- **Rotation:** After rotating credentials, re-apply the secret and restart the deployment (`kubectl rollout restart deployment/external-dns -n external-dns`).

- **Monitoring:** Surfaced metrics include Kubernetes readiness probes and structured logs; consider forwarding logs to your existing platform.          secretKeyRef:curl http://localhost:8888/healthz


            name: technitium-webhook# Expected: {"ready":true}

            key: api-token```

      - name: DOMAIN_FILTER

        value: "example.com"## Deployment Steps

      - name: LOG_LEVEL

        value: "INFO"### Option 1: Docker Compose (Simplest)

      - name: LISTEN_PORT

        value: "8888"1. **Configure environment:**

    resources:```bash

      requests:# Edit docker-compose.yml with your values

        cpu: 50mTECHNITIUM_API_URL=http://technitium:5380

        memory: 64MiTECHNITIUM_API_TOKEN=your-token

      limits:DOMAIN_FILTER=example.com

        cpu: 200m```

        memory: 128Mi

    livenessProbe:2. **Deploy:**

      httpGet:```bash

        path: /healthzdocker-compose up -d

        port: 8888```

      initialDelaySeconds: 10

      periodSeconds: 303. **Verify:**

    readinessProbe:```bash

      httpGet:curl http://localhost:8888/healthz

        path: /healthz```

        port: 8888

      initialDelaySeconds: 5### Option 2: Kubernetes Deployment (Production)

      periodSeconds: 10

    securityContext:1. **Create namespace:**

      allowPrivilegeEscalation: false```bash

      readOnlyRootFilesystem: truekubectl create namespace external-dns

      runAsNonRoot: true```

      runAsUser: 1000

      capabilities:2. **Create secret with API token:**

        drop:```bash

          - ALLkubectl create secret generic technitium-webhook-secret \

  --from-literal=api-token=your-token-here \

# Resource limits for ExternalDNS  -n external-dns

resources:```

  requests:

    cpu: 50m3. **Create ConfigMap:**

    memory: 64Mi```yaml

  limits:# technitium-webhook-config.yaml

    cpu: 200mapiVersion: v1

    memory: 128Mikind: ConfigMap

metadata:

# Service account  name: technitium-webhook-config

serviceAccount:  namespace: external-dns

  create: truedata:

  name: external-dns  TECHNITIUM_API_URL: "http://technitium-dns.default.svc.cluster.local:5380"

  DOMAIN_FILTER: "example.com,*.example.com"

# RBAC  LOG_LEVEL: "INFO"

rbac:```

  create: true

```bash

# Sources to watchkubectl apply -f technitium-webhook-config.yaml

sources:```

  - service

  - ingress4. **Deploy webhook:**

```yaml

# Policy for record synchronization# technitium-webhook-deployment.yaml

policy: syncapiVersion: apps/v1

kind: Deployment

# Loggingmetadata:

logLevel: info  name: technitium-webhook

```  namespace: external-dns

spec:

### Step 4: Deploy with Helm  replicas: 2  # High availability

  selector:

```bash    matchLabels:

helm upgrade --install external-dns external-dns/external-dns \      app: technitium-webhook

  --namespace external-dns \  template:

  --create-namespace \    metadata:

  --values external-dns-values.yaml      labels:

```        app: technitium-webhook

    spec:

### Step 5: Verify Deployment      securityContext:

        runAsNonRoot: true

```bash        runAsUser: 1000

# Check pods        fsGroup: 1000

kubectl get pods -n external-dns      containers:

      - name: webhook

# Check logs        image: ghcr.io/your-org/technitium-dns-webhook:latest

kubectl logs -n external-dns -l app.kubernetes.io/name=external-dns -c technitium-webhook        imagePullPolicy: Always

        ports:

# Test health endpoint        - containerPort: 8888

kubectl port-forward -n external-dns svc/external-dns 8888:8888          name: http

curl http://localhost:8888/healthz        env:

```        - name: TECHNITIUM_API_TOKEN

          valueFrom:

## Testing            secretKeyRef:

              name: technitium-webhook-secret

Create a test service:              key: api-token

        envFrom:

```yaml        - configMapRef:

apiVersion: v1            name: technitium-webhook-config

kind: Service        livenessProbe:

metadata:          httpGet:

  name: test-service            path: /healthz

  annotations:            port: 8888

    external-dns.alpha.kubernetes.io/hostname: test.example.com          initialDelaySeconds: 10

spec:          periodSeconds: 30

  type: LoadBalancer        readinessProbe:

  ports:          httpGet:

  - port: 80            path: /healthz

  selector:            port: 8888

    app: test          initialDelaySeconds: 5

```          periodSeconds: 10

        resources:

Verify DNS record in Technitium after 30-60 seconds.          requests:

            memory: "64Mi"

## Resource Recommendations            cpu: "100m"

          limits:

**Minimum:**            memory: "256Mi"

```yaml            cpu: "500m"

requests: {cpu: 50m, memory: 64Mi}        securityContext:

limits: {cpu: 100m, memory: 128Mi}          allowPrivilegeEscalation: false

```          readOnlyRootFilesystem: true

          capabilities:

**Production:**            drop:

```yaml            - ALL

requests: {cpu: 100m, memory: 64Mi}---

limits: {cpu: 200m, memory: 128Mi}apiVersion: v1

```kind: Service

metadata:

## Support  name: technitium-webhook

  namespace: external-dns

See [main documentation](../../README.md) for more details.spec:

  selector:
    app: technitium-webhook
  ports:
  - protocol: TCP
    port: 80
    targetPort: 8888
  type: ClusterIP
```

```bash
kubectl apply -f technitium-webhook-deployment.yaml
```

5. **Configure ExternalDNS to use webhook:**
```yaml
# external-dns-config.yaml (add to ExternalDNS deployment)
args:
- --source=service
- --source=ingress
- --provider=webhook
- --webhook-provider-url=http://technitium-webhook.external-dns.svc.cluster.local
```

6. **Verify deployment:**
```bash
# Check pods
kubectl get pods -n external-dns

# Check logs
kubectl logs -n external-dns -l app=technitium-webhook

# Test webhook endpoint
kubectl run -it --rm debug --image=curlimages/curl --restart=Never -- \
  curl http://technitium-webhook.external-dns.svc.cluster.local/healthz
```

### Option 3: Standalone Service (Development)

1. **Install dependencies:**
```bash
python -m venv .venv
source .venv/bin/activate  # or `.venv\Scripts\activate` on Windows
pip install -e ".[dev]"
```

2. **Configure environment:**
```bash
export TECHNITIUM_API_URL="http://localhost:5380"
export TECHNITIUM_API_TOKEN="your-token"
export DOMAIN_FILTER="example.com"
```

3. **Run server:**
```bash
python -m uvicorn external_dns_technitium_webhook.main:app \
  --host 0.0.0.0 \
  --port 8888 \
  --reload  # For development
```

## Post-Deployment Verification

### 1. Health Checks ✅
```bash
# Basic health
curl http://webhook-url:8888/

# Ready status
curl http://webhook-url:8888/healthz

# Expected: {"ready":true}
```

### 2. ExternalDNS Integration Test ✅
```bash
# Create test service
kubectl apply -f - <<EOF
apiVersion: v1
kind: Service
metadata:
  name: test-service
  annotations:
    external-dns.alpha.kubernetes.io/hostname: test.example.com
spec:
  type: LoadBalancer
  ports:
  - port: 80
  selector:
    app: test
EOF

# Wait 30-60 seconds, then check Technitium DNS
# Expected: A record for test.example.com created
```

### 3. Enhanced Features Test ✅

**Test CAA records (Let's Encrypt):**
```bash
# Add annotation to ingress
external-dns.alpha.kubernetes.io/target: "0 issue letsencrypt.org"
external-dns.alpha.kubernetes.io/record-type: CAA

# Verify in Technitium DNS
# Expected: CAA record created
```

**Test auto-cleanup:**
```bash
# Add annotation for 24-hour expiry
external-dns.alpha.kubernetes.io/ttl: "86400"

# Verify record expires after 24 hours
# Expected: Record auto-deleted
```

## Monitoring and Maintenance

### Logging
```bash
# View logs in real-time
kubectl logs -f -n external-dns -l app=technitium-webhook

# Filter for errors
kubectl logs -n external-dns -l app=technitium-webhook | grep ERROR
```

### Metrics (Optional)
If you implemented Prometheus metrics:
```yaml
# ServiceMonitor for Prometheus Operator
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: technitium-webhook
  namespace: external-dns
spec:
  selector:
    matchLabels:
      app: technitium-webhook
  endpoints:
  - port: http
    path: /metrics
```

### Security Updates
```bash
# Regular dependency updates
pip install --upgrade pip
pip install --upgrade -r requirements.txt

# Security scans
make security-check

# Rebuild Docker image
make docker-build
```

## Troubleshooting

### Common Issues

**1. Authentication Error**
```
Error: Invalid token
```
**Solution:** Verify TECHNITIUM_API_TOKEN is correct:
```bash
curl -X POST http://technitium:5380/api/user/login \
  -d "token=your-token"
```

**2. Domain Filter Mismatch**
```
Warning: Domain not in filter
```
**Solution:** Add domain to DOMAIN_FILTER:
```bash
export DOMAIN_FILTER="example.com,newdomain.com"
```

**3. Connection Timeout**
```
Error: Connection timeout
```
**Solution:** Check Technitium DNS is reachable:
```bash
curl http://technitium:5380/api/zones/list
```

**4. Record Not Created**
```
Warning: Failed to create record
```
**Solution:** Check ExternalDNS logs and webhook logs:
```bash
kubectl logs -n external-dns -l app=external-dns
kubectl logs -n external-dns -l app=technitium-webhook
```

### Debug Mode
Enable detailed logging:
```bash
export LOG_LEVEL="DEBUG"
# Or in Kubernetes ConfigMap:
# LOG_LEVEL: "DEBUG"
```

### Health Check Failures
```bash
# Check pod status
kubectl describe pod -n external-dns -l app=technitium-webhook

# Check service endpoints
kubectl get endpoints -n external-dns technitium-webhook

# Test directly
kubectl port-forward -n external-dns svc/technitium-webhook 8888:80
curl http://localhost:8888/healthz
```

## Rollback Procedure

If you need to rollback:

1. **Docker Compose:**
```bash
docker-compose down
# Restore previous docker-compose.yml
docker-compose up -d
```

2. **Kubernetes:**
```bash
# Rollback to previous version
kubectl rollout undo deployment/technitium-webhook -n external-dns

# Or specific revision
kubectl rollout history deployment/technitium-webhook -n external-dns
kubectl rollout undo deployment/technitium-webhook --to-revision=2 -n external-dns
```

## Security Considerations

### Production Hardening
- [ ] Use TLS for Technitium API communication
- [ ] Implement network policies to restrict pod communication
- [ ] Rotate API tokens regularly
- [ ] Run security scans before each deployment
- [ ] Use read-only root filesystem
- [ ] Drop all Linux capabilities
- [ ] Run as non-root user (UID 1000)
- [ ] Enable pod security policies/standards
- [ ] Use secrets management (HashiCorp Vault, Sealed Secrets)
- [ ] Implement rate limiting
- [ ] Enable audit logging

### Secrets Management
```bash
# Using external secrets operator
apiVersion: external-secrets.io/v1beta1
kind: ExternalSecret
metadata:
  name: technitium-webhook-secret
  namespace: external-dns
spec:
  secretStoreRef:
    name: vault-backend
    kind: SecretStore
  target:
    name: technitium-webhook-secret
  data:
  - secretKey: api-token
    remoteRef:
      key: technitium/api-token
```

## Performance Tuning

### Scaling
```bash
# Horizontal Pod Autoscaler
kubectl autoscale deployment technitium-webhook \
  --cpu-percent=70 \
  --min=2 \
  --max=10 \
  -n external-dns
```

### Resource Limits
Adjust based on your load:
```yaml
resources:
  requests:
    memory: "64Mi"   # Minimum for startup
    cpu: "100m"      # 0.1 CPU
  limits:
    memory: "256Mi"  # Maximum memory
    cpu: "500m"      # 0.5 CPU
```

### Caching (Future Enhancement)
Consider implementing Redis cache for frequently accessed records.

## Support and Documentation

### Resources
- **Main README:** `README.md`
- **API Documentation:** 
  - Swagger UI: `http://localhost:3000/docs`
  - ReDoc: `http://localhost:3000/redoc`
  - OpenAPI JSON: `http://localhost:3000/openapi.json`
- **API Reference:** `docs/API.md`
- **Development Guide:** `docs/DEVELOPMENT.md` - Includes quick start, testing, and workflow

### Getting Help
1. Check existing documentation
2. Review logs for error messages
3. Search GitHub issues
4. Create new issue with:
   - Environment details (Kubernetes version, Technitium version)
   - Configuration (sanitized)
   - Error logs
   - Steps to reproduce

## Compliance and Auditing

### Audit Trail
All DNS changes are logged with:
- Timestamp
- Record type
- Domain name
- Action (create/delete)
- Source (ExternalDNS service/ingress)

Enable audit logging in Technitium DNS Server for complete audit trail.

### Compliance Requirements
- [ ] Document all production changes
- [ ] Maintain change log
- [ ] Regular security audits
- [ ] Backup DNS configuration
- [ ] Test disaster recovery procedures

## Success Criteria ✅

Your deployment is successful when:
- [ ] Health checks return ready status
- [ ] ExternalDNS successfully creates records
- [ ] Records appear in Technitium DNS within 60 seconds
- [ ] DNS queries resolve correctly
- [ ] No error messages in logs
- [ ] Monitoring dashboards show healthy metrics
- [ ] Test service/ingress creates expected DNS records
- [ ] Enhanced features (CAA, ANAME, etc.) work as expected

## Next Steps

After successful deployment:
1. Monitor for 24-48 hours
2. Implement Prometheus metrics (optional)
3. Set up alerting rules
4. Document any environment-specific configuration
5. Train team on new features (CAA, auto-cleanup, etc.)
6. Plan regular maintenance windows for updates

---

**Need help?** Check `docs/ENHANCEMENTS.md` for detailed feature documentation and examples.
