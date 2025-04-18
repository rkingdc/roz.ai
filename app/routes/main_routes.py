# app/routes/main_routes.py
from flask import Blueprint, render_template, current_app

# Create Blueprint
# Use 'main' as the blueprint name, and import_name usually __name__
bp = Blueprint('main', __name__)

@bp.route('/')
def index():
    """Serves the main HTML page, passing available models."""
    available_models = current_app.config.get('AVAILABLE_MODELS', [])
    default_model = current_app.config.get('DEFAULT_MODEL', '')
    return render_template(
        'main.html',
        available_models=available_models,
        default_model=default_model
    )

