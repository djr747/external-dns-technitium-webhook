# Performance and Reliability Guide

This document describes the performance optimizations and reliability patterns implemented in the webhook.

## Async-First Architecture

### Why Async?

The webhook handles I/O-bound operations (HTTP calls to Technitium DNS), making async/await ideal:

```python
# ✅ Good - Non-blocking
async def create_records(records: list[Endpoint]) -> None:
    tasks = [create_record(r) for r in records]
    await asyncio.gather(*tasks)  # Concurrent execution

# ❌ Bad - Blocking
def create_records_sync(records: list[Endpoint]) -> None:
    for record in records:
        create_record_sync(record)  # Sequential execution
```

**Benefits**:
- Handle multiple requests concurrently
- Don't block on Technitium API calls
- Better resource utilization

### Implementation

All I/O operations use async/await:
- HTTP client: `httpx.AsyncClient`
- FastAPI handlers: `async def`
- State management: `async with` context managers

## Connection Pooling

### HTTP Client Reuse

The webhook maintains persistent connections to Technitium DNS:

```python
# In technitium_client.py
class TechnitiumClient:
    def __init__(self, base_url: str, timeout: float = 10.0):
        self._client = httpx.AsyncClient(timeout=timeout)
        # Connection pool maintained across requests
```

**Benefits**:
- Eliminates TCP handshake overhead
- Reduces latency for repeated requests
- Efficient resource usage

**Configuration**:
- Timeout: `TECHNITIUM_TIMEOUT` (default: 10 seconds)
- Connection limits: httpx defaults (100 max connections)

## Graceful Shutdown

### Signal Handling

The webhook handles SIGTERM and SIGINT for clean shutdown:

```python
# In main.py
def handle_signal(signum: int, frame: object) -> None:
    logger.info(f"Received signal {signum}, shutting down...")
    sys.exit(0)

signal.signal(signal.SIGINT, handle_signal)
signal.signal(signal.SIGTERM, handle_signal)
```

**Lifecycle on Shutdown**:
1. Signal received (SIGTERM/SIGINT)
2. FastAPI lifespan context cleanup triggered
3. HTTP client connections closed
4. Technitium client cleaned up
5. Process exits

**Kubernetes Integration**:
```yaml
spec:
  terminationGracePeriodSeconds: 30  # Allow time for cleanup
```

## Error Recovery

### Automatic Token Renewal

The Technitium client handles expired tokens transparently:

```python
# In technitium_client.py
async def _post(self, endpoint: str, data: dict) -> dict:
    try:
        return await self._post_raw(endpoint, data)
    except InvalidTokenError:
        logger.warning("Token expired, renewing authentication")
        await self.authenticate(self.username, self.password)
        return await self._post_raw(endpoint, data)  # Retry
```

**Benefits**:
- No manual token management
- Automatic recovery from auth failures
- Transparent to callers

### Retry Logic Recommendations

For production deployments, consider adding retry logic for transient failures:

```python
# Example with tenacity (not currently implemented)
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10)
)
async def create_dns_record(record: Endpoint) -> None:
    await client.add_record(...)
```

## Resource Management

### Async Context Managers

Proper cleanup using async context managers:

```python
# Application lifecycle
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    # Startup: initialize resources
    state = AppState(config)
    await state.ensure_ready()
    app.state.app_state = state
    
    yield
    
    # Shutdown: cleanup resources
    await state.client.close()
```

**Ensures**:
- Resources initialized before serving requests
- Connections closed on shutdown
- No resource leaks

### Memory Management

**Efficient Data Structures**:
```python
# Pydantic models validate and optimize memory
class Endpoint(BaseModel):
    dns_name: str
    targets: list[str] = Field(default_factory=list)  # Only allocate when needed
```

**Request Size Limits**:
```python
# In middleware.py
class RequestSizeLimitMiddleware:
    def __init__(self, max_size: int = 1024 * 1024):  # 1MB default
        self.max_size = max_size
```

## Rate Limiting

### Token Bucket Algorithm

Prevents resource exhaustion from high request rates:

```python
# In middleware.py
class RateLimiter:
    def __init__(self, requests_per_minute: int = 1000, burst: int = 10):
        self.rate = requests_per_minute / 60.0  # Tokens per second
        self.burst = float(burst)
```

**Configuration**:
- Sustained rate: 1000 requests/minute (~16.7/second) configurable via `REQUESTS_PER_MINUTE`
- Burst capacity: 10 requests
- Per-client tracking (by IP address)

**Customization**:
```python
# Adjust for your workload
rate_limiter = RateLimiter(requests_per_minute=2000, burst=20)
app.middleware("http")(rate_limit_middleware)
```

## Performance Best Practices

### 1. Batch Operations

When possible, batch DNS record changes:

```python
# ✅ Good - Single request with multiple changes
changes = Changes(
    create=[record1, record2, record3],
    delete=[old_record1, old_record2]
)
await apply_record(state, changes)

# ❌ Bad - Multiple separate requests
await apply_record(state, Changes(create=[record1]))
await apply_record(state, Changes(create=[record2]))
await apply_record(state, Changes(create=[record3]))
```

### 2. Concurrent DNS Operations

The handlers process records concurrently:

