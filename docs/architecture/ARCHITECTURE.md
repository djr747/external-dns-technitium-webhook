# Project Architecture

This document provides a visual overview of the external-dns-technitium-webhook architecture and component interactions.

## System Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         Kubernetes Cluster                              │
│                                                                         │
│  ┌──────────────────┐         ┌──────────────────┐                     │
│  │   Ingress        │         │   Service        │                     │
│  │   Resources      │         │   Resources      │                     │
│  │                  │         │                  │                     │
│  │  annotations:    │         │  annotations:    │                     │
│  │   external-dns   │         │   external-dns   │                     │
│  └────────┬─────────┘         └────────┬─────────┘                     │
│           │                            │                               │
│           │         ┌──────────────────┘                               │
│           │         │                                                  │
│           ▼         ▼                                                  │
│  ┌──────────────────────────────────┐                                  │
│  │       ExternalDNS                │                                  │
│  │                                  │                                  │
│  │  - Watches K8s resources         │                                  │
│  │  - Detects DNS changes           │                                  │
│  │  - Calls webhook provider        │                                  │
│  └──────────────────┬───────────────┘                                  │
│                     │                                                  │
└─────────────────────┼──────────────────────────────────────────────────┘
                      │
                      │ HTTP/HTTPS
                      │
                      ▼
┌─────────────────────────────────────────────────────────────────────────┐
│              Technitium Webhook (This Project)                          │
│                                                                         │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │                      FastAPI Application                         │  │
│  │                                                                  │  │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌───────────┐ │  │
│  │  │  Health    │  │  Negotiate │  │   Records  │  │   Apply   │ │  │
│  │  │  Endpoint  │  │  Endpoint  │  │  Endpoint  │  │  Endpoint │ │  │
│  │  │            │  │            │  │            │  │           │ │  │
│  │  │    /       │  │    /       │  │    /       │  │    /      │ │  │
│  │  │ /healthz   │  │  negotiate │  │  records   │  │ adjustend │ │  │
│  │  │            │  │            │  │            │  │  points   │ │  │
│  │  └────────────┘  └────────────┘  └────────────┘  └───────────┘ │  │
│  │                                                                  │  │
│  │  ┌──────────────────────────────────────────────────────────┐   │  │
│  │  │               Request Handlers                           │   │  │
│  │  │  - Domain filtering                                      │   │  │
│  │  │  - Record type validation                                │   │  │
│  │  │  - Endpoint adjustment                                   │   │  │
│  │  │  - Change detection (create/delete)                      │   │  │
│  │  └──────────────────────┬───────────────────────────────────┘   │  │
│  │                         │                                        │  │
│  │                         ▼                                        │  │
│  │  ┌──────────────────────────────────────────────────────────┐   │  │
│  │  │               Technitium Client                          │   │  │
│  │  │  - API authentication (auto token renewal)               │   │  │
│  │  │  - Zone management (auto-create)                         │   │  │
│  │  │  - Record CRUD operations                                │   │  │
│  │  │  - Enhanced error handling                               │   │  │
│  │  │  - Advanced options support                              │   │  │
│  │  └──────────────────────┬───────────────────────────────────┘   │  │
│  │                         │                                        │  │
│  │  ┌──────────────────────────────────────────────────────────┐   │  │
│  │  │               Pydantic Models                            │   │  │
│  │  │  - Endpoint (ExternalDNS format)                         │   │  │
│  │  │  - Changes (create/delete)                               │   │  │
│  │  │  - DomainFilter (include/exclude/regex)                  │   │  │
│  │  │  - Record data (10 types)                                │   │  │
│  │  │    • A, AAAA, CNAME, TXT                                 │   │  │
│  │  │    • ANAME, CAA, URI, SSHFP, SVCB, HTTPS                 │   │  │
│  │  └──────────────────────────────────────────────────────────┘   │  │
│  └──────────────────────────────────────────────────────────────────┘  │
└─────────────────────────┬───────────────────────────────────────────────┘
                          │
                          │ HTTP REST API
                          │
                          ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    Technitium DNS Server                                │
