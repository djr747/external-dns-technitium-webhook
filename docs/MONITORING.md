# Monitoring and Observability

This document outlines current and planned monitoring capabilities for the ExternalDNS Technitium Webhook.

## Current Implementation

### Structured Logging

The webhook uses structured logging in External-DNS format with key-value pairs:

```logs
time="2025-11-02T20:33:18Z" level=info module=external_dns_technitium_webhook.handlers msg="Successfully created DNS record"
time="2025-11-02T20:33:19Z" level=error module=external_dns_technitium_webhook.technitium_client msg="Failed to authenticate: Invalid credentials"
```

**Log Format**: `time="TIMESTAMP" level=LEVEL module=MODULE msg="MESSAGE"`

**Configuration**: Set `LOG_LEVEL` environment variable (DEBUG, INFO, WARNING, ERROR)

**Log Levels in Use**:

- `DEBUG` - Detailed API call traces and internal operations
- `INFO` - Normal successful operations
- `WARNING` - Retry attempts, degraded conditions, token renewals
- `ERROR` - Failures and exceptions

**Best Practices**:

- Enable DEBUG in development to troubleshoot API interactions
- Use INFO in production for normal operation tracking
- Monitor WARNING logs for retry patterns indicating issues
- Alert on ERROR logs for immediate investigation

### Failover & Failback Monitoring

**Cluster Detection & Recovery Events**:

Watch for these key log messages to understand failover/failback behavior:

```logs
# Connection error detected - failover initiated
time="2025-11-02T20:33:20Z" level=warning module=handlers msg="Connection error detected, attempting failover to alternate endpoints: Connection refused"

# Successful failover to alternate endpoint
time="2025-11-02T20:33:21Z" level=info module=app_state msg="Successfully authenticated with failover endpoint http://secondary1:5380"

# Cluster role detected (primary vs secondary)
time="2025-11-02T20:33:21Z" level=info module=app_state msg="Failover endpoint http://secondary1:5380 is secondary node (writable=false)"

# Retry after failover succeeded
time="2025-11-02T20:33:22Z" level=info module=handlers msg="Failover successful to writable endpoint, retrying record changes"

# Intelligent failback to primary
time="2025-11-02T20:35:30Z" level=info module=main msg="Successfully failed back to primary endpoint"

# Token renewal continues independently
time="2025-11-02T20:40:00Z" level=debug module=main msg="Successfully renewed Technitium DNS server access token"
```

**Monitoring Checklist**:

| Event | Log Level | What It Means | Action |
| --- | --- | --- | --- |
| "Connection error detected" | WARNING | Primary failed, attempting failover | Monitor - automatic recovery in progress |
| "Successfully authenticated with failover endpoint" | INFO | Failover succeeded, now on secondary | Monitor - waiting for primary recovery |
| "secondary node (writable=false)" | INFO | Confirmed on read-only replica | Expected when primary is down |
| "Successfully failed back to primary" | INFO | Primary recovered and is writable | Good - normal operation restored |
| "Failover endpoint X is primary node (writable=true)" | INFO | Failover to alternate primary | Monitor - verify topology is as expected |
| "All failover endpoints failed" | ERROR | Complete outage across all nodes | **CRITICAL** - check Technitium cluster health |

**Failover Method Summary**:

- Failover is event-driven on connection errors (no fixed timer for initial failover).
- Failback is polling-based and controlled by `HEALTH_POLLING_INTERVAL_SECONDS` (default: 15 seconds).
- Polling checks both endpoint reachability and endpoint role/writability before failback.
- The webhook only fails back to a node when it is confirmed writable.

**Key Timings to Monitor**:

- **Failover detection**: < 1 second (triggered by connection error)
- **Failback attempt frequency**: Every `HEALTH_POLLING_INTERVAL_SECONDS` (default: 15 seconds)
- **Failback success**: Typically one poll cycle after primary recovers and is writable
- **Token renewal**: Every 20 minutes (normal) or 1 minute (after failure)

**Setting up Alerts**:

```yaml
# Example Prometheus alerting rules (future enhancement)
- alert: TechnitiumFailoverActive
  expr: rate(failover_attempts_total[5m]) > 0
  for: 1m
  annotations:
    summary: "Active Technitium DNS failover"

- alert: TechnitiumAllNodesFailed
  expr: rate(all_failover_endpoints_failed_total[5m]) > 0
  for: 30s
  annotations:
    summary: "All Technitium DNS nodes unreachable"
```

### Health Checks

**Endpoints** (on separate health server thread, port 8080):

> Ports 8888 (main API) and 8080 (health) are hard-coded by the ExternalDNS
> controller; users cannot change them in production. They appear here for
> completeness and to guide probe configuration.

- `GET /health` - Liveness probe
- `GET /healthz` - Readiness probe (Kubernetes-style)

**Behavior**:

