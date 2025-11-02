"""Configuration management for the application."""

from pathlib import Path
from typing import Any

from pydantic_settings import BaseSettings, SettingsConfigDict


class Config(BaseSettings):
    """Application configuration loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    listen_address: str = "0.0.0.0"
    listen_port: int = 3000
    technitium_url: str
    technitium_username: str
    technitium_password: str
    zone: str
    domain_filters: str | None = None
    log_level: str = "INFO"
    technitium_timeout: float = 10.0  # HTTP client timeout in seconds
    requests_per_minute: int = 1000
    rate_limit_burst: int = 10
    technitium_failover_urls: str | None = None
    catalog_zone: str | None = None
    technitium_verify_ssl: bool = True
    # Optional path to a PEM file containing one or more CA certificates.
    # Intended to be mounted via ConfigMap (like username/password secrets).
    # When verify_ssl is True and ca_bundle is set, the file must exist and be readable.
    technitium_ca_bundle: str | None = None

    def __init__(self, **values: Any) -> None:
        """Allow instantiation without explicit arguments for env loading."""
        super().__init__(**values)
        # Validate CA bundle after model initialization
        if self.technitium_verify_ssl and self.technitium_ca_bundle:
            path = Path(self.technitium_ca_bundle)
            if not path.exists() or not path.is_file():
                raise ValueError(
                    f"TECHNITIUM_CA_BUNDLE path '{self.technitium_ca_bundle}' does not exist or is not a regular file"
                )
            try:
                with path.open("rb"):
                    pass
            except Exception as exc:
                raise ValueError(f"TECHNITIUM_CA_BUNDLE file is not readable: {exc}") from exc

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
            f"password=***REDACTED***, "
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
            data["technitium_password"] = "***REDACTED***"
        return data
