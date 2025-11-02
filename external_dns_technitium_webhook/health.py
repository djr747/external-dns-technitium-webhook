"""Health check endpoint and logic for ExternalDNS Technitium Webhook."""

import logging
import socket

from fastapi import FastAPI, HTTPException, status

from .config import Config as AppConfig


def is_main_server_ready() -> bool:
    """Check if main server is ready by attempting socket connection."""
    config = AppConfig()
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        result = sock.connect_ex((config.listen_address, config.listen_port))
        sock.close()
        return result == 0
    except Exception as e:
        logging.warning(f"Health check failed: {e}")
        return False


def create_health_app() -> FastAPI:
    app = FastAPI(
        title="ExternalDNS Technitium Webhook - Health",
        description="Health check endpoint for ExternalDNS Technitium webhook",
        version="0.1.0",
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    @app.get("/health")
    async def health() -> dict[str, str]:
        if is_main_server_ready():
            return {"status": "ok"}
        else:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Main application not responding",
            )

    return app