- Returns `200 OK` with `{"status": "ok"}` when service is ready and circuit breaker is closed
- Returns `503 Service Unavailable` when:
  - During the **startup delay period** (default 10 seconds) while initializing Technitium connections
  - Not yet connected to Technitium
  - Circuit breaker is open (distinguishable by `"circuit_breaker": "open"` in response)
- Checks main API server connectivity (port 8888)
- Runs on separate thread to isolate from main API load

**Startup Sequence (Non-Blocking)**:
The webhook server starts accepting connections on port 8888 **immediately**, even during Technitium initialization:

1. Pod starts
2. Server binds to port 8888 and accepts connections
3. Technitium setup runs in background (connecting, authenticating, checking zones)
4. Handler requests return `503 Service Unavailable` until Technitium is ready
5. After Technitium is ready, handlers return normal responses

This prevents "connection refused" errors. ExternalDNS can connect immediately and retries until the service is ready.

**Startup Delay**: 
The health check endpoint (port 8080) includes a configurable grace period (default `STARTUP_DELAY_SECONDS=10`) before reporting ready. This gives Technitium initialization time to complete.

**Tuning Startup Delay**:
If your Technitium DNS server has high latency or initial zone checks are slow, increase `STARTUP_DELAY_SECONDS`:

```bash
# For slow Technitium connections (WAN, high latency)
STARTUP_DELAY_SECONDS=30

# For very fast local connections
STARTUP_DELAY_SECONDS=5

# To disable (not recommended)
STARTUP_DELAY_SECONDS=0
```

**Kubernetes Integration**:

```yaml
livenessProbe:
  httpGet:
    path: /health
    port: 8080
  initialDelaySeconds: 10
  periodSeconds: 30
  timeoutSeconds: 5
  failureThreshold: 3

readinessProbe:
  httpGet:
    path: /healthz
    port: 8080
  initialDelaySeconds: 5
  periodSeconds: 10
  timeoutSeconds: 3
  failureThreshold: 2
```

> **Note**: The `initialDelaySeconds` in Kubernetes probes should be **less than** your `STARTUP_DELAY_SECONDS` environment variable. This allows the health server to start reporting status during the grace period. For example, if `STARTUP_DELAY_SECONDS=15`, use `initialDelaySeconds: 5` in the probe configuration.

### Performance Monitoring (Current)

**Current Approach**: Structured logging with DEBUG level

Enable DEBUG logging to observe performance:

```bash
# Kubernetes
kubectl set env deployment/external-dns LOG_LEVEL=DEBUG

# Docker
docker run -e LOG_LEVEL=DEBUG ...
```

Debug logs include operation details that help identify performance issues:

```logs
time="2025-11-02T20:33:18Z" level=debug module=technitium_client msg="Fetching records from zone example.com"
time="2025-11-02T20:33:18Z" level=info module=handlers msg="Found 42 endpoints"
```

## Planned Enhancements

### 1. Prometheus Metrics (Future)

**Planned Metrics**:

```python
# Counter metrics
webhook_requests_total{method, endpoint, status}
webhook_dns_records_created_total{zone, record_type}
webhook_dns_records_deleted_total{zone, record_type}
webhook_technitium_api_calls_total{endpoint, status}
webhook_errors_total{error_type}

# Histogram metrics  
webhook_request_duration_seconds{method, endpoint}
webhook_technitium_api_duration_seconds{endpoint}

# Gauge metrics
webhook_active_connections
webhook_dns_records_managed{zone}
```

**Endpoint**: `GET /metrics` (Prometheus format)

**Implementation Plan**:

1. Add `prometheus_client` dependency
2. Create metrics module (`external_dns_technitium_webhook/metrics.py`)
3. Add middleware to track request metrics
4. Instrument Technitium client for API call metrics
5. Add metrics endpoint to FastAPI app

### 2. OpenTelemetry Tracing (Future)

**Planned Features**:

- Distributed tracing across webhook → Technitium DNS
- Span tracking for DNS operations
- Correlation IDs for request tracking

**Implementation Plan**:

1. Add `opentelemetry-api` and `opentelemetry-sdk` dependencies
2. Add OTLP exporter for backend integration
3. Instrument FastAPI with auto-instrumentation
4. Add custom spans for business logic
5. Configure sampling strategy

**Example Trace**:

```text
ExternalDNS Request
└── POST /records (webhook)
    ├── Authenticate (Technitium)
    ├── Verify Zone (Technitium)
    ├── Create A Record (Technitium)
    └── Response
```

### 3. Custom Dashboard (Future)

**Grafana Dashboard** showing:

- Request rate and latency
- DNS record creation/deletion rate
- Technitium API health
- Error rates by type
- Active connections
- Resource utilization

## Troubleshooting

### View Logs

```bash
# Kubernetes
kubectl logs -f deployment/external-dns -c webhook

# Docker
docker logs -f <container-id>
```

### Common Log Patterns

**Successful DNS operations**:

