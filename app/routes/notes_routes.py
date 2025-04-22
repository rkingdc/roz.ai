import logging
from flask import Blueprint, request, jsonify
from app import database

# Configure logging
logger = logging.getLogger(__name__)

bp = Blueprint('notes_api', __name__, url_prefix='/api')

@bp.route('/note', methods=['GET'])
def get_note():
    """API endpoint to retrieve the single note content."""
    logger.info("Received GET request for /api/note")
    try:
        note_content = database.get_note_from_db()
        if note_content is None:
            # If get_note_from_db returns None, it indicates a database error
            logger.error("Failed to retrieve note content from database.")
            return jsonify({"error": "Failed to retrieve note content"}), 500

        logger.info("Successfully retrieved note content.")
        return jsonify({"content": note_content})

    except Exception as e:
        logger.error(f"An unexpected error occurred while getting note: {e}", exc_info=True)
        return jsonify({"error": "An unexpected error occurred"}), 500

@bp.route('/note', methods=['PUT'])
def save_note():
    """API endpoint to save the single note content."""
    logger.info("Received PUT request for /api/note")
    data = request.get_json()
    if not data or 'content' not in data:
        logger.warning("PUT request for /api/note missing 'content' in body.")
        return jsonify({"error": "Missing 'content' in request body"}), 400

    note_content = data['content']
    logger.info(f"Attempting to save note content (length: {len(note_content)})...")

    try:
        success = database.save_note_to_db(note_content)
        if not success:
            logger.error("Failed to save note content to database.")
            return jsonify({"error": "Failed to save note content"}), 500

        logger.info("Successfully saved note content.")
        return jsonify({"message": "Note saved successfully"})

    except Exception as e:
        logger.error(f"An unexpected error occurred while saving note: {e}", exc_info=True)
        return jsonify({"error": "An unexpected error occurred"}), 500
