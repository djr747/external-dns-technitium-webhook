"""ExternalDNS webhook provider for Technitium DNS."""

from importlib.metadata import PackageNotFoundError, version

from .technitium_client import InvalidTokenError, TechnitiumClient, TechnitiumError

# Get version from installed package metadata (pyproject.toml)
try:
    __version__ = version("external-dns-technitium-webhook")
except PackageNotFoundError:
    # Fallback for development environments where package isn't installed
    __version__ = "0.0.0+dev"

__all__ = ["TechnitiumClient", "TechnitiumError", "InvalidTokenError", "__version__"]
