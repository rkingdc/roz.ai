# Configure logging
import logging
import os # Need os for environment variables
import uvicorn
# from flask import Flask # Not needed at top level when using factory=True
# from asgiref.wsgi import WsgiToAsgi # Not needed for factory pattern

from app import create_app  # Import the factory function from our app package

logger = logging.getLogger(__name__) # Move logger definition after imports


if __name__ == "__main__":
    # Get config values safely *before* starting uvicorn for logging/reload flag
    # The actual app config is set inside create_app when Uvicorn calls it.

    # Get host and port from environment
    host = os.environ.get('FLASK_RUN_HOST', '127.0.0.1')
    port = int(os.environ.get('FLASK_RUN_PORT', 5000))

    # Determine debug/reload status based on environment variables set by Makefile
    # IS_DEV_SERVER=TRUE is set by the Makefile for start-dev
    debug_reload = os.environ.get('IS_DEV_SERVER', 'False').lower() == 'true' or os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'

    # Log info before starting uvicorn
    # Avoid logging DB_NAME here as it might be misleading before the factory runs
    logger.info(f"Starting Uvicorn server on http://{host}:{port} (Debug/Reload: {debug_reload})")

    # Start uvicorn using the factory pattern
    # Uvicorn will import run.py, find create_app, call it,
    # and automatically wrap the returned Flask (WSGI) app.
    uvicorn.run(
        "run:create_app", # Point to the factory function string
        factory=True,     # Indicate using factory
        host=host,
        port=port,
        log_level="info",
        reload=debug_reload # Enable reload based on debug flag
    )

