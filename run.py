# Configure logging
import logging
import os
# import uvicorn # Not needed here anymore, uvicorn is run from Makefile
# from asgiref.wsgi import WsgiToAsgi # Not needed for start-dev anymore

from app import create_app

logger = logging.getLogger(__name__)

# Create the Flask app instance using the factory
# Import socketio along with create_app
from app import create_app, socketio
import os # Import os
import logging # Import logging

logger = logging.getLogger(__name__)

app = create_app()

# The asgi_app wrapper is no longer needed

if __name__ == "__main__":
    host = os.environ.get('FLASK_RUN_HOST', '127.0.0.1')
    port = int(os.environ.get('FLASK_RUN_PORT', 5000))
    # Use FLASK_DEBUG for debug mode which enables reloader and SocketIO verbose logs
    debug_mode = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    logger.info(f"Starting Flask-SocketIO server on http://{host}:{port} (Debug: {debug_mode})")

    # Use socketio.run() instead of app.run() or uvicorn
    # debug=True enables Flask debugger and SocketIO verbose logs.
    # allow_unsafe_werkzeug=True is often needed for the reloader with newer Werkzeug versions.
    # Consider installing eventlet or gevent for better performance.
    socketio.run(
        app,
        host=host,
        port=port,
        debug=debug_mode,
        allow_unsafe_werkzeug=debug_mode # Only allow unsafe when debugging
        # For production, consider:
        # async_mode='eventlet' # or 'gevent'
        # log_output=True
    )
