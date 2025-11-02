# Kubernetes Deployment Guide# Kubernetes Deployment Guide# Kubernetes Deployment with Helm# Deployment Checklist



Deploy the Technitium webhook as a sidecar container next to ExternalDNS in Kubernetes. This guide covers Helm-based deployment, standalone deployments, and configuration options including private CA support.



## PrerequisitesDeploy the Technitium webhook as a sidecar container next to ExternalDNS. This guide focuses on the minimum Helm configuration; adapt it to your platform and tooling.



- Kubernetes cluster 1.19+ with sufficient RBAC permissions

- Helm 3.x installed

- Technitium DNS Server v5.0+ accessible from the cluster## PrerequisitesThis guide shows how to deploy the Technitium webhook alongside ExternalDNS using Helm.This checklist will guide you through deploying the external-dns-technitium-webhook to production.

- API token from Technitium (see `docs/CREDENTIALS_SETUP.md`)

- For private CA: PEM certificate file (optional, see "TLS Configuration" section)- Kubernetes 1.19+ with cluster-admin rights (or equivalent)



## Quick Start: Helm Deployment (Recommended)- Helm 3.x



### Step 1: Add ExternalDNS Helm Repository- Technitium DNS reachable from the cluster



```bash- Credentials created per `docs/CREDENTIALS_SETUP.md`## Prerequisites## Prerequisites ✅

helm repo add external-dns https://kubernetes-sigs.github.io/external-dns/

helm repo update## High Availability (HA) credential note

```

If you plan to run ExternalDNS with multiple replicas (for HA), ensure the Technitium credentials are consistent across replicas. The webhook expects a single Technitium service account (username/password) to be used by all sidecars. Store the credentials in one Kubernetes Secret and reference the same secret in your Helm values so all replicas read the identical values. See `docs/CREDENTIALS_SETUP.md` for details.

### Step 2: Create Kubernetes Namespace and Secrets



```bash

# Create namespace## Step 1 – Prepare Secrets and Namespace

kubectl create namespace external-dns

```bash

# Create secret with Technitium credentials

kubectl create secret generic technitium-credentials \kubectl create namespace external-dns --dry-run=client -o yaml | kubectl apply -f -- Kubernetes cluster (1.19+)### Required

  --from-literal=username='technitium-user' \

  --from-literal=password='technitium-password' \# Credentials secret (username/password fields)

  -n external-dns

```# See docs/CREDENTIALS_SETUP.md for details- Helm 3.x installed- [ ] Technitium DNS Server (v5.0+)



### Step 3: Create Helm Values File```



Create `values-technitium.yaml`:- Technitium DNS Server running and accessible  - Installation: https://technitium.com/dns/



