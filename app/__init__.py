# app/__init__.py
import os
from flask import Flask
import google.generativeai as genai

def create_app(test_config=None):
    """Create and configure an instance of the Flask application."""
    app = Flask(__name__, instance_relative_config=True)

    # Load Configuration
    app.config.from_object('app.config.Config')
    if test_config is None:
        app.config.from_pyfile('config.py', silent=True)
    else:
        app.config.from_mapping(test_config)

    # Ensure instance folder exists
    try:
        os.makedirs(app.instance_path)
        print(f"Instance folder created at {app.instance_path}")
    except OSError:
        print(f"Instance folder found at {app.instance_path}")

    # Configure Gemini API
    from . import ai_services
    ai_services.configure_gemini(app)

    # Initialize Database
    from . import database
    database.init_app(app)

    # Register Blueprints
    from .routes import main_routes, chat_routes, file_routes
    app.register_blueprint(main_routes.bp)
    app.register_blueprint(chat_routes.bp)
    app.register_blueprint(file_routes.bp)
    print("Registered blueprints: main, chat_api, file_api")

    # --- Register Calendar Blueprint ---
    try:
        from .routes import calendar_routes
        app.register_blueprint(calendar_routes.bp)
        print("Registered blueprint: calendar_api")
    except ImportError:
        print("Calendar routes not found or import error, skipping registration.")
    except Exception as e:
        print(f"Error registering calendar blueprint: {e}")
    # ---------------------------------

    # Health Check Route
    @app.route('/health')
    def health():
        return "OK"

    print("Flask app created and configured.")
    return app

