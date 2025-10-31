# Webhook API Reference

The Technitium webhook implements the [ExternalDNS webhook specification](https://github.com/kubernetes-sigs/external-dns/blob/master/docs/tutorials/webhook-provider.md). All responses use the media type `application/external.dns.webhook+json;version=1` unless stated otherwise.

## Base URL
Default bind address is `http://0.0.0.0:3000`. Adjust with `LISTEN_ADDRESS` / `LISTEN_PORT` environment variables.

## Supported Record Types
`A`, `AAAA`, `CNAME`, `TXT`, `ANAME`, `CAA`, `URI`, `SSHFP`, `SVCB`, `HTTPS`

Provider-specific options (e.g., comments, expiry TTL, PTR creation, SVCB hints) are passed through using the `providerSpecific` array on each endpoint.

## Endpoints

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Readiness probe; returns `503` until initialization completes |
| `GET` | `/` | Domain filter negotiation (startup only) |
| `GET` | `/records` | Fetch current records for the configured zone |
| `POST` | `/adjustendpoints` | Optional endpoint rewrites (no-op in this provider) |
| `POST` | `/records` | Apply create/update/delete operations |

### `GET /health`
- `200 OK` when the Technitium connection is initialized and writable (if required)
- `503 Service Unavailable` with a sanitized error message otherwise

### `GET /`
Returns the negotiated domain filters based on `DOMAIN_FILTERS`:
```json
{
  "filters": ["example.com"],
  "exclude": []
}
```

### `GET /records`
Returns an array of ExternalDNS endpoints sourced from Technitium:
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

### `POST /adjustendpoints`
Accepts an array of desired endpoints and returns the same payload unchanged. The hook exists for compatibility and validation only.

### `POST /records`
Accepts an object with `create`, `updateOld`, `updateNew`, and `delete` arrays. All fields are optional; missing keys default to empty lists. A successful request returns `204 No Content`.

Example: create a disabled A record with metadata
```json
{
  "create": [
    {
      "dnsName": "blue.example.com",
      "recordType": "A",
      "targets": ["192.0.2.20"],
      "providerSpecific": [
        {"name": "comment", "value": "staging"},
        {"name": "disable", "value": "true"},
        {"name": "expiryTtl", "value": "86400"}
      ]
    }
  ]
}
```

Errors are reported as sanitized JSON messages with appropriate HTTP status codes (`400`, `500`, `503`).

## Rate Limiting & Payload Limits
- Requests are limited using a token bucket (`REQUESTS_PER_MINUTE` and `RATE_LIMIT_BURST`). 429 responses include a descriptive error string.
- The request body size is capped (default 1 MB) and returns `413` when exceeded.

## Authentication
The webhook listens on localhost inside the ExternalDNS pod and does not expose additional authentication. It authenticates to Technitium using the configured credentials and refreshes tokens automatically.