```yaml## Step 2 – Author Helm Values

provider:

  name: webhookCreate `values-technitium.yaml` with the webhook sidecar configuration:- API token from Technitium  - API access enabled

  webhook:

    image:

      repository: ghcr.io/<YOUR_ORG>/external-dns-technitium-webhook

      tag: v1.0.0  # Use your released version```yaml  - API token created

    env:

      - name: TECHNITIUM_URLprovider:

        value: "http://technitium-dns.technitium.svc.cluster.local:5380"

      - name: TECHNITIUM_USERNAME  name: webhook## Deploy as ExternalDNS Sidecar (Recommended)- [ ] Kubernetes cluster (for ExternalDNS integration)

        valueFrom:

          secretKeyRef:  webhook:

            name: technitium-credentials

            key: username    image:  - ExternalDNS deployed: https://github.com/kubernetes-sigs/external-dns

      - name: TECHNITIUM_PASSWORD

        valueFrom:      repository: ghcr.io/<YOUR_ORG>/external-dns-technitium-webhook

          secretKeyRef:

            name: technitium-credentials      tag: latestThis approach deploys the webhook as a sidecar container in the ExternalDNS pod for maximum efficiency.  - Webhook provider enabled

            key: password

      - name: ZONE    env:

        value: "example.com"

      - name: DOMAIN_FILTERS      - name: TECHNITIUM_URL- [ ] Docker or Podman (for container builds)

        value: "example.com"  # semicolon-separated list

      - name: LOG_LEVEL        value: "http://technitium-dns.technitium.svc.cluster.local:5380"

        value: "INFO"

      - name: LISTEN_PORT      - name: TECHNITIUM_USERNAME### Step 1: Add ExternalDNS Helm Repository

        value: "3000"

    resources:        valueFrom:

      requests:

        cpu: 50m          secretKeyRef:### Optional but Recommended

        memory: 64Mi

      limits:            name: technitium-credentials

        cpu: 200m

        memory: 128Mi            key: username```bash- [ ] GitHub Actions (for CI/CD automation)

    securityContext:

      runAsNonRoot: true      - name: TECHNITIUM_PASSWORD

      allowPrivilegeEscalation: false

      readOnlyRootFilesystem: true        valueFrom:helm repo add external-dns https://kubernetes-sigs.github.io/external-dns/- [ ] Container registry (GHCR, Docker Hub, or private registry)

      capabilities:

        drop:          secretKeyRef:

          - ALL

    livenessProbe:            name: technitium-credentialshelm repo update- [ ] Prometheus/Grafana (for monitoring)

      httpGet:

        path: /health            key: password

        port: 3000

      initialDelaySeconds: 10      - name: ZONE```

      periodSeconds: 30

    readinessProbe:        value: "example.com"

      httpGet:

        path: /health      - name: DOMAIN_FILTERS## Pre-Deployment Verification

        port: 3000

      initialDelaySeconds: 5        value: "example.com"  # optional

      periodSeconds: 10

    resources:### Step 2: Create Technitium Secret

# ExternalDNS configuration

sources:      requests:

  - service

  - ingress        cpu: 50m### 1. Code Quality ✅

registry: txt

policy: upsert-only        memory: 64Mi

interval: 1m

      limits:```bash```bash

# Resource limits for ExternalDNS container

resources:        cpu: 200m

  requests:

    cpu: 50m        memory: 128Mikubectl create namespace external-dns# Run tests

    memory: 64Mi

  limits:    securityContext:

    cpu: 200m

    memory: 128Mi      runAsNonRoot: truemake test



# Service account      allowPrivilegeEscalation: false

serviceAccount:

  create: true      readOnlyRootFilesystem: truekubectl create secret generic technitium-webhook \

  name: external-dns



# RBAC

rbac:sources:  --from-literal=api-token='your-technitium-api-token-here' \# Check linting

  create: true

  - service

# Log level

logLevel: info  - ingress  -n external-dnsmake lint

```

registry: txt

### Step 4: Deploy with Helm

policy: upsert-only```

```bash

helm upgrade --install external-dns external-dns/external-dns \interval: 1m

  --namespace external-dns \

  --create-namespace \```# Run security scans

  --values values-technitium.yaml

```



### Step 5: Verify DeploymentIf you operate multiple Technitium endpoints, add `TECHNITIUM_FAILOVER_URLS` with a semicolon-separated list.### Step 3: Create Helm Values Filemake security-check



```bash

# Check pods

kubectl get pods -n external-dns## Step 3 – Install or Upgrade ExternalDNS



# View logs```bash

kubectl logs -n external-dns deploy/external-dns -c webhook

helm repo add external-dns https://kubernetes-sigs.github.io/external-dns/Create `external-dns-values.yaml`:# Expected: All tests passing (30/30), no critical issues

# Test health endpoint

kubectl port-forward -n external-dns deploy/external-dns 3000:3000 &helm repo update

curl http://127.0.0.1:3000/health

# Expected: 200 OK```



# Stop port-forwardhelm upgrade --install external-dns external-dns/external-dns \

kill %1

