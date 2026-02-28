"""ExternalDNS webhook provider for Technitium DNS."""

from .technitium_client import InvalidTokenError, TechnitiumClient, TechnitiumError

__version__ = "0.4.3"

__all__ = ["TechnitiumClient", "TechnitiumError", "InvalidTokenError", "__version__"]
