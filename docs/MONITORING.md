# Monitoring and Observability

This document outlines current and planned monitoring capabilities for the ExternalDNS Technitium Webhook.

## Current Implementation

### Structured Logging

The webhook uses structured logging in External-DNS format with key-value pairs:

```
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

### Health Checks

**Endpoints** (on separate health server thread, port 8080):
- `GET /health` - Liveness probe
- `GET /healthz` - Readiness probe (Kubernetes-style)

**Behavior**:
- Returns `200 OK` with `{"status": "ok"}` when service is ready
- Returns `503 Service Unavailable` when not ready
- Checks main API server connectivity (port 8888)
- Runs on separate thread to isolate from main API load

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
```
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
```
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
```
time="2025-11-02T20:33:18Z" level=info module=external_dns_technitium_webhook.handlers msg="  CREATE: test.example.com (A) -> ['192.0.2.1']"
time="2025-11-02T20:33:19Z" level=info module=external_dns_technitium_webhook.handlers msg="Adding record test.example.com with data {'ipAddress': '192.0.2.1'}"
time="2025-11-02T20:33:20Z" level=info module=external_dns_technitium_webhook.handlers msg="  DELETE: old.example.com (A) -> ['192.0.2.2']"
time="2025-11-02T20:33:21Z" level=info module=external_dns_technitium_webhook.handlers msg="Deleting record old.example.com with data {'ipAddress': '192.0.2.2'}"
```

**Authentication renewal**:
```
time="2025-11-02T20:33:15Z" level=warning module=external_dns_technitium_webhook.technitium_client msg="Token expired, renewing authentication"
time="2025-11-02T20:33:16Z" level=info module=external_dns_technitium_webhook.technitium_client msg="Successfully renewed authentication token"
```

**Rate limiting**:
```
time="2025-11-02T20:33:20Z" level=warning module=external_dns_technitium_webhook.middleware msg="Rate limit exceeded for client 10.0.0.1. Tokens: 0.50"
```

**Connection issues**:
```
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