```  --namespace external-dns \```yaml



## TLS Configuration (Private Certificate Authority)  --create-namespace \



If your Technitium DNS Server uses HTTPS with a private CA certificate, configure TLS verification:  --values values-technitium.yaml# External DNS configuration### 2. Docker Build ✅



### Step 1: Create ConfigMap with CA Certificate```



```bashprovider:```bash

# Option A: Create ConfigMap from CA certificate file

kubectl create configmap technitium-ca-bundle \Helm handles both fresh installs and upgrades; re-run the command whenever you update configuration or image versions.

  --from-file=ca.pem=/path/to/ca-certificate.pem \

  -n external-dns  name: webhook# Build multi-platform image



# Option B: Create from inline certificate## Step 4 – Validate the Deployment

kubectl create configmap technitium-ca-bundle \

  --from-literal=ca.pem="$(cat /path/to/ca-certificate.pem)" \```bashmake docker-build

  -n external-dns

```kubectl get pods -n external-dns



### Step 2: Update Helm Valueskubectl logs -n external-dns deploy/external-dns -c webhook --tail=20# Webhook provider configuration



Add to your `values-technitium.yaml`:kubectl logs -n external-dns deploy/external-dns -c external-dns --tail=20



```yamlextraArgs:# Or build for specific platform

provider:

  name: webhook# Forward the health endpoint if required

  webhook:

    image:kubectl port-forward -n external-dns deploy/external-dns 3000:3000 &  - --webhook-provider-url=http://localhost:8888docker build -t technitium-dns-webhook:latest .

      repository: ghcr.io/<YOUR_ORG>/external-dns-technitium-webhook

      tag: v1.0.0curl -s http://127.0.0.1:3000/health

    env:

      - name: TECHNITIUM_URL```

        value: "https://technitium-dns.technitium.svc.cluster.local:5380"

      - name: TECHNITIUM_VERIFY_SSL
        value: "true"  # Enable certificate verification

      - name: TECHNITIUM_CA_BUNDLE_FILE
        value: "/etc/technitium-ssl/ca.pem"  # Path in container

      # ... other env vars ...

    volumeMounts:

      - name: technitium-ca-bundle## Step 5 – Test Record Synchronisationsidecars:```

        mountPath: /etc/technitium-ssl

        readOnly: true```bash

    # ... rest of configuration ...

kubectl apply -f - <<'EOF'  - name: technitium-webhook

# Add volume to pod spec

volumes:apiVersion: v1

  - name: technitium-ca-bundle

    configMap:kind: Service    image: ghcr.io/yourusername/external-dns-technitium-webhook:latest### 3. Configuration Validation ✅

      name: technitium-ca-bundle

      items:metadata:

        - key: ca.pem

          path: ca.pem  name: webhook-smoke-test    imagePullPolicy: IfNotPresent```bash

```

  annotations:

### Step 3: Deploy

    external-dns.alpha.kubernetes.io/hostname: smoke.example.com    ports:# Test with actual Technitium credentials

```bash

helm upgrade --install external-dns external-dns/external-dns \spec:

  --namespace external-dns \

  --values values-technitium.yaml  selector: { app: kubernetes }      - containerPort: 8888export TECHNITIUM_API_URL="http://your-technitium-server:5380"

```

  ports:

### Step 4: Verify TLS Configuration

    - port: 80        name: httpexport TECHNITIUM_API_TOKEN="your-api-token-here"

```bash

# Check logs for successful connectionEOF

kubectl logs -n external-dns deploy/external-dns -c webhook | grep -i "tls\|ssl\|certificate"

        protocol: TCPexport DOMAIN_FILTER="example.com,test.example.com"

# Expected: No certificate verification errors

```sleep 60



For more TLS setup details, see `docs/CREDENTIALS_SETUP.md`.kubectl logs -n external-dns deploy/external-dns -c external-dns --tail=20    env:



## Advanced Configurationkubectl delete service webhook-smoke-test



### High Availability (Multiple Replicas)```      - name: TECHNITIUM_API_URL# Run locally



