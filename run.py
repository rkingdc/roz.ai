# Configure logging
import logging
import os
# import uvicorn # Not needed here anymore, uvicorn is run from Makefile
from asgiref.wsgi import WsgiToAsgi

from app import create_app

logger = logging.getLogger(__name__)

# Create the Flask app instance using the factory
app = create_app()

# Wrap the Flask (WSGI) app with WsgiToAsgi to create an ASGI app
# This asgi_app object will be imported by uvicorn when run from the Makefile
asgi_app = WsgiToAsgi(app)

# The __main__ block is removed as uvicorn will import and run asgi_app directly
# if __name__ == "__main__":
#     host = os.environ.get('FLASK_RUN_HOST', '127.0.0.1')
#     port = int(os.environ.get('FLASK_RUN_PORT', 5000))
#     debug_reload = os.environ.get('IS_DEV_SERVER', 'False').lower() == 'true' or os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
#     logger.info(f"Starting Uvicorn server on http://{host}:{port} (Debug/Reload: {debug_reload})")
#     uvicorn.run(
#         asgi_app,
#         host=host,
#         port=port,
#         log_level="info",
#         reload=debug_reload
#     )