│                                                                         │
│  ┌──────────────────┐   ┌──────────────────┐   ┌──────────────────┐   │
│  │  Zone Management │   │ Record Management│   │  Authentication  │   │
│  │                  │   │                  │   │                  │   │
│  │  - Auto-create   │   │  - 10 types      │   │  - Token auth    │   │
│  │  - Zone transfer │   │  - Comments      │   │  - Auto-renewal  │   │
│  │  - PTR zones     │   │  - Expiry TTL    │   │  - Secure        │   │
│  └──────────────────┘   └──────────────────┘   └──────────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

## Component Breakdown

### 1. ExternalDNS (External Component)
**Purpose:** Kubernetes controller that synchronizes DNS records with DNS providers

**Responsibilities:**
- Watch Kubernetes resources (Services, Ingresses)
- Detect DNS annotation changes
- Call webhook provider endpoints
- Reconcile DNS state

**Configuration:**
```yaml
args:
  - --source=service
  - --source=ingress
  - --provider=webhook
  - --webhook-provider-url=http://technitium-webhook
```

### 2. Technitium Webhook (This Project)
**Purpose:** Translate ExternalDNS webhook calls to Technitium DNS API calls

**Components:**

#### 2.1 FastAPI Application (`main.py`)
- HTTP server on port 8888
- 4 webhook endpoints
- Health check endpoints
- CORS support
- Async request handling

#### 2.2 Request Handlers (`handlers.py`)
**Functions:**
- `health_check()` - Health and readiness checks
- `negotiate()` - Domain filter negotiation
- `get_records()` - Retrieve DNS records
- `adjust_endpoints()` - Apply DNS changes

**Features:**
- Domain filtering (include/exclude/regex)
- Record type conversion (10 types)
- Change detection (create/delete/update)
- Error propagation

#### 2.3 Technitium Client (`technitium_client.py`)
**API Operations:**
- `login()` - Authenticate and get token
- `create_zone()` - Auto-create zones
- `get_records()` - Fetch zone records
- `add_record()` - Create DNS records (with 8 advanced options)
- `delete_record()` - Remove DNS records

**Enhanced Features:**
- Automatic token renewal
- Structured error handling (TechnitiumError)
- Stack trace capture
- Advanced options support

#### 2.4 Data Models (`models.py`)
**Pydantic Models:**

**ExternalDNS Format:**
- `Endpoint` - DNS record in ExternalDNS format
- `Changes` - Create/delete change sets
- `DomainFilter` - Domain filtering rules