For HA deployments, ensure all ExternalDNS replicas share the same Technitium credentials:



```yamlVerify the record in Technitium (Service → Zones → `example.com`). Remove the test service once confirmed.        value: "http://technitium-dns.default.svc.cluster.local:5380"python -m uvicorn external_dns_technitium_webhook.main:app --host 0.0.0.0 --port 8888

# Update Helm values

replicas: 3



# All replicas will reference the same secret## Maintenance Tips      - name: TECHNITIUM_API_TOKEN

provider:

  webhook:- **Updates:** Bump the container tag in `values-technitium.yaml` and rerun the Helm upgrade.

    env:

      - name: TECHNITIUM_USERNAME- **Scaling:** Increase the ExternalDNS deployment replicas; the webhook sidecar scales with it.        valueFrom:# Test health endpoint

        valueFrom:

          secretKeyRef:- **Rotation:** After rotating credentials, re-apply the secret and restart the deployment (`kubectl rollout restart deployment/external-dns -n external-dns`).

            name: technitium-credentials  # Single shared secret

            key: username- **Monitoring:** Surfaced metrics include Kubernetes readiness probes and structured logs; consider forwarding logs to your existing platform.          secretKeyRef:curl http://localhost:8888/healthz

```



### Multiple Technitium Endpoints (Failover)            name: technitium-webhook# Expected: {"ready":true}



If you have multiple Technitium servers, use the failover configuration:            key: api-token```



```bash      - name: DOMAIN_FILTER

# Add failover URLs to secret

kubectl patch secret technitium-credentials \        value: "example.com"## Deployment Steps

  -n external-dns \

  -p '{"stringData":{"failover_urls":"http://backup1:5380;http://backup2:5380"}}'      - name: LOG_LEVEL

```

        value: "INFO"### Option 1: Docker Compose (Simplest)

Update Helm values:

      - name: LISTEN_PORT

```yaml

provider:        value: "8888"1. **Configure environment:**

  webhook:

    env:    resources:```bash

      - name: TECHNITIUM_FAILOVER_URLS

        valueFrom:      requests:# Edit docker-compose.yml with your values

          secretKeyRef:

            name: technitium-credentials        cpu: 50mTECHNITIUM_API_URL=http://technitium:5380

            key: failover_urls

```        memory: 64MiTECHNITIUM_API_TOKEN=your-token



### Custom Domain Filtering      limits:DOMAIN_FILTER=example.com



```yaml        cpu: 200m```

provider:

  webhook:        memory: 128Mi

    env:

      - name: DOMAIN_FILTERS    livenessProbe:2. **Deploy:**

        value: "example.com;staging.example.com;api.example.com"

```      httpGet:```bash



## Testing the Deployment        path: /healthzdocker-compose up -d



### Test 1: Health Check        port: 8888```



```bash      initialDelaySeconds: 10

kubectl run -it --rm debug \

  --image=curlimages/curl \      periodSeconds: 303. **Verify:**

  --restart=Never \

  -n external-dns \    readinessProbe:```bash

  -- curl http://external-dns-webhook.external-dns.svc.cluster.local:3000/health

      httpGet:curl http://localhost:8888/healthz

# Expected: 200 OK with JSON response

```        path: /healthz```



### Test 2: Create Test Service        port: 8888



```bash      initialDelaySeconds: 5### Option 2: Kubernetes Deployment (Production)

kubectl apply -f - <<'EOF'

apiVersion: v1      periodSeconds: 10

kind: Service

metadata:    securityContext:1. **Create namespace:**

  name: webhook-test-service

  namespace: external-dns      allowPrivilegeEscalation: false```bash

  annotations:

    external-dns.alpha.kubernetes.io/hostname: webhook-test.example.com      readOnlyRootFilesystem: truekubectl create namespace external-dns

