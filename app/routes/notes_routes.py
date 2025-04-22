import logging
from flask import Blueprint, request, jsonify
from app import database

# Configure logging
logger = logging.getLogger(__name__)

bp = Blueprint('notes_api', __name__, url_prefix='/api')

@bp.route('/notes', methods=['GET'])
def get_all_notes():
    """API endpoint to retrieve a list of all notes."""
    logger.info("Received GET request for /api/notes")
    try:
        notes_list = database.get_saved_notes_from_db()
        if notes_list is None:
            # If get_saved_notes_from_db returns None, it indicates a database error
            logger.error("Failed to retrieve notes list from database.")
            return jsonify({"error": "Failed to retrieve notes list"}), 500

        logger.info(f"Successfully retrieved {len(notes_list)} notes.")
        return jsonify(notes_list)

    except Exception as e:
        logger.error(f"An unexpected error occurred while getting notes list: {e}", exc_info=True)
        return jsonify({"error": "An unexpected error occurred"}), 500

@bp.route('/notes', methods=['POST'])
def create_new_note():
    """API endpoint to create a new note."""
    logger.info("Received POST request for /api/notes")
    try:
        new_note_id = database.create_new_note_entry()
        if new_note_id is None:
            logger.error("Failed to create new note entry in database.")
            return jsonify({"error": "Failed to create new note"}), 500

        # Fetch the newly created note details to return
        new_note = database.get_note_from_db(new_note_id)
        if new_note is None:
             logger.error(f"Failed to retrieve details for newly created note ID {new_note_id}.")
             # Still return success but maybe with minimal info or an error about fetching details
             return jsonify({"message": "Note created, but failed to fetch details", "id": new_note_id}), 201 # Created
        logger.info(f"Successfully created new note with ID: {new_note_id}")
        return jsonify(new_note), 201 # Created

    except Exception as e:
        logger.error(f"An unexpected error occurred while creating note: {e}", exc_info=True)
        return jsonify({"error": "An unexpected error occurred"}), 500


@bp.route('/note/<int:note_id>', methods=['GET'])
def get_note(note_id):
    """API endpoint to retrieve a specific note content by ID."""
    logger.info(f"Received GET request for /api/note/{note_id}")
    try:
        note_details = database.get_note_from_db(note_id)
        if note_details is None:
            logger.warning(f"Note with ID {note_id} not found.")
            return jsonify({"error": "Note not found"}), 404

        logger.info(f"Successfully retrieved note with ID: {note_id}.")
        return jsonify(note_details)

    except Exception as e:
        logger.error(f"An unexpected error occurred while getting note {note_id}: {e}", exc_info=True)
        return jsonify({"error": "An unexpected error occurred"}), 500

@bp.route('/note/<int:note_id>', methods=['PUT'])
def save_note(note_id):
    """API endpoint to save a specific note content by ID."""
    logger.info(f"Received PUT request for /api/note/{note_id}")
    data = request.get_json()
    if not data or 'content' not in data or 'name' not in data:
        logger.warning(f"PUT request for /api/note/{note_id} missing 'name' or 'content' in body.")
        return jsonify({"error": "Missing 'name' or 'content' in request body"}), 400

    note_name = data['name']
    note_content = data['content']
    logger.info(f"Attempting to save note ID: {note_id} (name: '{note_name}', content length: {len(note_content)})...")

    try:
        success = database.save_note_to_db(note_id, note_name, note_content)
        if not success:
            # Check if the failure was because the note ID wasn't found
            # This requires checking the database function's return or adding a specific check
            # For now, assume generic failure or note not found if update affected 0 rows
            # A more robust implementation might check rowcount in save_note_to_db
            note_exists = database.get_note_from_db(note_id) is not None
            if not note_exists:
                 logger.warning(f"Attempted to save note ID {note_id} but it was not found.")
                 return jsonify({"error": "Note not found"}), 404
            else:
                 logger.error(f"Failed to save note content to database for ID {note_id}.")
                 return jsonify({"error": "Failed to save note content"}), 500


        logger.info(f"Successfully saved note ID: {note_id}.")
        # Optionally return the updated note details or just a success message
        return jsonify({"message": "Note saved successfully"})

    except Exception as e:
        logger.error(f"An unexpected error occurred while saving note {note_id}: {e}", exc_info=True)
        return jsonify({"error": "An unexpected error occurred"}), 500

@bp.route('/note/<int:note_id>', methods=['DELETE'])
def delete_note(note_id):
    """API endpoint to delete a specific note by ID."""
    logger.info(f"Received DELETE request for /api/note/{note_id}")
    try:
        success = database.delete_note_from_db(note_id)
        if not success:
            # Check if the failure was because the note ID wasn't found
            note_exists = database.get_note_from_db(note_id) is not None # Check *before* attempting delete for clearer error
            if not note_exists:
                 logger.warning(f"Attempted to delete note ID {note_id} but it was not found.")
                 return jsonify({"error": "Note not found"}), 404
            else:
                 logger.error(f"Failed to delete note from database for ID {note_id}.")
                 return jsonify({"error": "Failed to delete note"}), 500

        logger.info(f"Successfully deleted note ID: {note_id}.")
        return jsonify({"message": "Note deleted successfully"})

    except Exception as e:
        logger.error(f"An unexpected error occurred while deleting note {note_id}: {e}", exc_info=True)
        return jsonify({"error": "An unexpected error occurred"}), 500
