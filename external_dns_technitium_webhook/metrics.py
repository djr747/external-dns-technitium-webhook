"""Prometheus metrics for ExternalDNS Technitium Webhook."""

from prometheus_client import Counter, Gauge, Histogram

# Total DNS records processed (create/delete operations)
dns_records_processed_total = Counter(
    "webhook_dns_records_processed_total",
    "Total number of DNS records processed",
    ["operation"],
)

# Latency of Technitium API operations
technitium_latency_seconds = Histogram(
    "webhook_technitium_latency_seconds",
    "Latency of Technitium API operations in seconds",
    ["operation"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

# Webhook readiness (0=not ready, 1=ready)
webhook_ready = Gauge(
    "webhook_ready",
    "Webhook readiness status (1=ready, 0=not ready)",
)

# Total API errors by error type
api_errors_total = Counter(
    "webhook_api_errors_total",
    "Total number of API errors",
    ["error_type"],
)

# Current DNS record count
dns_records_total = Gauge(
    "webhook_dns_records_total",
    "Current number of DNS records in the managed zone",
)
