# app/__init__.py
import os
from flask import Flask
import google.generativeai as genai # Keep import here if configure_gemini uses it directly

def create_app(test_config=None):
    """Create and configure an instance of the Flask application."""
    app = Flask(__name__, instance_relative_config=True)

    # --- Load Configuration ---
    # Default config from app/config.py
    app.config.from_object('app.config.Config')

    if test_config is None:
        # Load the instance config (instance/config.py), if it exists, when not testing
        # Allows overriding default config easily
        app.config.from_pyfile('config.py', silent=True)
    else:
        # Load the test config if passed in
        app.config.from_mapping(test_config)

    # --- Ensure instance folder exists ---
    try:
        os.makedirs(app.instance_path)
        print(f"Instance folder created at {app.instance_path}")
    except OSError:
        # Already exists or permission error - okay to ignore
        print(f"Instance folder found at {app.instance_path}")

    # --- Configure Gemini API ---
    # Import ai_services here after app is created and configured
    from . import ai_services
    # Pass the app instance to the configuration function
    ai_services.configure_gemini(app)

    # --- Initialize Database ---
    from . import database
    database.init_app(app) # Register close_db and init-db command

    # --- Register Blueprints ---
    from .routes import main_routes, chat_routes, file_routes
    app.register_blueprint(main_routes.bp)
    app.register_blueprint(chat_routes.bp) # url_prefix='/api' is set in the blueprint file
    app.register_blueprint(file_routes.bp) # url_prefix='/api' is set in the blueprint file
    print("Registered blueprints: main, chat_api, file_api")

    # --- Basic Health Check Route (Optional) ---
    @app.route('/health')
    def health():
        return "OK"

    print("Flask app created and configured.")
    return app