**Technitium Format:**
- `RecordAData` - A record (IPv4)
- `RecordAAAAData` - AAAA record (IPv6)
- `RecordCNAMEData` - CNAME record
- `RecordTXTData` - TXT record
- `RecordANAMEData` - ANAME record (Technitium proprietary)
- `RecordCAAData` - CAA record (Let's Encrypt)
- `RecordURIData` - URI record
- `RecordSSHFPData` - SSHFP record
- `RecordSVCBData` - SVCB/HTTPS record

#### 2.5 Configuration (`config.py`)
**Environment Variables:**
- `TECHNITIUM_API_URL` - DNS server URL
- `TECHNITIUM_API_TOKEN` - Authentication token
- `DOMAIN_FILTER` - Domain filtering
- `LISTEN_ADDRESS` - Bind address
- `LISTEN_PORT` - HTTP port
- `LOG_LEVEL` - Logging verbosity

#### 2.6 Application State (`app_state.py`)
**Shared State:**
- Technitium client instance
- Configuration singleton
- Ready state flag

### 3. Technitium DNS Server (External Component)
**Purpose:** Authoritative DNS server with REST API

**API Endpoints Used:**
- `POST /api/user/login` - Authentication
- `POST /api/zones/create` - Zone creation
- `GET /api/zones/records/get` - Record retrieval
- `GET /api/zones/records/add` - Record creation
- `GET /api/zones/records/delete` - Record deletion

## Data Flow

### Record Creation Flow

```
1. User creates Kubernetes Service/Ingress
   │
   ├─ Service: my-app.example.com
   └─ Annotation: external-dns.alpha.kubernetes.io/hostname=my-app.example.com
   
2. ExternalDNS detects change
   │
   ├─ Calls: POST /adjustendpoints
   └─ Body: {"changes": {"create": [...]}}

3. Technitium Webhook processes request
   │
   ├─ handlers.py: adjust_endpoints()
   │   ├─ Parse changes
   │   ├─ Filter domains
   │   └─ Convert to Technitium format
   │
   ├─ technitium_client.py: add_record()
   │   ├─ Check zone exists (create if needed)
   │   ├─ Prepare API request
   │   └─ Call Technitium API
   │
   └─ models.py: RecordAData/RecordAAAAData
       └─ Validate data

4. Technitium DNS creates record
   │
   └─ Record: my-app.example.com -> 10.0.0.1

5. DNS query resolves
   │
   └─ dig my-app.example.com -> 10.0.0.1
```

### Error Handling Flow

```
1. API Error occurs in Technitium
   │
   ├─ Error: "Invalid zone name"
   ├─ Stack trace: "at ZoneManager.CreateZone()..."
   └─ Inner error: "Zone already exists"

2. Technitium Client captures error
   │
   ├─ TechnitiumError created
   │   ├─ error_message: "Invalid zone name"
   │   ├─ stack_trace: "at ZoneManager..."
   │   └─ inner_error: "Zone already exists"
   │
   └─ Logged with full context

3. Handler propagates error
   │
   ├─ HTTP 500 response
   └─ Error details in logs

4. ExternalDNS retries
   │
   └─ Exponential backoff
```

## Deployment Architecture

### Docker Container

```
┌──────────────────────────────────────────────────┐
│           Container: technitium-webhook           │
│                                                   │
│  User: appuser (UID 1000)                        │
│  Workdir: /app                                   │
│                                                   │
│  ┌────────────────────────────────────────────┐  │
│  │  Python 3.11 Runtime                       │  │
│  │                                            │  │
│  │  - FastAPI application                     │  │
│  │  - Uvicorn ASGI server                     │  │
│  │  - Python dependencies                     │  │
│  │  - Health check script                     │  │
│  └────────────────────────────────────────────┘  │
│                                                   │
│  Ports:                                          │
│  - 8888/tcp (HTTP)                               │
│                                                   │
│  Volumes:                                        │
│  - None (stateless)                              │
│                                                   │
│  Environment:                                    │
│  - TECHNITIUM_API_URL                            │
│  - TECHNITIUM_API_TOKEN                          │
│  - DOMAIN_FILTER                                 │
│  - LOG_LEVEL                                     │
└──────────────────────────────────────────────────┘
```

### Kubernetes Deployment

```
┌────────────────────────────────────────────────────────────┐
│                    Namespace: external-dns                 │
│                                                            │
│  ┌──────────────────────────────────────────────────────┐ │
│  │          Deployment: technitium-webhook               │ │
│  │                                                       │ │
│  │  Replicas: 2 (High Availability)                     │ │
│  │                                                       │ │
│  │  ┌─────────────────┐    ┌─────────────────┐          │ │
│  │  │   Pod 1         │    │   Pod 2         │          │ │
│  │  │                 │    │                 │          │ │
│  │  │  Container:     │    │  Container:     │          │ │
│  │  │   webhook       │    │   webhook       │          │ │
│  │  │                 │    │                 │          │ │
│  │  │  Resources:     │    │  Resources:     │          │ │
│  │  │   CPU: 100m-500m│    │   CPU: 100m-500m│          │ │
│  │  │   Mem: 64Mi-256Mi    │   Mem: 64Mi-256Mi          │ │
│  │  │                 │    │                 │          │ │
│  │  │  Probes:        │    │  Probes:        │          │ │
│  │  │   Liveness ✓    │    │   Liveness ✓    │          │ │
│  │  │   Readiness ✓   │    │   Readiness ✓   │          │ │
│  │  └─────────────────┘    └─────────────────┘          │ │
│  │                                                       │ │
│  │  ConfigMap: technitium-webhook-config                │ │
│  │  Secret: technitium-webhook-secret                   │ │
│  └──────────────────────────────────────────────────────┘ │
│                                                            │
│  ┌──────────────────────────────────────────────────────┐ │
│  │            Service: technitium-webhook                │ │
│  │                                                       │ │
│  │  Type: ClusterIP                                     │ │
│  │  Port: 80 → 8888                                     │ │
│  │  Selector: app=technitium-webhook                    │ │
│  └──────────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────────┘
```

## CI/CD Pipeline

```
┌──────────────────────────────────────────────────────────────┐
│                    GitHub Repository                         │
└──────────────────┬───────────────────────────────────────────┘
                   │
                   │ Push/PR
                   │
                   ▼
┌──────────────────────────────────────────────────────────────┐
│                  GitHub Actions Workflows                     │
│                                                               │
│  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐ │
│  │   ci.yml       │  │  security.yml  │  │   docker.yml   │ │
│  │                │  │                │  │                │ │
│  │ - Lint (ruff)  │  │ - Trivy scan   │  │ - Build image  │ │
│  │ - Type (mypy)  │  │ - Bandit scan  │  │ - Multi-arch   │ │
│  │ - Test (pytest)│  │ - Push GHCR    │ │
│  │ - Coverage     │  │ - CodeQL       │  │ - Cache layers │ │
│  └────────────────┘  └────────────────┘  └────────────────┘ │
│                                                               │
│  ┌────────────────┐                                          │
│  │  release.yml   │                                          │
│  │                │                                          │
│  │ - Semantic ver │                                          │
│  │ - Changelog    │                                          │
│  │ - GitHub rel   │                                          │
│  │ - Tag Docker   │                                          │
│  └────────────────┘                                          │
└──────────────────────────────────────────────────────────────┘
```

## Testing Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                      Test Suite (pytest)                      │
│                                                               │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  Unit Tests (30 total)                                 │  │
│  │                                                        │  │
│  │  test_config.py (5)                                    │  │
│  │  ├─ Configuration validation                           │  │
│  │  ├─ Environment variable handling                      │  │
│  │  └─ Domain filter parsing                              │  │
│  │                                                        │  │
│  │  test_models.py (5)                                    │  │
│  │  ├─ Pydantic model validation                          │  │
│  │  ├─ Serialization/deserialization                      │  │
│  │  └─ Field aliasing                                     │  │
│  │                                                        │  │
│  │  test_handlers.py (9)                                  │  │
│  │  ├─ Health checks                                      │  │
│  │  ├─ Domain filter negotiation                          │  │
│  │  ├─ Record retrieval                                   │  │
│  │  ├─ Endpoint adjustment                                │  │
│  │  └─ Change application                                 │  │
│  │                                                        │  │
│  │  test_technitium_client.py (5)                         │  │
│  │  ├─ Authentication                                      │  │
│  │  ├─ Zone creation                                      │  │
│  │  ├─ Record operations                                  │  │
│  │  └─ Error handling                                     │  │
│  │                                                        │  │
│  │  test_enhancements.py (7)                              │  │
│  │  ├─ Enhanced error handling                            │  │
│  │  ├─ ANAME records                                      │  │
│  │  ├─ CAA records                                        │  │
│  │  ├─ Advanced options                                   │  │
│  │  ├─ URI records                                        │  │
│  │  └─ SVCB/HTTPS records                                 │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                               │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  Test Infrastructure                                   │  │
│  │                                                        │  │
│  │  - pytest-asyncio (async testing)                     │  │
│  │  - pytest-mock (mocking)                              │  │
│  │  - pytest-cov (coverage reporting)                    │  │
│  │  - Fixtures (conftest.py)                             │  │
│  └────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

## Security Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                    Security Layers                            │
│                                                               │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  1. Container Security                                 │  │
│  │                                                        │  │
│  │  - Non-root user (UID 1000)                           │  │
│  │  - Read-only filesystem                               │  │
│  │  - Dropped capabilities                               │  │
│  │  - No privilege escalation                            │  │
│  │  - Minimal base image (python:slim)                   │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                               │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  2. Code Security                                      │  │
│  │                                                        │  │
│  │  - Bandit (Python security linting)                   │  │
│  │  - CodeQL (static analysis)                           │  │
│  │  - Ruff (modern linting rules)                        │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                               │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  3. Dependency Security                                │  │
│  │                                                        │  │
│  │  - Trivy (container scanning)                         │  │
│  │  - Pinned versions                                    │  │
│  │  - Regular updates                                    │  │
│  │  - Automated security alerts                          │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                               │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  4. Runtime Security                                   │  │
│  │                                                        │  │
│  │  - No hardcoded secrets                               │  │
│  │  - Environment variable config                        │  │
│  │  - Kubernetes secrets integration                     │  │
│  │  - TLS support for API calls                          │  │
│  └────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

## Scalability Considerations

### Horizontal Scaling
- ✅ **Stateless:** No shared state between instances
- ✅ **Load Balanced:** Service distributes traffic
- ✅ **Auto-scaling:** HPA ready (CPU/memory based)
- ✅ **Session-free:** Each request independent

### Performance Optimization
- ✅ **Async I/O:** Non-blocking operations
- ✅ **Connection pooling:** Reuse HTTP connections
- ✅ **Caching potential:** Future enhancement for record caching
- ✅ **Fast startup:** < 1 second initialization

### Resource Efficiency
- ✅ **Low memory:** ~50MB base footprint
- ✅ **Low CPU:** < 100m under normal load
- ✅ **Small image:** ~200MB container size
- ✅ **Fast builds:** Multi-stage Docker optimization

## Monitoring and Observability

### Current Implementation
```
┌────────────────────────────────────┐
│     Application Logging            │
│                                    │
│  - Structured logs (JSON ready)   │
│  - Log levels (DEBUG-CRITICAL)     │
│  - Request/response logging        │
│  - Error stack traces              │
└────────────────────────────────────┘
```

### Health Checks
```
GET /        → {"ready": true}
GET /healthz → {"ready": true}
```

### Future Enhancements
```
┌────────────────────────────────────┐
│    Prometheus Metrics (Future)     │
│                                    │
│  - Request count                  │
│  - Request duration               │
│  - Error rate                     │
│  - Technitium API latency         │
│  - Record operations              │
└────────────────────────────────────┘

┌────────────────────────────────────┐
│  OpenTelemetry Tracing (Future)    │
│                                    │
│  - Request tracing                │
│  - Span creation                  │
│  - Distributed tracing            │
│  - Performance analysis           │
└────────────────────────────────────┘
```

## Summary

This architecture provides:

1. ✅ **Separation of Concerns** - Clear component boundaries
2. ✅ **Scalability** - Horizontal scaling ready
3. ✅ **Security** - Multiple security layers
4. ✅ **Testability** - Comprehensive test suite
5. ✅ **Observability** - Logging and health checks
6. ✅ **Maintainability** - Clean code structure
7. ✅ **Extensibility** - Easy to add new record types
8. ✅ **Production Ready** - All best practices followed

For detailed implementation guides, see:
- [Complete Summary](COMPLETE_SUMMARY.md)
- [Deployment Checklist](DEPLOYMENT_CHECKLIST.md)
- [Development Guide](docs/DEVELOPMENT.md)
