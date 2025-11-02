"""Server setup and run_servers coroutine for ExternalDNS Technitium Webhook."""

import asyncio
import contextlib
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
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            async def serve_and_signal() -> None:
                logging.info("Health server starting...")

                # Start the server but don't wait for it immediately
                server_task = asyncio.create_task(health_server.serve())

                # Give uvicorn a brief moment to bind to the port and start accepting connections
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(asyncio.sleep(0.5), timeout=1.0)

                # Signal that the server is ready (after binding attempt)
                health_server_ready.set()
                logging.info(
                    f"Health server listening on {config.listen_address}:{config.health_port}"
                )

                # Now wait for the server indefinitely (until it exits)
                try:
                    await server_task
                except Exception as serve_error:
                    logging.error(f"Health server serve error: {serve_error}", exc_info=True)

            loop.run_until_complete(serve_and_signal())
        except Exception as e:
            health_server_error = e
            logging.error(f"Health server error: {e}", exc_info=True)
        finally:
            health_server_ready.set()  # Signal even on error to unblock main thread
            with contextlib.suppress(Exception):
                loop.close()

    health_thread = threading.Thread(target=run_health_server, daemon=True)
    health_thread.start()

    # Wait for health server to be ready, with timeout
    if not health_server_ready.wait(timeout=10):
        logging.error("Health server failed to start (timeout waiting for server to bind to port)")
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
