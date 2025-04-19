# run.py
# This script creates the Flask app using the factory
# and runs the development server.
import os
from app import create_app # Import the factory function from our app package

# Create the Flask app instance
app = create_app()

if __name__ == '__main__':
    # Get config values safely after app creation
    db_name = app.config.get('DB_NAME', 'unknown_db')
    host = os.environ.get('FLASK_RUN_HOST', '127.0.0.1')
    port = int(os.environ.get('FLASK_RUN_PORT', 5678))
    debug = app.config.get('DEBUG', False)

    print(f"Starting Flask server on http://{host}:{port} (DB: {db_name})")
    # Use debug=True carefully in production
    app.run(host=host, port=port, debug=debug)

