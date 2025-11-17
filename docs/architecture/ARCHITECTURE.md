# Project Architecture

This document provides a visual overview of the external-dns-technitium-webhook architecture and component interactions.

## System Architecture

```mermaid
graph TB
    subgraph K8s["Kubernetes Cluster"]
        Ingress["Ingress Resources<br/>(annotations: external-dns)"]
        Service["Service Resources<br/>(annotations: external-dns)"]
        ExternalDNS["ExternalDNS<br/>- Watches K8s resources<br/>- Detects DNS changes<br/>- Calls webhook provider"]
        
        Ingress --> ExternalDNS
        Service --> ExternalDNS
    end
    
    ExternalDNS -->|HTTP 8888| API["Main API Server (port 8888)<br/>main.py"]
    
    subgraph Webhook["Technitium Webhook (This Project)"]
        API --> Handlers["Request Handlers<br/>handlers.py"]
        Handlers -->|GET /| DomainFilter["Domain Filter Negotiation"]
        Handlers -->|GET /records| GetRecords["DNS Records Query"]
        Handlers -->|POST /records| ApplyRecords["Apply DNS Changes<br/>create/delete"]
        Handlers -->|POST /adjustendpoints| AdjustEP["Endpoint Adjustment"]
        
        Handlers --> Client["Technitium Client<br/>technitium_client.py<br/>- Authentication<br/>- Zone management<br/>- Record CRUD"]
        Client --> Models["Pydantic Models<br/>models.py<br/>10 DNS types: A, AAAA, CNAME, TXT,<br/>ANAME, CAA, URI, SSHFP, SVCB, HTTPS"]
    end
    
    Health["Health Server (port 8080)<br/>server.py + health.py<br/>Separate thread"]
    API -.-> Health
    
    Client -->|HTTP REST API| DNS["Technitium DNS Server<br/>5380 HTTP / 53443 HTTPS"]
    
    DNS --> ZoneMgmt["Zone Management<br/>- Auto-create zones<br/>- Zone transfer support"]
    DNS --> RecordMgmt["Record Management<br/>- 10 DNS record types<br/>- Comments & Expiry TTL<br/>- PTR record creation"]
    DNS --> Auth["Authentication<br/>- Token auth<br/>- Auto-renewal"]
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

```mermaid
graph TD
    A["1. User creates Kubernetes<br/>Service/Ingress<br/>with external-dns annotation"] --> B["2. ExternalDNS detects change<br/>via annotation webhook"]
    B --> C["3. ExternalDNS calls webhook<br/>POST /adjustendpoints"]
    C --> D["Technitium Webhook<br/>handlers.py"]
    D --> E["Parse & validate changes<br/>Domain filtering<br/>Record type conversion"]
    E --> F["technitium_client.py<br/>add_record function"]
    F --> G["Check if zone exists<br/>Create zone if needed"]
    G --> H["Prepare Technitium API request<br/>Convert to Technitium format"]
    H --> I["Call Technitium DNS API<br/>POST /api/zones/records/add"]
    I --> J["Technitium creates DNS record"]
    J --> K["DNS query resolves<br/>dig my-app.example.com"]
    K --> L["Returns IP address"]
```

### Error Handling Flow

```mermaid
graph TD
    A["Technitium API Error<br/>occurs"] --> B["Error from Technitium<br/>e.g., Invalid zone name"]
    B --> C["Stack trace captured<br/>at ZoneManager.CreateZone"]
    C --> D["Inner error details<br/>Zone already exists"]
    D --> E["TechnitiumError exception<br/>created with full context"]
    E --> F["Logged to stderr<br/>with level ERROR"]
    F --> G["Handler catches exception"]
    G --> H["HTTP 500 response<br/>sent to ExternalDNS"]
    H --> I["Error details in logs<br/>for debugging"]
    I --> J["ExternalDNS receives 500"]
    J --> K["Exponential backoff retry<br/>with jitter"]
    K --> L["Next attempt after delay"]