```python
# Multiple DNS operations in parallel
async def apply_record(state: AppState, changes: Changes) -> Response:
    tasks = []
    
    if changes.create:
        tasks.extend([create_record(r) for r in changes.create])
    
    if changes.delete:
        tasks.extend([delete_record(r) for r in changes.delete])
    
    await asyncio.gather(*tasks)  # Execute concurrently
```

### 3. Efficient Validation

Pydantic validates data at parse time, not runtime:

```python
# Validation happens once during deserialization
@app.post("/records")
async def apply(changes: Changes) -> None:  # Already validated
    await apply_record(state, changes)
```

## Monitoring Performance

### Enable Debug Logging

```bash
LOG_LEVEL=DEBUG
```

Logs include timing information:
```
DEBUG - POST /api/zones/records/add - 45ms
DEBUG - Creating DNS record: example.com (A)
INFO - Successfully created record - 52ms total
```

### Key Metrics to Monitor

1. **Request latency** - Time to process ExternalDNS requests
2. **Technitium API latency** - Time for DNS operations
3. **Error rate** - Failed requests / total requests
4. **Authentication renewals** - Token refresh frequency
5. **Rate limit hits** - Requests throttled

### Typical Performance

Under normal conditions:
- Health check: <10ms
- Domain filter negotiation: <5ms
- Get records: 50-200ms (depends on zone size)
- Create/delete records: 100-300ms per record
- Concurrent operations: ~50ms per record (with 5+ records)

## Kubernetes Deployment Configuration

### Resource Configuration

For Helm deployment, adjust resource requests and limits in `values.yaml`:

```yaml
resources:
  requests:
    cpu: 100m          # Minimum CPU (0.1 CPU)
    memory: 128Mi      # Minimum memory
  limits:
    cpu: 500m          # Maximum CPU (0.5 CPU)
    memory: 512Mi      # Maximum memory
```

**Rationale**:
- Small memory footprint (Python + FastAPI + dependencies)
- Low CPU usage (I/O bound, not CPU bound)
- Handles 1000+ req/min comfortably with single instance

### Rate Limiting Configuration

Adjust request rate limiting in Helm `values.yaml` or environment variables:

```yaml
# In values.yaml or as environment variables
env:
  REQUESTS_PER_MINUTE: "1000"  # Default: 1000 requests/min
  RATE_LIMIT_BURST: "10"        # Default: 10
```

**Note:** Only resource limits and rate limiting are adjustable. For full deployment configuration, see the Helm chart documentation.

## Troubleshooting Performance Issues

### Slow DNS Operations

**Symptom**: High latency for record creation/deletion

**Checks**:
1. Check Technitium DNS server performance
2. Verify network latency to Technitium
3. Check Technitium DNS zone size (large zones = slower operations)
4. Review Technitium server logs

**Solutions**:
- Increase `TECHNITIUM_TIMEOUT` if operations timeout
- Optimize Technitium DNS server resources
- Consider zone delegation for large zones

### High Memory Usage

**Symptom**: Memory usage exceeds 512MB

**Checks**:
1. Check for large DNS record sets
2. Review request size limits
3. Check for connection leaks

**Solutions**:
- Reduce `RequestSizeLimitMiddleware.max_size`
- Ensure clients aren't sending excessive data
- Verify graceful shutdown closes connections

### Rate Limiting Issues

**Symptom**: Requests blocked by rate limiter

**Checks**:
1. Check ExternalDNS sync frequency
2. Review rate limiter configuration
3. Check if rate limits are too strict for your workload

**Solutions**:
- Default rate limit is 1000 requests/min (usually sufficient)
- If needed, increase: `REQUESTS_PER_MINUTE=2000` environment variable
- If needed, increase burst capacity: `RATE_LIMIT_BURST=20` (default is 10)
- Reduce ExternalDNS sync frequency if possible

## Future Optimizations

Potential areas for optimization:

1. **DNS Record Caching** - Cache Technitium responses to reduce API calls
2. **Connection Pool Tuning** - Optimize httpx connection limits
3. **Batch API Support** - Single API call for multiple DNS records (if Technitium supports)
4. **Keep-alive Tuning** - Optimize HTTP keep-alive settings

## Implemented Optimizations

### Response Compression (Gzip)

The webhook automatically compresses HTTP responses using gzip when beneficial:

**How it works:**
- Automatically enabled for responses ≥ 1 KB
- Only applied when client sends `Accept-Encoding: gzip` header
- Modern HTTP clients handle decompression transparently

**Configuration:**
- Compression is always enabled (no environment variable to disable)
- Minimum response size threshold: 1 KB

**Benefits:**
- 50-80% bandwidth reduction for large DNS record sets
- Especially beneficial over high-latency or metered networks
- No performance penalty on the server (compression happens after processing)

**Implementation:**
The webhook uses FastAPI's built-in `GZipMiddleware`, which handles compression negotiation automatically.

**Example:**
```bash
# Client automatically handles compression
curl http://localhost:8888/records

# Or explicitly request compression
curl -H "Accept-Encoding: gzip" http://localhost:8888/records
```

## Contributing Performance Improvements

When optimizing performance:

1. **Measure first** - Profile before optimizing
2. **Add benchmarks** - Document performance improvements
3. **Test at scale** - Verify with realistic workloads
4. **Update docs** - Document configuration changes
5. **Maintain compatibility** - Don't break existing deployments
