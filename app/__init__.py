# app/__init__.py
import os
from flask import Flask
import google.generativeai as genai

# Configure logging
import logging        
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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
    app.config['DB_NAME'] = app.config['DATABASE_URI']

    database.init_app(app)

    # Initialize the database if using TEST_DATABASE
    if app.config['TEST_DATABASE']:
        with app.app_context():
            database.init_db()

        # Register function to delete the database file when the app context is torn down
        @app.teardown_appcontext
        def close_db_and_remove_db_file(e=None):
            database.close_db()  # Close the database connection
            try:
                os.remove(app.config['DATABASE_URI'])
                logger.info(f"Deleted database file: {app.config['DATABASE_URI']}")
            except OSError as e:
                logger.warning(f"Failed to delete database file {app.config['DATABASE_URI']}: {e}")

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