```

## Deployment Architecture

### Docker Container

### Docker Container

```mermaid
graph TB
    subgraph Container["Container: technitium-webhook<br/>Chainguard Python latest"]
        NonRoot["Non-root user<br/>UID 65532"]
        Work["Workdir: /app"]
        
        subgraph Runtime["Python 3.13 Runtime"]
            FastAPI["FastAPI application"]
            Uvicorn["Uvicorn ASGI server"]
            Deps["Python dependencies"]
            Health["Health check server"]
        end
        
        FastAPI --> Uvicorn
        Deps --> FastAPI
        Health -.-> FastAPI
    end
    
    Container --> Port1["Port 8888/tcp<br/>Main API"]
    Container --> Port2["Port 8080/tcp<br/>Health checks"]
    Container --> Env["Environment Variables<br/>TECHNITIUM_URL<br/>TECHNITIUM_USERNAME<br/>TECHNITIUM_PASSWORD"]
    Container --> Vol["Volumes: None<br/>Stateless"]
```

### Kubernetes Deployment

```mermaid
graph TB
    subgraph K8sNamespace["Namespace: external-dns"]
        subgraph Deploy["Deployment: technitium-webhook<br/>Replicas: 1 (Single instance)"]
            Pod["Pod<br/>Container: webhook<br/>CPU: 100m-500m<br/>Mem: 128Mi-512Mi"]
            Pod --> Probes["Liveness Probe ✓<br/>Readiness Probe ✓"]
        end
        
        Config["ConfigMap<br/>technitium-webhook-config"]
        Secret["Secret<br/>technitium-webhook-secret"]
        
        Config --> Deploy
        Secret --> Deploy
        
        Service["Service: technitium-webhook<br/>Type: ClusterIP<br/>Port: 80 → 8888"]
        Deploy --> Service
        
        Note["⚠️ Single replica<br/>ExternalDNS doesn't support HA"]
    end
```

## CI/CD Pipeline

```mermaid
graph LR
    Repo["GitHub<br/>Repository"] --> Push["Push/PR"]
    Push --> Actions["GitHub Actions"]
    
    Actions --> CI["ci.yml<br/>- Lint ruff<br/>- Type check mypy<br/>- Test pytest<br/>- Coverage ≥95%"]
    Actions --> Security["security.yml<br/>- Trivy scan<br/>- Semgrep analysis<br/>- CodeQL<br/>- Grype"]
    Actions --> Docker["docker.yml<br/>- Build image<br/>- Multi-arch AMD64/ARM64<br/>- Push to GHCR"]
    
    CI --> Test{Tests<br/>Pass?}
    Security --> Test
    Docker --> Test
    
    Test -->|Yes| Release["release.yml<br/>- Semantic versioning<br/>- Changelog update<br/>- GitHub release<br/>- Tag Docker image"]
    Test -->|No| Fail["❌ Workflow Fails<br/>Block merge"]
    
    Release --> Deploy["✅ Ready for Deploy"]
```

## Testing Architecture

```mermaid
graph TB
    subgraph TestSuite["Test Suite - pytest + pytest-asyncio"]
        subgraph UnitTests["Unit Tests: 176 total"]
            Config["test_config.py<br/>- Env var validation<br/>- Domain filter parsing<br/>- Config initialization"]
            Models["test_models.py<br/>- Pydantic validation<br/>- Serialization/deserialization<br/>- Field aliasing"]
            Handlers["test_handlers.py<br/>- Health checks<br/>- Domain negotiation<br/>- Record retrieval<br/>- Changes application"]
            Client["test_technitium_client.py<br/>- Authentication<br/>- Zone creation<br/>- Record CRUD<br/>- Error handling"]
            Enhanced["test_enhancements.py<br/>- Advanced error handling<br/>- Special record types<br/>- Provider properties"]
        end
        
        Config --> Coverage["Coverage Report<br/>99% (933/941 lines)"]
        Models --> Coverage
        Handlers --> Coverage
        Client --> Coverage
        Enhanced --> Coverage
        
        Coverage --> Gate{Coverage<br/>≥95%?}
    end
    
    Infrastructure["Test Infrastructure<br/>- pytest-asyncio<br/>- pytest-mock<br/>- pytest-cov<br/>- conftest.py fixtures"]
    Infrastructure --> TestSuite
    
    Gate -->|Pass| Success["✅ Tests Pass<br/>Ready for merge"]
    Gate -->|Fail| Failure["❌ Coverage too low<br/>Block merge"]