spec:

  type: ClusterIP      runAsNonRoot: true```

  ports:

    - port: 80      runAsUser: 1000

      targetPort: 8080

  selector:      capabilities:2. **Create secret with API token:**

    app: webhook-test

        drop:```bash

---

apiVersion: apps/v1          - ALLkubectl create secret generic technitium-webhook-secret \

kind: Deployment

metadata:  --from-literal=api-token=your-token-here \

  name: webhook-test-app

  namespace: external-dns# Resource limits for ExternalDNS  -n external-dns

spec:

  replicas: 1resources:```

  selector:

    matchLabels:  requests:

      app: webhook-test

  template:    cpu: 50m3. **Create ConfigMap:**

    metadata:

      labels:    memory: 64Mi```yaml

        app: webhook-test

    spec:  limits:# technitium-webhook-config.yaml

      containers:

        - name: app    cpu: 200mapiVersion: v1

          image: nginx:latest

          ports:    memory: 128Mikind: ConfigMap

            - containerPort: 8080

EOFmetadata:



# Wait 30-60 seconds, then verify in Technitium DNS# Service account  name: technitium-webhook-config

# Expected: A record created for webhook-test.example.com

```serviceAccount:  namespace: external-dns



### Test 3: Verify DNS Record  create: truedata:



```bash  name: external-dns  TECHNITIUM_API_URL: "http://technitium-dns.default.svc.cluster.local:5380"

# Method 1: Check Technitium via curl (if accessible)

curl -X GET "http://technitium:5380/api/zones/example.com/records/webhook-test?type=A"  DOMAIN_FILTER: "example.com,*.example.com"



# Method 2: Check from within cluster# RBAC  LOG_LEVEL: "INFO"

kubectl run -it --rm dns-test \

  --image=busybox:latest \rbac:```

  --restart=Never \

  -- nslookup webhook-test.example.com <TECHNITIUM_IP>  create: true



# Expected: Resolved IP address```bash

```

# Sources to watchkubectl apply -f technitium-webhook-config.yaml

### Cleanup Test Resources

sources:```

```bash

kubectl delete svc webhook-test-service -n external-dns  - service

kubectl delete deployment webhook-test-app -n external-dns

```  - ingress4. **Deploy webhook:**



## Monitoring and Troubleshooting```yaml



### View Logs# Policy for record synchronization# technitium-webhook-deployment.yaml



```bashpolicy: syncapiVersion: apps/v1

# Webhook logs

kubectl logs -n external-dns deploy/external-dns -c webhook -fkind: Deployment



# ExternalDNS logs# Loggingmetadata:

kubectl logs -n external-dns deploy/external-dns -c external-dns -f

logLevel: info  name: technitium-webhook

# Combined search

kubectl logs -n external-dns deploy/external-dns --all-containers=true | grep -i error```  namespace: external-dns

```

spec:

### Check Pod Status

### Step 4: Deploy with Helm  replicas: 2  # High availability

```bash

# Get pod details  selector:

kubectl describe pod -n external-dns -l app.kubernetes.io/name=external-dns

```bash    matchLabels:

# Check readiness probe

kubectl get pod -n external-dns -l app.kubernetes.io/name=external-dns -o jsonpath='{.items[0].status.conditions[?(@.type=="Ready")]}'helm upgrade --install external-dns external-dns/external-dns \      app: technitium-webhook

```

  --namespace external-dns \  template:

### Common Issues

  --create-namespace \    metadata:

**Issue: Webhook not connecting to Technitium**

```  --values external-dns-values.yaml      labels:

Error: connection refused or timeout

``````        app: technitium-webhook

Solution: Verify network connectivity and DNS resolution:

```bash    spec:

kubectl run -it --rm debug --image=alpine:latest --restart=Never \

  -- sh -c "apk add curl && curl http://technitium-dns.technitium.svc.cluster.local:5380/api"### Step 5: Verify Deployment      securityContext:

```

        runAsNonRoot: true

**Issue: Authentication failure**

``````bash        runAsUser: 1000

Error: Invalid token or credentials

```# Check pods        fsGroup: 1000

