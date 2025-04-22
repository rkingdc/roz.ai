
# Configure logging
import logging        
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# run.py
# This script creates the Flask app using the factory
# and runs the development server.
import os
import uvicorn
from flask import Flask
from asgiref.wsgi import WsgiToAsgi

from app import create_app  # Import the factory function from our app package

# Create the Flask app instance
app = create_app()

# Wrap Flask app with ASGI handler
asgi_app = WsgiToAsgi(app)

if __name__ == "__main__":
    # Get config values safely after app creation
    db_name = app.config.get('DB_NAME', 'unknown_db')
    host = os.environ.get('FLASK_RUN_HOST', '127.0.0.1')
    port = int(os.environ.get('FLASK_RUN_PORT', 5000)) # Default to 5000 for dev consistency
    debug = app.config.get('DEBUG', False) # Get debug status from app config
    is_dev_server = app.config.get('IS_DEV_SERVER', False) # Check if running via start-dev

    logger.info(f"Starting Uvicorn server on http://{host}:{port} (DB: {db_name}, Debug: {debug}, Dev Server: {is_dev_server})")

    # Enable reload only if DEBUG is True (typically set by FLASK_DEBUG or IS_DEV_SERVER)
    # Use app factory pattern for uvicorn reload to work correctly
    uvicorn.run(
        "run:create_app", # Point to the factory function string
        factory=True,     # Indicate using factory
        host=host,
        port=port,
        log_level="info",
        reload=debug      # Enable reload based on debug flag
    )



