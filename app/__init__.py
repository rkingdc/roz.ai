# app/__init__.py
import os
from flask import Flask
import google.generativeai as genai

# Configure logging FIRST, at the application entry point
import logging
# Set the root logger level to DEBUG to see all messages from all loggers
# This should be done as early as possible.
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)
logger.info("Root logger configured to DEBUG level via basicConfig.")


def create_app(test_config=None):
    """Create and configure an instance of the Flask application."""
    app = Flask(
        __name__,
        template_folder='templates',
        static_folder='static',
        instance_relative_config=True
    )

    # Load Configuration
    app.config.from_object('app.config.Config')
    if test_config is None:
        app.config.from_pyfile('config.py', silent=True)
    else:
        app.config.from_mapping(test_config)

    # Explicitly set logger levels after app creation, just in case Flask's dev server
    # or other imports have modified them.
    logging.getLogger().setLevel(logging.DEBUG) # Set root logger again
    app.logger.setLevel(logging.DEBUG) # Set Flask app logger
    logger.info("Logger levels explicitly set to DEBUG after app creation.")


    # Ensure instance folder exists
    try:
        os.makedirs(app.instance_path)
        logger.info(f"Instance folder created at {app.instance_path}")
    except OSError:
        logger.info(f"Instance folder found at {app.instance_path}")

    # Configure Gemini API
    from . import ai_services
    ai_services.configure_gemini(app)

    # Initialize Database
    from . import database
    # Override DB_NAME with DATABASE_URI from config
    # This line seems redundant as DB_NAME is already set from DATABASE_NAME env var in config.py
    # Keeping it for now, but it might be unnecessary.
    app.config['DB_NAME'] = app.config['DATABASE_URI']

    database.init_app(app)

    # Initialize the database if using TEST_DATABASE
    # Register function to delete the database file when the app context is torn down
    # ONLY delete the file if TEST_DATABASE is true AND it's NOT the development server
    @app.teardown_appcontext
    def close_db_and_remove_db_file(e=None):
        database.close_db()  # Close the database connection
        # Check if TEST_DATABASE is true AND IS_DEV_SERVER is false
        if app.config.get('TEST_DATABASE', False) and not app.config.get('IS_DEV_SERVER', False):
            db_path = app.config.get('DATABASE_URI') # Use DATABASE_URI as it holds the path
            if db_path and db_path != ':memory:': # Ensure it's a file path, not in-memory
                try:
                    os.remove(db_path)
                    logger.info(f"Deleted database file: {db_path}")
                except FileNotFoundError:
                    # File might have already been deleted by another teardown in debug mode
                    logger.debug(f"Database file not found during deletion attempt: {db_path}")
                except OSError as e:
                    logger.warning(f"Failed to delete database file {db_path}: {e}")


    # Register Blueprints
    from .routes import main_routes, chat_routes, file_routes
    app.register_blueprint(main_routes.bp)
    app.register_blueprint(chat_routes.bp)
    app.register_blueprint(file_routes.bp)
    logger.info("Registered blueprints: main, chat_api, file_api")

    # --- Register Calendar Blueprint ---
    try:
        from .routes import calendar_routes
        app.register_blueprint(calendar_routes.bp)
        logger.info("Registered blueprint: calendar_api")
    except ImportError:
        logger.error("Calendar routes not found or import error, skipping registration.")
    except Exception as e:
        logger.error(f"Error registering calendar blueprint: {e}")
    # ---------------------------------

    # Health Check Route
    @app.route('/health')
    def health():
        return "OK"

    logger.info("Flask app created and configured.")
    return app

