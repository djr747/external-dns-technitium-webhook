"""Server setup and run_servers coroutine for ExternalDNS Technitium Webhook."""

import asyncio
import logging
import signal
import threading

from fastapi import FastAPI
from uvicorn import Config as UvicornConfig
from uvicorn import Server

from .config import Config as AppConfig


def run_servers(app: FastAPI, health_app: FastAPI, config: AppConfig) -> None:
    main_config = UvicornConfig(
        app=app,
        host=config.listen_address,
        port=config.listen_port,
        log_level=config.log_level.lower(),
    )
    main_server = Server(main_config)
    health_config = UvicornConfig(
        app=health_app,
        host=config.listen_address,
        port=config.health_port,
        log_level=config.log_level.lower(),
        access_log=False,
    )
    health_server = Server(health_config)
    shutdown_event = threading.Event()

    def handle_signal(signum: int, _frame: object) -> None:
        logging.info(f"Received signal {signum}, shutting down...")
        shutdown_event.set()
        main_server.should_exit = True
        health_server.should_exit = True

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    logging.info(f"Starting main server on {config.listen_address}:{config.listen_port}")
    logging.info(f"Starting health server on {config.listen_address}:{config.health_port}")

    health_server_ready = threading.Event()
    health_server_error: Exception | None = None

    def run_health_server() -> None:
        nonlocal health_server_error
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            # Signal that we've started the event loop
            health_server_ready.set()
            logging.debug("Health server event loop started")
            loop.run_until_complete(health_server.serve())
        except Exception as e:
            health_server_error = e
            logging.error(f"Health server error: {e}", exc_info=True)
        finally:
            loop.close()

    health_thread = threading.Thread(target=run_health_server, daemon=True)
    health_thread.start()

    # Wait for health server to be ready, with timeout
    if not health_server_ready.wait(timeout=5):
        logging.error("Health server failed to start (event loop timeout)")
    elif health_server_error:
        logging.error(f"Health server encountered error during startup: {health_server_error}")
    else:
        logging.info("Health server is ready")

    try:
        asyncio.run(main_server.serve())
    except Exception as e:
        logging.error(f"Main server error: {e}")
    finally:
        shutdown_event.set()
        health_thread.join(timeout=5)