```

## Security Architecture

```mermaid
graph TB
    subgraph SecurityLayers["Security Layers"]
        subgraph Container["1. Container Security"]
            NonRoot["Non-root user<br/>UID 65532<br/>Chainguard default"]
            ReadOnly["Read-only filesystem<br/>recommended"]
            Minimal["Chainguard base image<br/>Python 3.13<br/>Zero CVEs"]
            SLSA["SLSA Level 3<br/>Reproducible builds"]
        end
        
        subgraph CodeSec["2. Code Security"]
            Semgrep["Semgrep<br/>Pattern-based detection"]
            CodeQL["CodeQL<br/>Semantic analysis"]
            Ruff["Ruff<br/>Modern linting"]
        end
        
        subgraph DepSec["3. Dependency Security"]
            Trivy["Trivy<br/>Container scanning"]
            Grype["Grype<br/>CVE scanning"]
            PipAudit["pip-audit<br/>Package audit"]
            Snyk["Snyk<br/>Vulnerability DB"]
        end
        
        subgraph Runtime["4. Runtime Security"]
            Secrets["No hardcoded secrets<br/>Env vars only"]
            K8sSecrets["Kubernetes Secrets<br/>for credentials"]
            TLS["TLS support<br/>for API calls"]
            NoLog["No logging of passwords<br/>or tokens"]
        end
    end
```

## Scalability Considerations

### Deployment Model
- ⚠️ **Single Instance Only:** ExternalDNS controller doesn't support HA deployments
- ✅ **Stateless Design:** Webhook is stateless and could theoretically scale if ExternalDNS supported it
- ✅ **Health Checks:** Liveness and readiness probes for pod restart on failure

### Performance Optimization
- ✅ **Async I/O:** Non-blocking operations
- ✅ **Connection pooling:** Reuse HTTP connections to Technitium
- ✅ **Graceful shutdown:** Drains in-flight requests on pod termination
- ✅ **Fast startup:** < 1 second initialization

### Resource Efficiency
- ✅ **Low memory:** ~64Mi base footprint
- ✅ **Low CPU:** 100m-500m per pod
- ✅ **Small image:** ~200MB container image
- ✅ **Multi-arch:** AMD64 and ARM64 support

## Monitoring and Observability

### Current Implementation
```
┌────────────────────────────────────────────────────┐
│     Application Logging                            │
│                                                    │
│  - Structured logs (External-DNS format)          │
│    time="..." level=... module=... msg="..."      │
│  - Log levels (DEBUG through ERROR)                │
│  - Request/response logging                        │
│  - Error stack traces                              │
└────────────────────────────────────────────────────┘
```

### Health Checks

**Main API Server (port 8888):**
- `GET /` → Negotiates domain filters (returns ExternalDNS webhook response)
- `GET /records` → Fetches current DNS records
- HTTP 200 OK if app is ready, HTTP 503 if not ready or Technitium unreachable

**Health Check Server (port 8080):**
- `GET /health` → Returns `{"status": "ok"}` on 200, or 503 with error on failure
- `GET /healthz` → Kubernetes-style readiness probe, returns `{"status": "ok"}` on 200, or 503 with error
- Checks if main server socket is responding (liveness/readiness validation)
- Runs on separate thread to isolate from main API load

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
- [API Reference](../API.md)
- [Development Guide](../DEVELOPMENT.md)
- [Kubernetes Deployment](../deployment/kubernetes.md)
- [Contributing Guidelines](../CONTRIBUTING.md)
- [Monitoring & Observability](../MONITORING.md)
- [Performance Tuning](../PERFORMANCE.md)