Solution: Verify secret content:

```bashkubectl get pods -n external-dns      containers:

kubectl get secret technitium-credentials -n external-dns -o jsonpath='{.data.username}' | base64 -d

kubectl get secret technitium-credentials -n external-dns -o jsonpath='{.data.password}' | base64 -d      - name: webhook

```

# Check logs        image: ghcr.io/your-org/technitium-dns-webhook:latest

**Issue: Records not being created**

```kubectl logs -n external-dns -l app.kubernetes.io/name=external-dns -c technitium-webhook        imagePullPolicy: Always

Warning: Failed to create record

```        ports:

Solution: Check both webhook and ExternalDNS logs:

```bash# Test health endpoint        - containerPort: 8888

kubectl logs -n external-dns deploy/external-dns -c webhook --tail=50 | grep -i "record\|error"

kubectl logs -n external-dns deploy/external-dns -c external-dns --tail=50 | grep -i "webhook\|error"kubectl port-forward -n external-dns svc/external-dns 8888:8888          name: http

```

curl http://localhost:8888/healthz        env:

**Issue: TLS certificate verification failed**

``````        - name: TECHNITIUM_API_TOKEN

Error: certificate verify failed or CERTIFICATE_VERIFY_FAILED

```          valueFrom:

Solution: Verify CA bundle is correctly mounted:

```bash## Testing            secretKeyRef:

kubectl get configmap technitium-ca-bundle -n external-dns -o yaml

kubectl exec -n external-dns deploy/external-dns -c webhook -- ls -la /etc/technitium-ssl/              name: technitium-webhook-secret

```

Create a test service:              key: api-token

## Maintenance and Updates

        envFrom:

### Update Configuration

```yaml        - configMapRef:

Edit Helm values and upgrade:

apiVersion: v1            name: technitium-webhook-config

```bash

# Edit values filekind: Service        livenessProbe:

vim values-technitium.yaml

metadata:          httpGet:

# Apply changes

helm upgrade external-dns external-dns/external-dns \  name: test-service            path: /healthz

  --namespace external-dns \

  --values values-technitium.yaml  annotations:            port: 8888

```

    external-dns.alpha.kubernetes.io/hostname: test.example.com          initialDelaySeconds: 10

### Update Container Image

spec:          periodSeconds: 30

```bash

# Update tag in values-technitium.yaml, then:  type: LoadBalancer        readinessProbe:

helm upgrade external-dns external-dns/external-dns \

  --namespace external-dns \  ports:          httpGet:

  --values values-technitium.yaml

```  - port: 80            path: /healthz



### Rotate Credentials  selector:            port: 8888



```bash    app: test          initialDelaySeconds: 5

# Create new secret

kubectl create secret generic technitium-credentials-v2 \```          periodSeconds: 10

  --from-literal=username='new-user' \

  --from-literal=password='new-password' \        resources:

  -n external-dns

Verify DNS record in Technitium after 30-60 seconds.          requests:

# Update Helm values to reference new secret

# Redeploy            memory: "64Mi"

helm upgrade external-dns external-dns/external-dns \

  --namespace external-dns \## Resource Recommendations            cpu: "100m"

  --values values-technitium.yaml

          limits:

# Delete old secret once verified

kubectl delete secret technitium-credentials -n external-dns**Minimum:**            memory: "256Mi"

```

```yaml            cpu: "500m"

### Rollback Deployment

requests: {cpu: 50m, memory: 64Mi}        securityContext:

```bash

# View rollback historylimits: {cpu: 100m, memory: 128Mi}          allowPrivilegeEscalation: false

helm history external-dns -n external-dns

```          readOnlyRootFilesystem: true

# Rollback to previous version

helm rollback external-dns 1 -n external-dns          capabilities:

```

**Production:**            drop:

## Production Hardening Checklist

