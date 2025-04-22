# app/__init__.py
import os
from flask import Flask
import google.generativeai as genai

# Configure logging FIRST, at the application entry point
import logging
# Ensure basicConfig is only called once if this file is imported multiple times
if not logging.getLogger(__name__).handlers:
    logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logger.info("Root logger configured to INFO level via basicConfig.")


def create_app(test_config=None):
    """Create and configure an instance of the Flask application."""
    app = Flask(
        __name__,
        template_folder='templates',
        static_folder='static',
        instance_relative_config=True
    )

    # --- Load Configuration ---
    app.config.from_object('app.config.Config') # Load default config
    app.config.from_pyfile('config.py', silent=True) # Load instance config if exists
    # Load test config if passed in
    else:
        app.config.from_mapping(test_config)

    # --- Ensure instance folder exists ---
    try:
        os.makedirs(app.instance_path)
        logger.info(f"Instance folder created at {app.instance_path}")
    except OSError:
        # Already exists or other error, assume it's fine
        logger.info(f"Instance folder found or not needed at {app.instance_path}")

    # --- Configure Logging (Re-check if needed after config load) ---
    # You might want more sophisticated logging config based on app.config here

    # --- Initialize Extensions with App ---
    db.init_app(app)
    migrate.init_app(app, db)

    # --- Import Models ---
    # Import models AFTER db is initialized and associated with the app
    # to ensure models are registered correctly with SQLAlchemy.
    from . import models # noqa

    # --- Configure Gemini API (if needed) ---
    # from . import ai_services
    # ai_services.configure_gemini(app) # Uncomment and adjust if needed

    # --- Register Blueprints ---
    from .routes import main_routes, chat_routes, file_routes # Keep existing
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

    # --- Register Notes Blueprint ---
    try:
        from .routes import notes_routes
        app.register_blueprint(notes_routes.bp)
        logger.info("Registered blueprint: notes_api")
    except ImportError:
        logger.error("Notes routes not found or import error, skipping registration.")
    except Exception as e:
        logger.error(f"Error registering notes blueprint: {e}")
    # ---------------------------------


    # Health Check Route
    @app.route('/health')
    def health():
        return "OK"

    logger.info("Flask app created and configured.")
    return app
