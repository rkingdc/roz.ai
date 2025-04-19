# app/config.py
import os
from dotenv import load_dotenv

# Load environment variables from .env file if it exists
load_dotenv()

class Config:
    """Flask configuration variables."""

    # General Config
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'a-default-secret-key-for-dev' # Change in production!
    DEBUG = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true' # Enable debug mode via env var

    # Database
    DB_NAME = os.environ.get('DATABASE_NAME', 'assistant_chat_v7.db') # Database filename

    # File Uploads (Using BLOB storage now, UPLOAD_FOLDER not needed)
    # Define allowed extensions for frontend validation and potential backend checks
    ALLOWED_EXTENSIONS = {'txt', 'py', 'js', 'html', 'css', 'md', 'json', 'csv', 'pdf', 'png', 'jpg', 'jpeg', 'gif', 'webp', 'mp3'}
    MAX_FILE_SIZE_MB = 10
    MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024
    # Flask's MAX_CONTENT_LENGTH for request size limit (includes overhead)
    MAX_CONTENT_LENGTH = MAX_FILE_SIZE_BYTES + (2 * 1024 * 1024) # Add 2MB buffer

    # Gemini API
    API_KEY = os.getenv("GEMINI_API_KEY")
    DEFAULT_MODEL = 'gemini-1.5-flash'
    SUMMARY_MODEL = 'gemini-1.5-flash' # Model used specifically for summarization
    AVAILABLE_MODELS = [
        'gemini-1.5-flash',
        'gemini-1.5-pro-latest',
        'gemini-2.0-flash',
        'gemini-2.0-flash-thinking-exp-01-21',
        # Add other valid models as needed
    ]
    GEMINI_REQUEST_TIMEOUT = 300 # Timeout for Gemini API calls in seconds

    # Ensure API Key is present for core functionality
    if not API_KEY:
        print("CRITICAL WARNING: GEMINI_API_KEY environment variable not set.")
        # In a real app, you might raise an error or have clearer handling
        # For now, allows app to run but AI features will fail.