```yaml            - ALL

- [ ] Use HTTPS for Technitium API communication

- [ ] Store secrets in a secret management system (Vault, Sealed Secrets)requests: {cpu: 100m, memory: 64Mi}---

- [ ] Implement network policies to restrict pod communication

- [ ] Enable pod security policieslimits: {cpu: 200m, memory: 128Mi}apiVersion: v1

- [ ] Run with read-only root filesystem

- [ ] Drop all Linux capabilities```kind: Service

- [ ] Use non-root user (UID 1000)

- [ ] Configure resource limits appropriatelymetadata:

- [ ] Enable pod disruption budgets for HA

- [ ] Implement monitoring and alerting## Support  name: technitium-webhook

- [ ] Regular security scanning and dependency updates

- [ ] Audit logging enabled in Technitium DNS  namespace: external-dns



## Resource RecommendationsSee [main documentation](../../README.md) for more details.spec:



### Minimal Configuration  selector:

```yaml    app: technitium-webhook

resources:  ports:

  requests:  - protocol: TCP

    cpu: 50m    port: 80

    memory: 64Mi    targetPort: 8888

  limits:  type: ClusterIP

    cpu: 100m```

    memory: 128Mi

``````bash

kubectl apply -f technitium-webhook-deployment.yaml

### Standard Production```

```yaml

resources:5. **Configure ExternalDNS to use webhook:**

  requests:```yaml

    cpu: 100m# external-dns-config.yaml (add to ExternalDNS deployment)

    memory: 128Miargs:

  limits:- --source=service

    cpu: 250m- --source=ingress

    memory: 256Mi- --provider=webhook

```- --webhook-provider-url=http://technitium-webhook.external-dns.svc.cluster.local

```

### High Performance

```yaml6. **Verify deployment:**

resources:```bash

  requests:# Check pods

    cpu: 200mkubectl get pods -n external-dns

    memory: 256Mi

  limits:# Check logs

    cpu: 500mkubectl logs -n external-dns -l app=technitium-webhook

    memory: 512Mi

```# Test webhook endpoint

kubectl run -it --rm debug --image=curlimages/curl --restart=Never -- \

## Next Steps  curl http://technitium-webhook.external-dns.svc.cluster.local/healthz

```

After successful deployment:

### Option 3: Standalone Service (Development)

1. Monitor webhook logs for 24-48 hours

2. Test DNS record creation and deletion1. **Install dependencies:**

3. Set up Prometheus monitoring (see `docs/DEVELOPMENT.md`)```bash

4. Configure alerting rulespython -m venv .venv

5. Document environment-specific configurationssource .venv/bin/activate  # or `.venv\Scripts\activate` on Windows

6. Plan regular maintenance and update schedulepip install -e ".[dev]"

```

## Additional Resources

2. **Configure environment:**

- [ExternalDNS Documentation](https://external-dns.readthedocs.io/)```bash

- [Helm Documentation](https://helm.sh/docs/)export TECHNITIUM_API_URL="http://localhost:5380"

- [Kubernetes RBAC](https://kubernetes.io/docs/reference/access-authn-authz/rbac/)export TECHNITIUM_API_TOKEN="your-token"

- [Project README](../../README.md)export DOMAIN_FILTER="example.com"

- [Credentials Setup Guide](../CREDENTIALS_SETUP.md)```

- [API Documentation](../API.md)

3. **Run server:**

## Support```bash

python -m uvicorn external_dns_technitium_webhook.main:app \

For issues or questions:  --host 0.0.0.0 \

  --port 8888 \

1. Check logs as described in "Monitoring and Troubleshooting"  --reload  # For development

2. Review `docs/CREDENTIALS_SETUP.md` for credential configuration```

3. See `docs/DEVELOPMENT.md` for debugging steps

4. Open a GitHub issue with:## Post-Deployment Verification

   - Kubernetes version

   - Helm values (sanitized)### 1. Health Checks ✅

   - Relevant logs```bash

   - Steps to reproduce# Basic health

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
