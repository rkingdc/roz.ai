# Configure logging
import logging        
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# app/file_utils.py
from flask import current_app

def allowed_file(filename):
    """Checks if the uploaded file extension is allowed based on config."""
    allowed_extensions = current_app.config.get('ALLOWED_EXTENSIONS', set())
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in allowed_extensions

# Add other file-related utility functions here if needed in the future
# e.g., functions for managing the (now unused) upload directory,
# or more complex filename sanitization.


