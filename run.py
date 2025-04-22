# Configure logging
import logging
import os
import uvicorn
# from flask import Flask # Not needed at top level when using factory=True
from asgiref.wsgi import WsgiToAsgi # Needed for explicit wrapping

from app import create_app  # Import the factory function from our app package

logger = logging.getLogger(__name__) # Move logger definition after imports

# Create the Flask app instance using the factory
app = create_app()

# Wrap the Flask (WSGI) app with WsgiToAsgi to create an ASGI app
asgi_app = WsgiToAsgi(app)


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

    # Start uvicorn with the explicitly wrapped ASGI application instance
    uvicorn.run(
        asgi_app,         # Pass the wrapped ASGI app instance
        # factory=True,   # Remove factory=True as we are passing the instance directly
        host=host,
        port=port,
        log_level="info",
        reload=debug_reload # Enable reload based on debug flag
    )

