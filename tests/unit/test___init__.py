"""Tests for package initialization and version resolution."""

import importlib
import importlib.metadata as metadata

import external_dns_technitium_webhook as package


def test_init_uses_installed_package_version(monkeypatch) -> None:
    """Use installed package version when metadata is available."""

    def fake_version(name: str) -> str:
        assert name == "external-dns-technitium-webhook"
        return "1.2.3"

    with monkeypatch.context() as context:
        context.setattr(metadata, "version", fake_version)
        reloaded = importlib.reload(package)
        assert reloaded.__version__ == "1.2.3"
        assert reloaded.__all__ == [
            "TechnitiumClient",
            "TechnitiumError",
            "InvalidTokenError",
            "__version__",
        ]

    importlib.reload(package)


def test_init_falls_back_when_package_metadata_missing(monkeypatch) -> None:
    """Use development fallback version when metadata cannot be resolved."""

    def missing_version(name: str) -> str:
        assert name == "external-dns-technitium-webhook"
        raise metadata.PackageNotFoundError

    with monkeypatch.context() as context:
        context.setattr(metadata, "version", missing_version)
        reloaded = importlib.reload(package)
        assert reloaded.__version__ == "0.0.0+dev"

    importlib.reload(package)