```logs
time="2025-11-02T20:33:18Z" level=info module=external_dns_technitium_webhook.handlers msg="  CREATE: test.example.com (A) -> ['192.0.2.1']"
time="2025-11-02T20:33:19Z" level=info module=external_dns_technitium_webhook.handlers msg="Adding record test.example.com with data {'ipAddress': '192.0.2.1'}"
time="2025-11-02T20:33:20Z" level=info module=external_dns_technitium_webhook.handlers msg="  DELETE: old.example.com (A) -> ['192.0.2.2']"
time="2025-11-02T20:33:21Z" level=info module=external_dns_technitium_webhook.handlers msg="Deleting record old.example.com with data {'ipAddress': '192.0.2.2'}"
```

**Authentication renewal**:

```logs
time="2025-11-02T20:33:15Z" level=warning module=external_dns_technitium_webhook.technitium_client msg="Token expired, renewing authentication"
time="2025-11-02T20:33:16Z" level=info module=external_dns_technitium_webhook.technitium_client msg="Successfully renewed authentication token"
```

**Rate limiting**:

## Technitium Cluster References

- [Technitium DNS Server features (includes clustering and catalog zones)](https://technitium.com/dns/)
- [Technitium DNS HTTP API documentation](https://github.com/TechnitiumSoftware/DnsServer/blob/master/APIDOCS.md)
- [Technitium Catalog Zones RFC reference (RFC 9432)](https://datatracker.ietf.org/doc/rfc9432/)

```logs
time="2025-11-02T20:33:20Z" level=warning module=external_dns_technitium_webhook.middleware msg="Rate limit exceeded for client 10.0.0.1. Tokens: 0.50"
```

**Circuit breaker**:

```logs
# Circuit opens after consecutive failures
time="2025-11-02T20:33:10Z" level=warning module=external_dns_technitium_webhook.resilience msg="Circuit breaker transitioning CLOSED → OPEN after 5 consecutive failures"

# Fast rejection while open
time="2025-11-02T20:33:11Z" level=warning module=external_dns_technitium_webhook.technitium_client msg="Circuit breaker is open; retry after 58.3s"

# Probe request after timeout
time="2025-11-02T20:34:12Z" level=info module=external_dns_technitium_webhook.resilience msg="Circuit breaker transitioning OPEN → HALF_OPEN after timeout"

# Recovery
time="2025-11-02T20:34:13Z" level=info module=external_dns_technitium_webhook.resilience msg="Circuit breaker transitioning HALF_OPEN → CLOSED after successful request"
```

**Connection issues**:

```logs
time="2025-11-02T20:33:10Z" level=error module=external_dns_technitium_webhook.technitium_client msg="Failed to connect to Technitium: Connection refused"
time="2025-11-02T20:33:15Z" level=info module=external_dns_technitium_webhook.technitium_client msg="Retrying connection after 5 seconds..."
```

## Performance Optimization

### Connection Pooling

The webhook maintains a persistent `httpx.AsyncClient` instance for all requests to Technitium:

```python
# In TechnitiumClient.__init__()
self._client = httpx.AsyncClient(timeout=timeout, verify=verify)

# Reused across all API calls
response = await self._client.post(url, data=data)
```

This approach:

- Eliminates TCP handshake overhead for each request
- Reuses connections through HTTP keep-alive
- Reduces latency for repeated API calls
- Improves overall throughput

### Async Operations

All I/O operations use async/await for non-blocking behavior:

```python
# Example: DNS record deletion
await state.client.delete_record(
    domain=ep.dns_name,
    record_type=ep.record_type,
    record_data=record_data,
)
```

Each API call to Technitium is awaited, allowing the FastAPI event loop to handle other requests while waiting for responses. This prevents blocking and enables efficient resource utilization.

### Rate Limiting

Middleware prevents abuse:

- Default: 1000 requests/minute per client (configurable via `REQUESTS_PER_MINUTE`)
- Burst capacity: 10 requests
- Configurable via `RateLimiter` class

## Monitoring Checklist

When deploying to production, ensure:

- [ ] Health checks configured in Kubernetes (port 8080)
- [ ] Log aggregation set up (ELK, Loki, CloudWatch, etc.)
- [ ] Log retention policy defined
- [ ] Alert rules configured for error rates
- [ ] Alert rules for health check failures
- [ ] Response time SLOs defined
- [ ] Resource limits set (CPU, memory)
- [ ] Single instance deployment verified (ExternalDNS doesn't support HA)

## Future Roadmap

1. **Phase 1** (Current): Structured logging + health checks
2. **Phase 2**: Prometheus metrics export
3. **Phase 3**: OpenTelemetry distributed tracing
4. **Phase 4**: Pre-built Grafana dashboards
5. **Phase 5**: Alerting best practices documentation

## Contributing

If implementing metrics or tracing:

1. Follow the implementation plans above
2. Ensure backward compatibility (metrics optional)
3. Add configuration documentation
4. Update this document with examples
5. Add tests for new monitoring features
