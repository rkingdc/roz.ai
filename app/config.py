# app/config.py
import os
from dotenv import load_dotenv

# Configure logging - Removed basicConfig here
import logging

logger = logging.getLogger(__name__)

# Load environment variables from .env file if it exists
load_dotenv()


class Config:
    """Flask configuration variables."""

    # General Config
    SECRET_KEY = (
        os.environ.get("SECRET_KEY") or "a-default-secret-key-for-dev"
    )  # Change in production!
    # DEBUG = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true' # Enable debug mode via env var
    # Let Flask's --debug flag control debug mode when using flask run
    # Keep this setting for other contexts if needed, but it's less critical with --debug
    # For consistency, let's rely on the FLASK_DEBUG env var or the --debug flag.
    # If you want DEBUG=True always in dev, keep this line. If you want --debug to control it, remove it.
    # Let's keep it for now, as it's harmless when --debug is also used.
    DEBUG = os.environ.get("FLASK_DEBUG", "False").lower() == "true"

    # Database
    TEST_DATABASE = (
        os.environ.get("TEST_DATABASE", "FALSE").lower() == "true"
    )  # Keep this flag separate for other logic
    IS_DEV_SERVER = (
        os.environ.get("IS_DEV_SERVER", "FALSE").lower() == "true"
    )  # New flag for dev server
    # Always read DB_NAME from environment variable, default to file name
    DB_NAME = os.environ.get("DATABASE_NAME", "assistant_chat_v8.db")
    logger.info(
        f"Database name configured as: {DB_NAME} (from DATABASE_NAME env var or default)"
    )

    # Define the SQLAlchemy Database URI based on DB_NAME
    # Ensure it's treated as a file path URI for SQLite
    SQLALCHEMY_DATABASE_URI = f"sqlite:///{os.path.abspath(DB_NAME)}"
    logger.info(f"SQLAlchemy Database URI set to: {SQLALCHEMY_DATABASE_URI}")

    # DATABASE_URI = DB_NAME # Remove old/redundant key

    # File Uploads (Using BLOB storage now, UPLOAD_FOLDER not needed)
    # Define allowed extensions for frontend validation and potential backend checks
    ALLOWED_EXTENSIONS = {
        "txt","tf",
        "py",
        "js",
        "html",
        "css",
        "md",
        "json",
        "csv",
        "pdf",
        "png",
        "jpg",
        "jpeg",
        "gif",
        "webp",
        "mp3",
        "md",
    }
    MAX_FILE_SIZE_MB = 20 # Increased from 2MB
    MAX_FILE_SIZE_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024

    # Flask's MAX_CONTENT_LENGTH for request size limit (includes overhead)
    # Increase significantly to allow large audio uploads (e.g., 100MB)
    # Adjust this value based on expected maximum recording size + overhead
    MAX_CONTENT_LENGTH_MB = 200
    MAX_CONTENT_LENGTH = MAX_CONTENT_LENGTH_MB * 1024 * 1024

    # Gemini API
    API_KEY = os.getenv("GEMINI_API_KEY")
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
    GOOGLE_CSE_ID = os.getenv("GOOGLE_CSE_ID")
    DEFAULT_MODEL = "gemini-2.5-flash-preview-04-17"
    SUMMARY_MODEL = "gemini-2.0-flash"  # Model used specifically for summarization
    AVAILABLE_MODELS = [
        "gemini-1.5-flash",
        "gemini-1.5-pro-latest",
        "gemini-2.0-flash",
        "gemini-2.0-flash-thinking-exp-01-21",
        "gemini-2.5-flash-preview-04-17",
        "gemini-2.5-pro-exp-05-06",
        # Add other valid models as needed
    ]
    GEMINI_REQUEST_TIMEOUT = 300  # Timeout for Gemini API calls in seconds

    # Ensure API Key is present for core functionality
    if not API_KEY:
        logger.info("CRITICAL WARNING: GEMINI_API_KEY environment variable not set.")
        # In a real app, you might raise an error or have clearer handling
        # For now, allows app to run but AI features will fail.

        # Google Cloud Storage (for long audio transcription)
    GCS_BUCKET_NAME = os.getenv("GCS_BUCKET_NAME")
    if not GCS_BUCKET_NAME:
        logger.warning(
            "GCS_BUCKET_NAME environment variable not set. Long audio transcription (>1 min) will fail."
        )
