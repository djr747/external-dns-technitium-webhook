# Monitoring and Observability

This document outlines current and planned monitoring capabilities for the ExternalDNS Technitium Webhook.

## Current Implementation

### Structured Logging

The webhook uses Python's standard logging with structured output:

```python
import logging

logger = logging.getLogger(__name__)

# Log levels in use:
logger.debug("Detailed API call traces")      # DEBUG
logger.info("Normal operations")              # INFO  
logger.warning("Retry attempts, degraded")    # WARNING
logger.error("Failures, exceptions")          # ERROR
```

**Configuration**: Set `LOG_LEVEL` environment variable (DEBUG, INFO, WARNING, ERROR)

**Best Practices**:
- Use DEBUG for API request/response details
- Use INFO for successful operations
- Use WARNING for retries and non-fatal issues
- Use ERROR for failures requiring attention

### Health Checks

**Endpoint**: `GET /health`

**Behavior**:
- Returns `200 OK` when service is ready
- Returns `503 Service Unavailable` when not ready
- Checks Technitium connectivity and authentication

**Kubernetes Integration**:
```yaml
livenessProbe:
  httpGet:
    path: /health
    port: 3000
  initialDelaySeconds: 10
  periodSeconds: 30
  timeoutSeconds: 5
  failureThreshold: 3

readinessProbe:
  httpGet:
    path: /health
    port: 3000
  initialDelaySeconds: 5
  periodSeconds: 10
  timeoutSeconds: 3
  failureThreshold: 2
```

### Performance Monitoring (Manual)

**Current Approach**: Log analysis

Example queries for production logs:
```bash
# Request duration patterns
grep "Request duration" /var/log/webhook.log | awk '{print $NF}'

# Error rates
grep "ERROR" /var/log/webhook.log | wc -l

# API call frequency
grep "POST /records" /var/log/webhook.log | wc -l
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

## Current Troubleshooting

### Enable Debug Logging

```bash
# Kubernetes
kubectl set env deployment/external-dns LOG_LEVEL=DEBUG

# Docker
docker run -e LOG_LEVEL=DEBUG ...

# Docker Compose
LOG_LEVEL=DEBUG docker-compose up
```

### View Logs

```bash
# Kubernetes
kubectl logs -f deployment/external-dns -c webhook

# Docker
docker logs -f <container-id>

# Docker Compose
docker-compose logs -f webhook
```

### Common Log Patterns

**Successful DNS creation**:
```
INFO - Creating DNS record: example.com (A) -> 192.0.2.1
INFO - Successfully created record in zone example.com
```

**Authentication renewal**:
```
WARNING - Token expired, renewing authentication
INFO - Successfully renewed authentication token
```

**Rate limiting**:
```
WARNING - Rate limit exceeded for client 10.0.0.1
```

**Connection issues**:
```
ERROR - Failed to connect to Technitium: Connection refused
ERROR - Retrying in 5 seconds...
```

## Performance Optimization

### Connection Pooling

The webhook uses `httpx.AsyncClient` for connection pooling:

```python
# Reuses connections to Technitium
async with httpx.AsyncClient(timeout=10.0) as client:
    # Multiple requests use same connection
```

### Async Operations

All I/O operations are async to prevent blocking:

```python
# Non-blocking concurrent operations
async def process_changes(changes):
    tasks = [create_record(r) for r in changes.create]
    await asyncio.gather(*tasks)
```

### Rate Limiting

Middleware prevents abuse:
- Default: 1000 requests/minute per client (configurable via `REQUESTS_PER_MINUTE`)
- Burst capacity: 10 requests
- Configurable via `RateLimiter` class

## Monitoring Checklist

When deploying to production, ensure:

- [ ] Health checks configured in Kubernetes
- [ ] Log aggregation set up (ELK, Loki, CloudWatch, etc.)
- [ ] Log retention policy defined
- [ ] Alert rules configured for error rates
- [ ] Alert rules for health check failures
- [ ] Response time SLOs defined
- [ ] Resource limits set (CPU, memory)
- [ ] Horizontal pod autoscaling configured (if needed)

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
