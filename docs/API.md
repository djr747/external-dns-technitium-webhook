# Webhook API Reference

The Technitium webhook implements the [ExternalDNS webhook specification](https://github.com/kubernetes-sigs/external-dns/blob/master/docs/tutorials/webhook-provider.md). All responses use the media type `application/external.dns.webhook+json;version=1` unless stated otherwise.

## Base URLs
- **Main API Server:** `http://0.0.0.0:8888` (default bind address and port)
- **Health Check Server:** `http://0.0.0.0:8080` (separate thread)

## Supported Record Types
`A`, `AAAA`, `CNAME`, `TXT`, `ANAME`, `CAA`, `URI`, `SSHFP`, `SVCB`, `HTTPS`

Provider-specific options (e.g., comments, expiry TTL, PTR creation, SVCB hints) are passed through using the `providerSpecific` array on each endpoint.

## Endpoints

### Main API Server (port 8888)

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/` | Domain filter negotiation (ExternalDNS startup) |
| `GET` | `/records` | Fetch current records for the configured zone |
| `POST` | `/adjustendpoints` | Optional endpoint rewrites (no-op in this provider) |
| `POST` | `/records` | Apply create/update/delete operations |

### Health Check Server (port 8080, separate thread)

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Readiness probe; returns `200 OK` when ready, `503` if not |
| `GET` | `/healthz` | Kubernetes-style readiness probe; same behavior as `/health` |

---

## API Endpoints Reference

### `GET /` (Main API, port 8888)
Domain filter negotiation with ExternalDNS at startup.

**Returns:** 
- `200 OK` with domain filter response when ready
- `503 Service Unavailable` if Technitium is unreachable

**Response body:**
```json
{
  "filters": ["example.com"],
  "exclude": []
}
```

### `GET /records` (Main API, port 8888)
Returns an array of ExternalDNS endpoints currently in Technitium for the configured zone.

**Returns:**
- `200 OK` with array of endpoints when ready
- `503 Service Unavailable` if Technitium is unreachable

**Response body:**
```json
[
  {
    "dnsName": "test.example.com",
    "targets": ["192.0.2.10"],
    "recordType": "A",
    "recordTTL": 3600,
    "providerSpecific": []
  }
]
```

### `POST /adjustendpoints` (Main API, port 8888)
Accepts an array of desired endpoints and returns the same payload unchanged. Provided for ExternalDNS compatibility and validation only.

**Request body:**
```json
[
  {
    "dnsName": "blue.example.com",
    "recordType": "A",
    "targets": ["192.0.2.20"],
    "providerSpecific": []
  }
]
```

**Returns:** `200 OK` with the same endpoint array

### `POST /records` (Main API, port 8888)
Applies DNS record changes (create, update, delete operations). Accepts an object with `create`, `updateOld`, `updateNew`, and `delete` arrays. All fields are optional; missing keys default to empty lists.

**Request body:**
```json
{
  "create": [
    {
      "dnsName": "blue.example.com",
      "recordType": "A",
      "targets": ["192.0.2.20"],
      "providerSpecific": [
        {"name": "comment", "value": "staging"},
        {"name": "disabled", "value": "true"},
        {"name": "expiryTtl", "value": "86400"}
      ]
    }
  ],
  "delete": [],
  "updateOld": [],
  "updateNew": []
}
```

**Returns:**
- `204 No Content` on success
- `400 Bad Request` for invalid input
- `500 Internal Server Error` if Technitium API call fails
- `503 Service Unavailable` if Technitium is unreachable

**Error response:**
```json
{
  "detail": "Failed to create record: Invalid zone name"
}
```

### `GET /health` (Health Server, port 8080)
Kubernetes liveness/readiness probe endpoint.

**Returns:**
- `200 OK` if main API server is ready and responding
- `503 Service Unavailable` if not ready or Technitium is unreachable

**Response body (success):**
```json
{
  "status": "ok"
}
```

**Response body (failure):**
```json
{
  "detail": "Main application not responding"
}
```

### `GET /healthz` (Health Server, port 8080)
Alternative health check endpoint (same as `/health`). Provided for Kubernetes probe flexibility.

**Returns:** Same as `/health`

## Rate Limiting & Payload Limits
- Requests are limited using a token bucket (`REQUESTS_PER_MINUTE` and `RATE_LIMIT_BURST`). 429 responses include a descriptive error string.
- The request body size is capped (default 1 MB) and returns `413` when exceeded.

## Authentication
The webhook does not expose endpoint-level authentication (relies on network isolation in Kubernetes). It authenticates to Technitium using the configured credentials (username/password) and automatically refreshes tokens as needed. Default bind address is `0.0.0.0` (all interfaces); it's typically deployed as a sidecar with ExternalDNS in the same pod.
