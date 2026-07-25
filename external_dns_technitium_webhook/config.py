"""Configuration management for the application."""

import os
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from pydantic_settings import BaseSettings, SettingsConfigDict

_REDACTED_VALUE = "***REDACTED***"


class Config(BaseSettings):
    """Application configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    listen_address: str = "0.0.0.0"
    listen_port: int = 8888
    health_port: int = 8080  # Separate port for health checks (security separation)
    technitium_url: str  # Required: Technitium DNS API endpoint
    technitium_username: str  # Required: Technitium authentication username
    technitium_password: str  # Required: Technitium authentication password
    zone: str  # Required: Primary DNS zone
    domain_filters: str | None = None
    log_level: str = "INFO"
    technitium_timeout: float = 10.0  # HTTP client timeout in seconds
    requests_per_minute: int = 1000
    rate_limit_burst: int = 10
    technitium_failover_urls: str | None = None
    catalog_zone: str | None = None
    # Optional path to a PEM file containing one or more CA certificates.
    # Intended to be mounted via ConfigMap (like username/password secrets).
    # When set, the file must exist and be readable.
    technitium_ca_bundle_file: str | None = None
    technitium_enable_request_compression: bool = False
    technitium_compression_threshold_bytes: int = 32768
    circuit_breaker_failure_threshold: int = 5
    circuit_breaker_timeout: float = 60.0
    records_cache_ttl_seconds: float = 0.0  # TTL for get_records cache (0 to disable)
    health_polling_interval_seconds: float = 15.0  # Health check polling interval
    startup_delay_seconds: float = (
        10.0  # Grace period during startup before health checks return ready
    )

    def __init__(self, **values: Any) -> None:
        """Allow instantiation without explicit arguments for env loading."""
        if "TECHNITIUM_VERIFY_SSL" in os.environ:
            raise ValueError(
                "TECHNITIUM_VERIFY_SSL is no longer supported; remove it. "
                "TLS certificate and hostname verification are always enabled."
            )
        super().__init__(**values)
        for endpoint in self.technitium_endpoints:
            parsed = urlparse(endpoint)
            if parsed.scheme.lower() != "https" or not parsed.netloc:
                raise ValueError("TECHNITIUM_URL and TECHNITIUM_FAILOVER_URLS must use HTTPS URLs.")
        # Validate CA bundle after model initialization
        if self.technitium_ca_bundle_file:
            path = Path(self.technitium_ca_bundle_file)
            if not path.exists() or not path.is_file():
                raise ValueError(
                    f"TECHNITIUM_CA_BUNDLE_FILE path '{self.technitium_ca_bundle_file}' does not exist or is not a regular file"
                )
            try:
                with path.open("rb"):
                    # Open file to ensure it is readable; no content is read.
                    pass
            except Exception as exc:
                raise ValueError(f"TECHNITIUM_CA_BUNDLE_FILE file is not readable: {exc}") from exc

    @property
    def domain_filter_list(self) -> list[str]:
        """Parse domain filters from semicolon-separated string."""
        if not self.domain_filters:
            return []
        return [f.strip() for f in self.domain_filters.split(";") if f.strip()]

    @property
    def technitium_endpoints(self) -> list[str]:
        """Get ordered list of Technitium API endpoints for HA setups."""

        endpoints: list[str] = []

        def _add(url: str | None) -> None:
            if not url:
                return
            normalized = url.strip()
            if not normalized:
                return
            normalized = normalized.rstrip("/")
            if normalized not in endpoints:
                endpoints.append(normalized)

        _add(self.technitium_url)
        if self.technitium_failover_urls:
            for candidate in self.technitium_failover_urls.split(";"):
                _add(candidate)

        return endpoints

    @property
    def catalog_zone_name(self) -> str | None:
        """Normalized catalog zone name, if configured."""

        if not self.catalog_zone:
            return None

        normalized = self.catalog_zone.strip().rstrip(".")
        return normalized.lower() if normalized else None

    @property
    def bind_address(self) -> str:
        """Get the full bind address."""
        return f"{self.listen_address}:{self.listen_port}"

    def __repr__(self) -> str:
        """Safely represent config without exposing password.

        Returns:
            String representation with password redacted
        """
        return (
            f"Config("
            f"url={self.technitium_url}, "
            f"username={self.technitium_username}, "
            f"password={_REDACTED_VALUE}, "
            f"zone={self.zone}, "
            f"filters={self.domain_filter_list})"
        )

    def model_dump(self, **kwargs: Any) -> dict[str, Any]:
        """Dump model with password redacted.

        Args:
            **kwargs: Additional arguments for model_dump

        Returns:
            Dictionary with password redacted
        """
        data = super().model_dump(**kwargs)
        if "technitium_password" in data:
            data["technitium_password"] = _REDACTED_VALUE
        return data
